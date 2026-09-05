#!/usr/bin/env python3
import html
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUTPUT = Path("assets/data/paper-radar.json")
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

def clean(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def date_parts(item, key):
    parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
    if len(parts) < 3:
        return None
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None

def publication_date(item):
    for key in ("published-online", "published-print", "published", "issued"):
        value = date_parts(item, key)
        if value:
            return value
    return None

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
        "filter": f"from-online-pub-date:{start},until-online-pub-date:{end},issn:{issn},type:journal-article",
        "rows": "1000",
        "select": "DOI,title,author,container-title,published-online,published-print,published,issued,URL,abstract,ISSN,volume,issue,page,article-number",
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
        r"batter|anode|cathode|solid electrolyte interphase|lithium[- ]rich layered oxide",
        title_text,
    ))
    ion_material = bool(re.search(
        r"ion[ -]conducting (?:polymer|organo[ -]ionic solid)|single[ -]ion conduct|"
        r"polymer electrolyte|gel polymer electrolyte|composite polymer electrolyte",
        title_text,
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
        r"nasicon electrolyte",
        title_text,
    )) and not bool(re.search(r"solid electrolyte interphase", title_text))
    if solid_state:
        matched.append(TOPICS[1])

    lithium_metal = storage_context and bool(re.search(
        r"lithium[ -]metal|li metal|anode[ -]free lithium",
        title_text,
    ))
    if lithium_metal:
        matched.append(TOPICS[2])

    direct_fast = bool(re.search(
        r"fast[ -]charg|ultrafast[ -]charg|extreme fast charg|high[ -]rate",
        title_text,
    ))
    interface_transport = bool(re.search(
        r"interfac|interphase|solvation|desolvation|dendrite|deposition|plating|"
        r"ion transport|ionic transport|redox kinetics|kinetic[ -]buffering",
        title_text,
    ))
    if storage_context and (direct_fast or interface_transport):
        matched.append(TOPICS[3])
    return matched

def main():
    end = date.today()
    start = end - timedelta(days=WINDOW_DAYS - 1)
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
    for journal, issns in JOURNALS.items():
        journal_items = []
        for issn in issns:
            try:
                journal_items.extend(fetch_issn(issn, start.isoformat(), end.isoformat()))
                time.sleep(0.25)
            except Exception as exc:
                errors.append(f"{journal} ({issn}): {exc}")
        for item in journal_items:
            topics = matched_topics(item)
            pub_date = publication_date(item)
            title = clean((item.get("title") or [""])[0])
            if not topics or not pub_date or not title or not (start <= pub_date <= end):
                continue
            doi = clean(item.get("DOI")).lower()
            key = doi or re.sub(r"[^a-z0-9]+", "", title.lower())
            paper = {
                "title": title,
                "authors": authors(item),
                "authorsCitation": author_initials(item),
                "journal": journal,
                "publicationDate": pub_date.isoformat(),
                "volume": clean(item.get("volume")),
                "issue": clean(item.get("issue")),
                "page": first_page(item),
                "doi": doi,
                "link": f"https://doi.org/{doi}" if doi else clean(item.get("URL")),
                "abstract": clean(item.get("abstract")),
                "matchedTopics": topics,
            }
            old = existing.get(key, {})
            for field in ("summaryZh", "summarySource", "summaryGeneratedAt", "summaryPromptVersion", "correspondingAuthors", "correspondingAuthorSource", "correspondingAuthorVerifiedAt"):
                if old.get(field):
                    paper[field] = old[field]
            if paper.get("summaryZh"):
                paper["abstract"] = ""
            collected[key] = paper
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
