from __future__ import annotations

import hashlib
import html
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.xrlinlab.com/"
PEOPLE_URL = urljoin(BASE, "?page_id=32295")
PUBS_URL = urljoin(BASE, "?page_id=32298")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
ASSETS = OUT / "assets"
IMG_DIR = ASSETS / "images"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; xrlinlab-static-migration/1.0)"
})

def fetch(url: str) -> BeautifulSoup:
    r = SESSION.get(url, timeout=60)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return BeautifulSoup(r.text, "html.parser")

def norm_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urljoin(BASE, url)

def image_url(img) -> str | None:
    # QFY lazy-load pages frequently use a placeholder in src and the real image in data-src.
    for key in ("data-src", "src"):
        u = img.get(key)
        if u and not u.startswith("data:"):
            return norm_url(u)
    return None

_image_cache: dict[str, str] = {}

def localize_image(url: str | None) -> str | None:
    if not url:
        return None
    url = norm_url(url)
    if url in _image_cache:
        return _image_cache[url]

    try:
        r = SESSION.get(url, timeout=60)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").split(";")[0].lower()
        suffix_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        suffix = suffix_map.get(ctype)
        if not suffix:
            suffix = Path(urlparse(url).path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
                suffix = ".img"
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:18] + suffix
        target = IMG_DIR / name
        target.write_bytes(r.content)
        rel = f"assets/images/{name}"
        _image_cache[url] = rel
        return rel
    except Exception as exc:
        print(f"[image warning] {url}: {exc}")
        # Keep the source URL as a fallback so content is not lost.
        _image_cache[url] = url
        return url

def unique_page_images(soup: BeautifulSoup):
    seen = set()
    out = []
    for img in soup.find_all("img"):
        u = image_url(img)
        if not u:
            continue
        alt = (img.get("alt") or "").strip()
        key = (u, alt)
        if key in seen:
            continue
        seen.add(key)
        out.append((u, alt))
    return out

def esc(s: str) -> str:
    return html.escape(s, quote=True)

def common_head(title: str, description: str = "Xinrong Lin Lab | 林欣蓉课题组") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{esc(description)}">
  <meta name="keywords" content="Xinrong Lin, 林欣蓉, polymer electrolyte, solid-state battery, organic energy materials">
  <title>{esc(title)}</title>
  <link rel="stylesheet" href="assets/css/style.css">
</head>
<body>
"""

def header(active: str) -> str:
    def cls(name): return ' class="active"' if active == name else ""
    return f"""
<header class="site-header">
  <div class="shell header-inner">
    <a class="brand" href="index.html" aria-label="Xinrong Lin Lab home">
      <span class="brand-main">Organic Energy Materials and Energy Storage Lab</span>
      <span class="brand-cn">有机能源材料与电化学储能实验室</span>
      <span class="brand-sub">Organic Synthetic</span>
    </a>
    <button class="nav-toggle" aria-label="Toggle navigation" aria-expanded="false">Menu</button>
    <nav class="site-nav" aria-label="Primary">
      <a{cls("research")} href="index.html">Research <span>研究内容</span></a>
      <a{cls("people")} href="people.html">People <span>研究人员</span></a>
      <a{cls("publications")} href="publications.html">Publications <span>研究成果</span></a>
    </nav>
  </div>
</header>
"""

def footer() -> str:
    return """
<footer class="site-footer">
  <div class="shell">By Lin Research Lab</div>
</footer>
<script src="assets/js/main.js"></script>
</body>
</html>
"""

def write_static_assets():
    css = r"""
