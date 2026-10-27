#!/usr/bin/env python3
import html
import json
import re
import time
import argparse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

OUTPUT = Path("assets/data/paper-radar.json")
AUDIT = Path("paper-radar-audit.json")
REVIEWS = Path("assets/data/paper-radar-reviews.json")
WINDOW_DAYS = 30
JOURNALS = {
    "Science": ["0036-8075", "1095-9203"],
    "Nature": ["0028-0836", "1476-4687"],
    "Nature Materials": ["1476-1122", "1476-4660"],
    "Nature Chemistry": ["1755-4330", "1755-4349"],
    "Nature Energy": ["2058-7546"],
    "Nature Nanotechnology": ["1748-3387", "1748-3395"],
    "Joule": ["2542-4351"],
    "Chem": ["2451-9294"],
    "Journal of the American Chemical Society": ["0002-7863", "1520-5126"],
    "Angewandte Chemie International Edition": ["1433-7851", "1521-3773"],
    "Macromolecules": ["0024-9297", "1520-5835"],
    "Nature Sustainability": ["2398-9629"],
}
TOPICS = [
    "Ion-conducting polymers and single-ion conductors",
    "Solid-state batteries",
    "Lithium-metal and anode-free batteries",
    "Fast charging and interfacial ion transport",
]

# Independent publisher discovery, not additional journals or research topics.
PUBLISHER_FEEDS = {
    **{journal: f"https://www.nature.com/{slug}.rss" for journal, slug in (
        ("Nature", "nature"), ("Nature Materials", "nmat"),
        ("Nature Chemistry", "nchem"), ("Nature Energy", "nenergy"),
        ("Nature Nanotechnology", "nnano"), ("Nature Sustainability", "natsustain"))},
    "Science": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    "Joule": "https://www.cell.com/joule/rss",
    "Chem": "https://www.cell.com/chem/rss",
    "Journal of the American Chemical Society": "https://pubs.acs.org/action/showFeed?type=etoc&feed=rss&jc=jacsat",
    "Macromolecules": "https://pubs.acs.org/action/showFeed?type=etoc&feed=rss&jc=mamobx",
    "Angewandte Chemie International Edition": "https://onlinelibrary.wiley.com/feed/15213773/most-recent",
}
PUBLISHER_DIRECTORIES = {
    **{j: u.removesuffix(".rss") + "/research-articles" for j, u in PUBLISHER_FEEDS.items()
       if "www.nature.com/" in u},
    "Joule": "https://www.cell.com/joule/inpress",
    "Chem": "https://www.cell.com/chem/inpress",
}

# Explicitly reviewed false positives that match broad interface keywords but fall
# outside the configured Paper Radar research scope.
EXCLUDED_DOIS = {
    "10.1002/anie.5076332",  # Na–CO2 battery
    "10.1002/anie.1544949",  # aluminum-metal battery
    "10.1021/jacs.6c05378",  # bulk Li-ion transport in a disordered cathode
    "10.1021/acs.macromol.6c01264",  # bottlebrush suppresses crystallization: established polymer-electrolyte logic
    "10.1002/anie.3712910",  # aqueous LMO cathode degradation; outside configured fast-charge/ion-transport scope
    "10.1002/anie.9049103",  # Li–CO2 cathode catalyst/product crystallography; outside configured scope
    "10.1002/anie.2026-m2509035600",  # Inside Front Cover metadata; not a distinct research article
    "10.1038/s41565-026-02301-2",  # cation-disordered rocksalt cathode hysteresis; bulk positive-electrode mechanism
    "10.1021/jacs.6c15213",  # Mg-metal battery separator/solvation; outside the configured lithium/solid-state scope
    "10.1021/jacs.6c15661",  # oxychloride stacking/band structure; battery appears only as background context
    "10.1016/j.joule.2026.102706",  # Joule preview of a Nature Nanotechnology study; not a distinct research article
    "10.1021/jacs.6c15210",  # anode-free potassium-metal battery; outside configured lithium/solid-state scope
    "10.1002/anie.5594912",  # Li-rich cathode binder/anionic-redox study; outside configured electrolyte scope
    "10.1126/science.ael3782",  # Science Perspective accompanying a research article; not a distinct study
    "10.1038/s41563-026-02757-6",  # Nature Materials News & Views; not a distinct research article
}