:root{
  --blue:#2969b0;
  --blue-deep:#164f8e;
  --ink:#191919;
  --muted:#6c737d;
  --line:#e8ebef;
  --soft:#f6f8fa;
  --max:1280px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  color:var(--ink);
  background:#fff;
  font-family:Arial,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;
  line-height:1.62;
}
a{color:var(--blue);text-decoration:none}
a:hover{color:var(--blue-deep)}
img{max-width:100%;display:block}
.shell{width:min(var(--max),calc(100% - 48px));margin:0 auto}
.site-header{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:50}
.header-inner{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:28px}
.brand{display:flex;flex-direction:column;color:#111;line-height:1.22}
.brand-main{font-size:20px;font-weight:600;letter-spacing:.01em}
.brand-cn{font-size:15px;margin-top:3px}
.brand-sub{font-size:13px;color:#7a8088;margin-top:6px}
.site-nav{display:flex;align-items:center;gap:28px}
.site-nav a{font-size:15px;color:#222;white-space:nowrap;padding:34px 0 30px;border-bottom:3px solid transparent}
.site-nav a span{color:#757b83;margin-left:3px}
.site-nav a.active{color:var(--blue);border-bottom-color:var(--blue)}
.nav-toggle{display:none;border:0;background:#fff;font-size:15px}
.hero{position:relative;overflow:hidden;background:#f1f4f7}
.hero-track{position:relative;aspect-ratio:16/6;min-height:330px}
.hero-slide{position:absolute;inset:0;opacity:0;transition:opacity .7s ease}
.hero-slide.active{opacity:1}
.hero-slide img{width:100%;height:100%;object-fit:cover}
.hero-dots{position:absolute;left:0;right:0;bottom:18px;display:flex;justify-content:center;gap:8px;z-index:4}
.hero-dot{width:9px;height:9px;border-radius:50%;border:1px solid #fff;background:rgba(255,255,255,.35);padding:0}
.hero-dot.active{background:#fff}
.main{padding:48px 0 72px}
.page-title{font-size:34px;font-weight:500;margin:0 0 34px;letter-spacing:.01em}
.section-title{font-size:25px;font-weight:500;margin:0 0 22px}
.section{padding:30px 0;border-top:1px solid var(--line)}
.section:first-child{border-top:0}
.overview{max-width:1000px;font-size:16px}
.overview ol{padding-left:24px;margin:0}
.overview li{margin:10px 0}
.research-block{margin-top:42px}
.research-gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin:24px 0}
.research-gallery figure{margin:0;border:1px solid var(--line);background:#fff;overflow:hidden}
.research-gallery img{width:100%;aspect-ratio:1/1;object-fit:cover}
.research-gallery figcaption{padding:10px 12px;color:#666;font-size:13px}
.topic-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 28px;padding-left:20px}
.leader-card{display:grid;grid-template-columns:300px 1fr;gap:42px;align-items:start}
.leader-card img{width:100%;aspect-ratio:300/264;object-fit:cover;border:1px solid var(--line)}
.leader-card h2{margin:0 0 8px;font-size:28px;font-weight:500}
.leader-meta{color:#4f5660;margin-bottom:18px}
.leader-bio p{margin:10px 0}
.people-section{margin-top:52px}
.people-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:30px 24px}
.person-card{text-align:center}
.person-card img{width:100%;aspect-ratio:1/1;object-fit:cover;border:1px solid var(--line);background:var(--soft)}
.person-name{font-size:16px;margin-top:10px}
.person-year{font-size:13px;color:var(--muted);margin-top:3px}
.assistant-image{max-width:240px}
.publications{display:flex;flex-direction:column}
.publication-entry{
  display:grid;
  grid-template-columns:minmax(130px,18%) minmax(0,1fr) minmax(170px,27%);
  gap:34px;
  align-items:center;
  padding:32px 0;
  border-top:1px solid var(--line);
}
.publication-entry:first-child{border-top:0}
.publication-visual{display:flex;align-items:center;justify-content:center}
.publication-visual img{max-height:300px;width:auto;max-width:100%;object-fit:contain}
.publication-copy{font-size:15px;min-width:0}
.publication-copy div,.publication-copy p{margin:5px 0}
.publication-copy a{color:var(--blue)}
.publication-copy strong{font-weight:600}
.pub-number{font-weight:600}
.site-footer{border-top:1px solid var(--line);padding:24px 0 40px;color:#777;font-size:13px}
.source-note{font-size:12px;color:#8b9198;margin-top:14px}
@media (max-width:900px){
  .shell{width:min(100% - 30px,var(--max))}
  .header-inner{min-height:76px}
  .brand-main{font-size:16px}
  .brand-cn{font-size:13px}
  .brand-sub{display:none}
  .nav-toggle{display:block}
  .site-nav{display:none;position:absolute;top:76px;left:0;right:0;background:#fff;border-bottom:1px solid var(--line);padding:8px 20px 18px;flex-direction:column;gap:0;align-items:stretch}
  .site-nav.open{display:flex}
  .site-nav a{padding:12px 0;border-bottom:1px solid var(--line)}
  .hero-track{aspect-ratio:4/3;min-height:0}
  .research-gallery{grid-template-columns:1fr}
  .topic-list{grid-template-columns:1fr}
  .leader-card{grid-template-columns:1fr}
  .leader-card img{max-width:300px}
  .people-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .publication-entry{grid-template-columns:1fr;gap:18px}
  .publication-visual img{max-height:280px}
}
@media (max-width:520px){
  .people-grid{grid-template-columns:1fr 1fr;gap:24px 14px}
  .page-title{font-size:28px}
}
"""
    js = r"""
(() => {
  const button = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.site-nav');
  if (button && nav) {
    button.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  const slides = [...document.querySelectorAll('.hero-slide')];
  const dots = [...document.querySelectorAll('.hero-dot')];
  if (slides.length > 1) {
    let active = 0;
    const show = (i) => {
      slides.forEach((s, n) => s.classList.toggle('active', n === i));
      dots.forEach((d, n) => d.classList.toggle('active', n === i));
      active = i;
    };
    dots.forEach((d, i) => d.addEventListener('click', () => show(i)));
    setInterval(() => show((active + 1) % slides.length), 5000);
  }
})();
"""
    (ASSETS / "css").mkdir(parents=True, exist_ok=True)
    (ASSETS / "js").mkdir(parents=True, exist_ok=True)
    (ASSETS / "css" / "style.css").write_text(css.strip() + "\n", encoding="utf-8")
    (ASSETS / "js" / "main.js").write_text(js.strip() + "\n", encoding="utf-8")

def build_home(soup: BeautifulSoup):
    imgs = unique_page_images(soup)
    localized = [(localize_image(u), alt) for u, alt in imgs]
    localized = [(u, a) for u, a in localized if u]

    hero = localized[:4]
    material = localized[4:7]
    energy = localized[7:10]

    hero_html = "\n".join(
        f'<div class="hero-slide{" active" if i == 0 else ""}"><img src="{esc(u)}" alt="{esc(a or "Xinrong Lin Lab")}"></div>'
        for i, (u, a) in enumerate(hero)
    )
    dots = "\n".join(
        f'<button class="hero-dot{" active" if i == 0 else ""}" aria-label="Slide {i+1}"></button>'
        for i in range(len(hero))
    )

    def gallery(items):
        return "\n".join(
            f'<figure><img src="{esc(u)}" alt="{esc(a)}"><figcaption>{esc(a)}</figcaption></figure>'
            for u, a in items
        )

    body = common_head("Xinrong Lin Lab | 林欣蓉课题组 | Homepage 主页")
    body += header("research")
    body += f"""
<section class="hero">
  <div class="hero-track">
    {hero_html}
    <div class="hero-dots">{dots}</div>
  </div>
</section>
<main class="main shell">
  <section class="section">
    <h1 class="page-title">Overview</h1>
    <div class="overview">
      <ol>
        <li>Develop synthetic methodology of new high-performance materials through the design, preparation and characterization of polymer and small molecular materials;</li>
        <li>Build lithium batteries, supercapacitors and flexible devices based on solid-state electrolytes;</li>
        <li>Use modern analysis and characterization techniques to elucidate the structure-performance relationship and ion transport mechanism at the molecular level.</li>
      </ol>
    </div>
  </section>

  <section class="section research-block">
    <h2 class="section-title">Materials Synthesis <span>有机能源材料合成与创制</span></h2>
    <div class="research-gallery">{gallery(material)}</div>
    <ul class="topic-list">
      <li>Polymers 聚合物</li>
      <li>Porous organic materials 有机多孔材料</li>
      <li>Fluorinated molecules 含氟分子</li>
    </ul>
  </section>

  <section class="section research-block">
    <h2 class="section-title">Energy Storage and Conversion <span>聚合物基固态电池与新能源应用</span></h2>
    <div class="research-gallery">{gallery(energy)}</div>
    <ul class="topic-list">
      <li>Solid polymer electrolytes 聚合物电解质</li>
      <li>All-solid-state batteries 固态电池</li>
      <li>Lithium metal batteries 锂金属电池</li>
      <li>Solid-state supercapacitors and beyond batteries 固态超级电容器与超锂电化学储能</li>
    </ul>
  </section>
</main>
"""
    body += footer()
    (OUT / "index.html").write_text(body, encoding="utf-8")

def build_people(soup: BeautifulSoup):
    alt_map: dict[str, str] = {}
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        u = image_url(img)
        if alt and u and alt not in alt_map:
            alt_map[alt] = localize_image(u) or u

    def img_for(*alts):
        for a in alts:
            if a in alt_map:
                return alt_map[a]
        return ""

    def person_card(name, year, *alts):
        src = img_for(*alts)
        img_html = f'<img src="{esc(src)}" alt="{esc(name)}">' if src else '<div class="person-placeholder"></div>'
        return f"""<article class="person-card">
{img_html}
<div class="person-name">{esc(name)}</div>
<div class="person-year">{esc(year)}</div>
</article>"""

    postdocs = [
        ("文鹏", "2026级", "文鹏"),
        ("刘凯庆", "2026级", "刘凯庆师兄"),
    ]
    grads = [
        ("罗光涛 Ph.D.", "2025级", "罗光涛2"),
        ("李林青 Ph.D.", "2025级", "李林青2"),
        ("季利昌 Ph.D.", "2026级", "季利昌2"),
        ("张黎鑫 Ph.D.", "2026级", "张黎鑫"),
        ("陈泽轩", "2024级", "陈泽轩"),
        ("黎励", "2025级", "黎励22"),
        ("王丹", "2025级", "王丹22"),
        ("臧亦宇", "2025级", "臧亦宇"),
    ]
    alumni = [
        ("张鲁", "2016级", "张鲁"),
        ("张佳伟", "2017级", "张佳伟"),
        ("卿霞", "2018级", "卿霞"),
        ("贾旻祎", "2018级", "贾旻祎_2"),
        ("文鹏", "2018级", "文鹏"),
        ("李佳芮", "2019级", "李佳芮"),
        ("谢文", "2019级", "谢文"),
        ("邵飞", "2019级", "邵飞"),
        ("李卫平", "2020级", "李卫平"),
        ("刘晓彤", "2020级", "1"),
        ("任阳", "2020级", "任阳"),
        ("刘昳敏", "2020级", "刘轶敏"),
        ("毛金艳", "2020级", "毛金艳"),
        ("吴柏飞", "2021级", "吴柏飞"),
        ("钱驹", "2021级", "钱驹"),
        ("马祥和", "2021级", "马祥和"),
        ("闫晶莹", "2022级", "闫晶莹2"),
        ("张羽昕", "2022级", "张羽昕2"),
        ("罗飞宇", "2022级", "罗飞宇2"),
        ("肖晨曦", "2022级", "肖晨曦2"),
        ("王文燃", "2023级", "王文燃2(1)"),
        ("卢玺旭", "2023级", "卢玺旭2"),
        ("余登祥", "2023级", "余登祥2"),
        ("周祉融", "2021级（本科生）", "周祉融1"),
        ("林艳梅", "2017级（本科生）", "林艳梅"),
        ("徐文猛", "2017级（本科生）", "徐文猛"),
        ("刘馨", "2017级（本科生）", "刘馨"),
    ]

    leader = img_for("小林老师2")
    assistant = img_for("未标题-2")

    body = common_head("Xinrong Lin Lab | 林欣蓉课题组 | People 研究人员")
    body += header("people")
    body += f"""
<main class="main shell">
  <h1 class="page-title">People 研究人员</h1>

  <section class="section">
    <h2 class="section-title">Research Team Leader 负责人</h2>
    <div class="leader-card">
      <div>{f'<img src="{esc(leader)}" alt="Dr. Xinrong Lin 林欣蓉博士">' if leader else ''}</div>
      <div class="leader-bio">
        <h2>Dr. Xinrong Lin&nbsp;&nbsp; 林欣蓉博士</h2>
        <div class="leader-meta">
          Email: <a href="mailto:xrlin@sioc.ac.cn">xrlin@sioc.ac.cn</a><br>
          <a href="mailto:xinronglinlin@gmail.com">xinronglinlin@gmail.com</a><br>
          ORCID: <a href="https://orcid.org/0000-0003-1157-0175" target="_blank" rel="noopener">0000-0003-1157-0175</a>
        </div>
        <p>Xinrong is a Professor at Shanghai Institute of Organic Chemistry, Chinese Academy of Sciences (CAS). She received her B.S. degree in chemistry from Wuhan University in 2008 (Thesis advisor: Prof. Aiwen Lei) and her Ph.D. degree in chemistry from Boston University in 2014 (Supervisor: Mark W. Grinstaff). Her Ph.D. training was also received from Massachusetts Institute of Technology from 2011 to 2013 (Supervisor: Yang Shao-Horn).</p>
        <p>She then worked as a Postdoctoral Associate at Boston University, Research Team Leader at BASF Global Battery Materials, Associate Professor at Yunnan University, Principal Research Investigator at Duke Kunshan University and Duke University (secondary appointment).</p>
        <p>Xinrong’s research interest centers on the interdisciplinary interface of organic materials design principles and sustainable energy storage technologies and devices, where her research group focuses on chemistry that enables design and synthesis of new electrolyte and electrode molecules for the applications such as solid-state batteries, lithium metal batteries and organic batteries.</p>
        <p>She has received the Outstanding Young Talent by National Natural Science Foundation of China and serves at the early career advisory board at Material Chemistry Frontiers (RSC), etc.</p>
      </div>
    </div>
  </section>

  <section class="section people-section">
    <h2 class="section-title">Postdoc 博士后</h2>
    <div class="people-grid">{''.join(person_card(*x) for x in postdocs)}</div>
  </section>

  <section class="section people-section">
    <h2 class="section-title">Research Assistants 研究助理</h2>
    {f'<img class="assistant-image" src="{esc(assistant)}" alt="Research Assistant">' if assistant else ''}
  </section>

  <section class="section people-section">
    <h2 class="section-title">Graduate Students</h2>
    <div class="people-grid">{''.join(person_card(*x) for x in grads)}</div>
  </section>

  <section class="section people-section">
    <h2 class="section-title">Alumni 毕业生</h2>
    <div class="people-grid">{''.join(person_card(*x) for x in alumni)}</div>
  </section>
</main>
"""
    body += footer()
    (OUT / "people.html").write_text(body, encoding="utf-8")

ALLOWED = {"a", "strong", "em", "b", "i", "span", "div", "p", "br", "ul", "ol", "li"}

def sanitize_wrapper(wrapper) -> str:
    frag = BeautifulSoup(str(wrapper), "html.parser")
    root = frag.find(class_="qfe_wrapper") or frag

    for bad in root.find_all(["script", "style", "svg"]):
        bad.decompose()

    for tag in list(root.find_all(True)):
        if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            tag.name = "div"
        if tag.name not in ALLOWED:
            tag.unwrap()
            continue
        if tag.name == "a":
            keep = {}
            href = tag.get("href")
            if href:
                keep["href"] = norm_url(href)
                keep["target"] = "_blank"
                keep["rel"] = "noopener"
            tag.attrs = keep
        else:
            tag.attrs = {}

    # Remove empty blocks and visual spacing artifacts inherited from the page builder.
    for _ in range(3):
        for tag in list(root.find_all(["div", "p", "span"])):
            text = tag.get_text(" ", strip=True).replace("\xa0", " ").strip()
            if not text and not tag.find("img") and not tag.find("a"):
                tag.decompose()

    inner = "".join(str(x) for x in root.contents)
    inner = inner.replace("&nbsp;", " ")
    inner = re.sub(r"[ \t]{3,}", " ", inner)
    inner = re.sub(r"(?:<br\s*/?>\s*){3,}", "<br><br>", inner, flags=re.I)
    return inner.strip()

def build_publications(soup: BeautifulSoup):
    found = {}
    for wrapper in soup.find_all(class_="qfe_wrapper"):
        text = wrapper.get_text(" ", strip=True).replace("\xa0", " ")
        m = re.match(r"^\s*(\d+)\.\s*", text)
        if not m:
            continue
        n = int(m.group(1))
        if not (1 <= n <= 100) or n in found:
            continue
        section = wrapper.find_parent("section")
        imgs = []
        if section:
            seen = set()
            for img in section.find_all("img"):
                u = image_url(img)
                if u and u not in seen:
                    seen.add(u)
                    loc = localize_image(u)
                    if loc:
                        imgs.append((loc, (img.get("alt") or f"Publication {n}").strip()))
        found[n] = {
            "html": sanitize_wrapper(wrapper),
            "images": imgs[:2],
        }

    # Current public page contains publications 1–41. Fail loudly if parsing becomes incomplete.
    expected = set(range(1, 42))
    missing = sorted(expected - set(found))
    if missing:
        raise RuntimeError(f"Publication parser missed entries: {missing}")

    rows = []
    for n in sorted(found, reverse=True):
        item = found[n]
        imgs = item["images"]
        left = ""
        right = ""
        if len(imgs) >= 1:
            left = f'<div class="publication-visual"><img src="{esc(imgs[0][0])}" alt="{esc(imgs[0][1])}"></div>'
        else:
            left = '<div class="publication-visual"></div>'
        if len(imgs) >= 2:
            right = f'<div class="publication-visual"><img src="{esc(imgs[1][0])}" alt="{esc(imgs[1][1])}"></div>'
        else:
            right = '<div class="publication-visual"></div>'
        rows.append(f"""
<article class="publication-entry" id="publication-{n}">
  {left}
  <div class="publication-copy">{item["html"]}</div>
  {right}
</article>
""")

    body = common_head("Xinrong Lin Lab | 林欣蓉课题组 | Publications 研究成果")
    body += header("publications")
    body += f"""
<main class="main shell">
  <h1 class="page-title">Publications 研究成果</h1>
  <section class="publications">
    {''.join(rows)}
  </section>
</main>
"""
    body += footer()
    (OUT / "publications.html").write_text(body, encoding="utf-8")

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching public source pages...")
    home = fetch(BASE)
    people = fetch(PEOPLE_URL)
    pubs = fetch(PUBS_URL)

    write_static_assets()
    build_home(home)
    build_people(people)
    build_publications(pubs)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built clean static site at {OUT}")
    print(f"Localized {len(_image_cache)} unique images.")

if __name__ == "__main__":
    main()