def clean(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Superscript markup such as Li<sup>+</sup> otherwise becomes "Li +".
    return re.sub(r"(?<=[A-Za-z0-9])\s+([+-])(?=\s|$)", r"\1", text)

def date_parts(item, key):
    parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
    if len(parts) < 3:
        return None
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None

def partial_date_parts(item, key):
    parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
    try:
        return tuple(int(part) for part in parts)
    except (TypeError, ValueError):
        return ()

def publication_date(item):
    if item.get("_publisherDate"):
        return date.fromisoformat(item["_publisherDate"])
    for key in ("published-online", "published-print", "published", "issued"):
        value = date_parts(item, key)
        if value:
            return value
    # User-selected proxy when an exact publication date is unavailable.
    return date_parts(item, "created")

def publication_date_source(item):
    if item.get("_publisherDate"):
        return "publisher-online"
    for key in ("published-online", "published-print", "published", "issued"):
        if date_parts(item, key):
            return "crossref-" + key
    return "crossref-registration" if date_parts(item, "created") else "unavailable"

def authors(item):
    names = []
    for author in item.get("author") or []:
        name = " ".join(part for part in (author.get("given", "").strip(), author.get("family", "").strip()) if part)
        if name:
            names.append(name)
    return ", ".join(names)

def author_initials(item):
    formatted = []
    for author in item.get("author") or []:
        family = clean(author.get("family"))
        given = clean(author.get("given"))
        if not family:
            name = clean(author.get("name"))
            if name:
                formatted.append(name)
            continue
        groups = []
        for group in given.split():
            parts = [part for part in group.split("-") if part]
            if parts:
                groups.append("-".join(f"{part[0].upper()}." for part in parts))
        initials = " ".join(groups)
        formatted.append(f"{initials} {family}".strip())
    return ", ".join(formatted)

def first_page(item):
    value = clean(item.get("page") or item.get("article-number"))
    if not value:
        return ""
    return re.split(r"[-–—]", value, maxsplit=1)[0].strip()

def fetch_issn(issn, start, end):
    params = {
        # Science and some other publishers deposit newly released articles
        # with published/issued or published-print, but no published-online
        # field. Filtering only on the online date silently drops them before
        # the topic matcher can run.
        "filter": f"from-pub-date:{start},until-pub-date:{end},issn:{issn},type:journal-article",
        "rows": "1000",
        "select": "DOI,title,author,container-title,published-online,published-print,published,issued,created,URL,abstract,ISSN,volume,issue,page,article-number",
        "mailto": "xinronglinlin@gmail.com",
    }
    url = "https://api.crossref.org/works?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "MolEnergy-Paper-Radar/1.0 (mailto:xinronglinlin@gmail.com)", "Accept": "application/json"})
    with urlopen(request, timeout=45) as response:
        return json.load(response).get("message", {}).get("items", [])

def matched_topics(item):
    title = clean((item.get("title") or [""])[0])
    abstract = clean(item.get("abstract"))
    title_text = re.sub(r"[‐‑‒–—−]", "-", title.lower())
    corpus = re.sub(r"[‐‑‒–—−]", "-", (title + " " + abstract).lower())
    if re.match(r"^(author correction|correction(?: to)?|editorial)(?::|\b)", title_text):
        return []

    matched = []
    storage_context = bool(re.search(
        r"batter|anode|cathode|solid electrolyte interphase|lithium[- ]rich layered oxide|"
        r"(?:lithium.{0,30}dendrite|dendrite.{0,30}lithium)|"
        r"(?:zinc.{0,30}dendrite|dendrite.{0,30}zinc)|electrode[- ]scale ion transport",
        title_text,
    ))
    ion_material = bool(re.search(
        r"ion[ -]conducting (?:polymer|organo[ -]ionic solid)|single[ -]ion conduct|"
        r"polymer electrolyte|gel polymer electrolyte|composite polymer electrolyte|hydrogel electrolyte",
        corpus,
    ))
    ion_function = bool(re.search(
        r"ionic conductivity|ion transport|proton conduction|cation conduction|"
        r"anion conduction|li\s*\+ transport|na\s*\+ transport|vehicular transport",
        corpus,
    ))
    if ion_material and ion_function:
        matched.append(TOPICS[0])

    solid_state = bool(re.search(
        r"all[ -]solid[ -]state.{0,25}batter|solid[ -]state.{0,25}batter|"
        r"(?:composite|polymer|ceramic|halide|sulfide(?:[ -]chloride)?) solid electrolyte|"
        r"solid[ -]state(?:[ -]+\w+){0,4}[ -]+electrolytes?|"
        r"li\s*\+? solid[- ]state electrolyte|sulfide superionic conductor|nasicon electrolyte",
        corpus,
    )) and not bool(re.search(r"solid electrolyte interphase", title_text))
    if solid_state:
        matched.append(TOPICS[1])

    lithium_metal = bool(re.search(
        r"lithium[ -]metal|\bli metal\b|anode[ -]free lithium|"
        r"lithium.{0,20}failure|li plating/stripping|"
        r"lithium[ -](?:sulfur|disulfur dichloride) batter",
        title_text,
    )) or (storage_context and bool(re.search(
        r"lithium[ -]metal|\bli metal\b|anode[ -]free lithium",
        corpus,
    )))
    if lithium_metal:
        matched.append(TOPICS[2])

    direct_fast = bool(re.search(
        r"fast[ -]charg|ultrafast[ -]charg|extreme fast charg|high[ -]rate",
        title_text,
    ))
    interface_transport = bool(re.search(
        r"interfac|interphase|solvation|desolvation|dendrite|deposition|plating|"
        r"ion transport|ionic transport|redox kinetics|kinetic[ -]buffering|"
        r"multi[- ]li\s*\+? clustering|molecular gating",
        title_text,
    ))
    if storage_context and (direct_fast or interface_transport):
        matched.append(TOPICS[3])
    return matched

def normalized_title(title):
    return re.sub(r"[^a-z0-9]+", "", clean(title).lower())

def candidate(item):
    """High-recall routing only. This NEVER authorizes public inclusion."""
    title = clean((item.get("title") or [""])[0]).lower()
    return bool(re.search(r"batter|electrolyt|ion[ -]conduct|superionic|lithium|"
                          r"\bli\+|anode|cathode|dendrite|solvation|interphase", title))

def read_url(url):
    request = Request(url, headers={"User-Agent": "MolEnergy-Paper-Radar/2.0 (literature metadata)",
                                    "Accept": "text/html,application/rss+xml,application/xml"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace"), response.url

def feed_items(url):
    body, _ = read_url(url)
    root = ET.fromstring(body)
    result = []
    for entry in root.iter():
        if entry.tag.split("}")[-1] not in ("item", "entry"):
            continue
        fields = {}
        for child in entry:
            key = child.tag.split("}")[-1].lower()
            fields[key] = child.attrib.get("href") or "".join(child.itertext()).strip()
        title = clean(fields.get("title"))
        doi_text = " ".join(fields.get(k, "") for k in ("doi", "identifier", "link", "id"))
        found = re.search(r"10\.\d{4,9}/[^\s<>\"?#]+", html.unescape(doi_text), re.I)
        item = {"title": [title], "DOI": found.group(0).rstrip(".,;") if found else "",
                "URL": fields.get("link", ""), "_publisherFeed": url}
        # Feed dates are discovery timestamps, not assumed first-online dates.
        item["_feedDate"] = fields.get("pubdate") or fields.get("date") or fields.get("published")
        if title:
            result.append(item)
    if not result:
        raise ValueError("Publisher feed contained no parseable entries")
    return result

def directory_items(url):
    body, final = read_url(url)
    if "Site Unavailable" in body or "Performing security verification" in body:
        raise ValueError("Publisher directory unavailable")
    result = []
    # Nature research directory cards expose article title and canonical DOI URL.
    for href, title in re.findall(r'<a\b[^>]*href="([^"]*/articles/[^"]+)"[^>]*>(.*?)</a>', body, re.S):
        title = clean(title)
        link = urljoin(final, html.unescape(href))
        match = re.search(r"/articles/(s[\w-]+)(?:$|[?#])", link)
        if title and match:
            result.append({"DOI": "10.1038/" + match.group(1), "title": [title],
                           "URL": link, "_publisherDirectory": url})
    if not result:
        raise ValueError("No supported article cards parsed; manual directory review required")
    return result

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            self.values.setdefault(key, []).append(attrs.get("content", ""))

def publisher_metadata(item):
    doi = clean(item.get("DOI")).lower()
    url = item.get("URL") or f"https://doi.org/{doi}"
    body, final_url = read_url(url)
    if re.search(r"<title>[^<]*(?:just a moment|access denied)|performing security verification", body, re.I):
        raise ValueError("Publisher security verification; no bypass attempted")
    parser = MetaParser()
    parser.feed(body)
    values = parser.values
    declared = clean((values.get("citation_doi") or [""])[0]).lower()
    if not doi or declared != doi:
        raise ValueError("Publisher page DOI not verified")
    abstract = clean((values.get("citation_abstract") or values.get("dc.description") or
                      values.get("description") or values.get("og:description") or [""])[0])
    # Only explicitly online-labelled dates; never infer from issue/registration.
    raw_date = (values.get("citation_online_date") or values.get("dc.date.online") or [""])[0]
    pub_date = None
    match = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw_date)
    if match:
        pub_date = date(*map(int, match.groups())).isoformat()
    return {"abstract": abstract, "date": pub_date, "url": final_url}

def write_if_changed(path, payload):
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) == payload:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    args = argparse.ArgumentParser(description="Discover, review and update Paper Radar")
    args.add_argument("--date", type=date.fromisoformat, help="Shanghai date for reproducible backfills")
    args.add_argument("--audit-path", type=Path, default=AUDIT)
    options = args.parse_args()
    # The site and scheduled task use Shanghai time.  Using the runner's UTC
    # date keeps previous-day papers one day too long during the morning run.
    end = options.date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    # Crossref interprets incomplete YYYY-MM publication dates as the first of
    # the month when applying its server-side date filter.  Query from the
    # beginning of the boundary month, then enforce the exact 30-day window
    # locally using verified publication dates, never registration timestamps.
    query_start = start.replace(day=1)
    existing = {}
    previous_payload = None
    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
            previous_payload = previous
            existing = {
                (paper.get("doi") or re.sub(r"[^a-z0-9]+", "", paper.get("title", "").lower())): paper
                for paper in previous.get("papers", []) if isinstance(paper, dict)
            }
        except (OSError, json.JSONDecodeError):
            existing = {}
    collected = {}
    errors = []
    reviews = json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}
    audit = {"windowStart": start.isoformat(), "windowEnd": end.isoformat(),
             "coverageComplete": False, "journals": {}, "pending": []}
    def fetch_feed(journal):
        try:
            return feed_items(PUBLISHER_FEEDS[journal]), None
        except Exception as exc:
            return [], str(exc)
    with ThreadPoolExecutor(max_workers=6) as pool:
        feeds = dict(zip(JOURNALS, pool.map(fetch_feed, JOURNALS)))
    def fetch_directory(journal):
        if journal not in PUBLISHER_DIRECTORIES:
            return [], "No directory adapter: manual archive review required"
        try:
            return directory_items(PUBLISHER_DIRECTORIES[journal]), None
        except Exception as exc:
            return [], str(exc)
    with ThreadPoolExecutor(max_workers=6) as pool:
        directories = dict(zip(JOURNALS, pool.map(fetch_directory, JOURNALS)))
    for journal, issns in JOURNALS.items():
        print(f"Auditing {journal}...", flush=True)
        journal_items = []
        stats = {"crossrefRecords": 0, "publisherFeedRecords": len(feeds[journal][0]),
                 "publisherFeedError": feeds[journal][1], "included": 0, "pending": 0,
                 "publisherDirectoryRecords": len(directories[journal][0]),
                 "publisherDirectoryError": directories[journal][1],
                 "excluded": 0, "outsideWindow": 0, "notCandidate": 0,
                 "coverage": "partial: latest feed is not a full 30-day publisher archive"}
        audit["journals"][journal] = stats
        for issn in issns:
            try:
                journal_items.extend(fetch_issn(issn, query_start.isoformat(), end.isoformat()))
                time.sleep(0.25)
            except Exception as exc:
                errors.append(f"{journal} ({issn}): {exc}")
        stats["crossrefRecords"] = len({i.get("DOI") for i in journal_items})
        merged = {clean(i.get("DOI")).lower() or normalized_title((i.get("title") or [""])[0]): i
                  for i in journal_items}
        for feed_item in feeds[journal][0] + directories[journal][0]:
            key = clean(feed_item.get("DOI")).lower() or normalized_title(feed_item["title"][0])
            if key in merged:
                merged[key]["_publisherDiscovery"] = True
            else:
                merged[key] = feed_item
        def enrich(entry):
            key, item = entry
            if key in existing or key in EXCLUDED_DOIS or not candidate(item):
                return key, None, None
            pub_date = publication_date(item)
            if pub_date and not start <= pub_date <= end:
                return key, None, None
            if clean(item.get("abstract")) and pub_date:
                return key, None, None
            try:
                return key, publisher_metadata(item), None
            except Exception as exc:
                return key, None, str(exc)
        with ThreadPoolExecutor(max_workers=4) as pool:
            metadata = {key: (meta, error) for key, meta, error in pool.map(enrich, merged.items())}
        for item in merged.values():
            doi = clean(item.get("DOI")).lower()
            title = clean((item.get("title") or [""])[0])
            review = reviews.get(doi, {})
            if doi in EXCLUDED_DOIS or review.get("decision") == "exclude":
                stats["excluded"] += 1
                continue
            if review.get("publisherOnlineDate") and review.get("publisherSource"):
                item["_publisherDate"] = review["publisherOnlineDate"]
            topics = matched_topics(item)
            if review.get("decision") == "include" and review.get("publisherSource"):
                reviewed_topics = review.get("matchedTopics", [])
                if reviewed_topics and all(topic in TOPICS for topic in reviewed_topics):
                    topics = reviewed_topics
            pub_date = publication_date(item)
            old = existing.get(doi, {})
            if pub_date and not (start <= pub_date <= end):
                stats["outsideWindow"] += 1
                continue
            if not (topics or candidate(item) or old):
                stats["notCandidate"] += 1
                continue
            metadata_error = None
            if not old and (not clean(item.get("abstract")) or not pub_date):
                meta, metadata_error = metadata.get(doi or normalized_title(title), (None, None))
                if meta:
                    if meta["abstract"]:
                        item["abstract"] = meta["abstract"]
                    if meta["date"]:
                        item["_publisherDate"] = meta["date"]
                    topics, pub_date = matched_topics(item), publication_date(item)
            if pub_date and not (start <= pub_date <= end):
                stats["outsideWindow"] += 1
                continue
            approved = bool(topics) or (review.get("decision") == "include"
                        and review.get("publisherSource") and review.get("verifiedAt"))
            if approved and review.get("matchedTopics") and all(t in TOPICS for t in review["matchedTopics"]):
                topics = review["matchedTopics"]
            if not old and (not approved or not pub_date or not topics):
                reasons = []
                # Missing both publication and registration dates cannot be placed
                # in the 30-day public list; report as unprocessable, not pending.
                if not pub_date:
                    stats["missingAllDates"] = stats.get("missingAllDates", 0) + 1
                    continue
                if not topics: reasons.append("topic-needs-semantic-review")
                audit["pending"].append({"journal": journal, "doi": doi, "title": title,
                    "reasons": reasons, "publisherError": metadata_error,
                    "registrationDate": str(date_parts(item, "created") or ""),
                    "matchedTopics": topics})
                stats["pending"] += 1
                continue
            if old and (not pub_date or not topics):
                # Do not erase reviewed articles just because a deposit loses metadata.
                pub_date = date.fromisoformat(old["publicationDate"])
                topics = old.get("matchedTopics", [])
                if not start <= pub_date <= end:
                    stats["outsideWindow"] += 1
                    continue
            key = doi or re.sub(r"[^a-z0-9]+", "", title.lower())
            paper = {
                "title": title,
                "authors": authors(item),
                "authorsCitation": author_initials(item),
                "journal": journal,
                "publicationDate": pub_date.isoformat(),
                "publicationDateSource": publication_date_source(item),
                "volume": clean(item.get("volume")),
                "issue": clean(item.get("issue")),
                "page": first_page(item),
                "doi": doi,
                "link": f"https://doi.org/{doi}" if doi else clean(item.get("URL")),
                "abstract": clean(item.get("abstract")),
                "matchedTopics": topics,
            }
            old = existing.get(key, {})
            for field in ("authors", "authorsCitation", "volume", "issue", "page"):
                if not paper.get(field) and old.get(field):
                    paper[field] = old[field]
            for field in ("summaryZh", "summarySource", "summaryGeneratedAt", "summaryPromptVersion", "correspondingAuthors", "correspondingAuthorSource", "correspondingAuthorVerifiedAt"):
                if old.get(field):
                    paper[field] = old[field]
            if paper.get("summaryZh"):
                paper["abstract"] = ""
            collected[key] = paper
            stats["included"] += 1
        # Feed/Crossref outages must not silently delete existing in-window records.
        for key, old in existing.items():
            if old.get("journal") != journal or key in collected or key in EXCLUDED_DOIS:
                continue
            if reviews.get(key, {}).get("decision") == "exclude":
                continue
            if start.isoformat() <= old["publicationDate"] <= end.isoformat():
                paper = dict(old)
                if paper.get("summaryZh"): paper["abstract"] = ""
                collected[key] = paper
                stats["included"] += 1
                audit["pending"].append({"journal": journal, "doi": key, "title": old["title"],
                                         "reasons": ["existing-record-missing-from-current-discovery"]})
                stats["pending"] += 1
    # Duplicate title and DOI checks are independent.
    seen_titles = set()
    deduplicated = {}
    for key, paper in sorted(collected.items(), key=lambda pair: not bool(pair[1].get("summaryZh"))):
        title_key = normalized_title(paper["title"])
        if title_key not in seen_titles:
            deduplicated[key] = paper
            seen_titles.add(title_key)
    collected = deduplicated
    audit["sourceErrors"] = errors
    audit["pending"].sort(key=lambda p: (p["journal"], p.get("doi", ""), p["title"]))
    write_if_changed(options.audit_path, audit)
    print(f"Coverage incomplete: {len(audit['pending'])} pending; inspect {options.audit_path}.")
    papers = sorted(collected.values(), key=lambda p: (p["publicationDate"], p["title"]), reverse=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "windowDays": WINDOW_DAYS,
        "topics": TOPICS,
        "journals": list(JOURNALS),
        "papers": papers,
        "source": "Crossref",
        "errors": errors,
    }
    if previous_payload is not None:
        previous_semantic = {key: value for key, value in previous_payload.items() if key != "generatedAt"}
        current_semantic = {key: value for key, value in payload.items() if key != "generatedAt"}
        if previous_semantic == current_semantic:
            print("Paper data is unchanged.")
            return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(papers)} papers; {len(errors)} source errors.")

if __name__ == "__main__":
    main()
