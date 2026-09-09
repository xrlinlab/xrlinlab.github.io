document.addEventListener("DOMContentLoaded", function () {
  var list = document.getElementById("radar-list");
  var filters = document.getElementById("radar-filters");
  var status = document.getElementById("radar-status");
  var data;
  var active = "All";

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function formatDate(value) {
    var parts = String(value || "").split("-");
    if (parts.length !== 3) return value || "Date unavailable";
    var date = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
    return new Intl.DateTimeFormat("en", {month: "long", day: "numeric", year: "numeric", timeZone: "UTC"}).format(date);
  }

  function normalizedAuthorName(name) {
    return String(name || "").normalize("NFKD").replace(/[^\p{L}\p{N}]+/gu, "").toLowerCase();
  }

  function authorLineNode(paper) {
    var line = element("p", "radar-paper-authors");
    var authors = String(paper.authors || "").split(",").map(function (name) { return name.trim(); }).filter(Boolean);
    var corresponding = (paper.correspondingAuthors || []).map(normalizedAuthorName);
    if (!authors.length) {
      line.textContent = "Authors unavailable";
      return line;
    }
    authors.forEach(function (name, index) {
      if (index) line.appendChild(document.createTextNode(", "));
      line.appendChild(document.createTextNode(name));
      if (corresponding.indexOf(normalizedAuthorName(name)) !== -1) {
        var marker = element("sup", "radar-corresponding-mark", "*");
        marker.title = "Corresponding author";
        marker.setAttribute("aria-label", " corresponding author");
        line.appendChild(marker);
      }
    });
    return line;
  }

  function renderFilters() {
    filters.replaceChildren();
    ["All"].concat(data.topics || []).forEach(function (topic) {
      var button = element("button", "radar-filter" + (topic === active ? " active" : ""), topic);
      button.type = "button";
      button.setAttribute("aria-pressed", topic === active ? "true" : "false");
      button.addEventListener("click", function () { active = topic; renderFilters(); renderPapers(); });
      filters.appendChild(button);
    });
  }

  function paperNode(paper) {
    var article = element("article", "radar-paper");
    var title = element("h3", "radar-paper-title");
    var link = element("a", "", paper.title || "Untitled paper");
    link.href = paper.link;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    title.appendChild(link);
    article.appendChild(title);
    article.appendChild(authorLineNode(paper));
    article.appendChild(element("p", "radar-paper-meta", [paper.journal, paper.publicationDate].filter(Boolean).join(" · ")));
    if (paper.doi) {
      var doiLine = element("p", "radar-paper-doi");
      var doiLink = element("a", "", "DOI: " + paper.doi);
      doiLink.href = "https://doi.org/" + paper.doi;
      doiLink.target = "_blank";
      doiLink.rel = "noopener noreferrer";
      doiLine.appendChild(doiLink);
      article.appendChild(doiLine);
    }
    var tags = element("div", "radar-paper-tags");
    (paper.matchedTopics || []).forEach(function (topic) { tags.appendChild(element("span", "radar-paper-tag", topic)); });
    article.appendChild(tags);
    if (paper.abstract) article.appendChild(element("p", "radar-paper-abstract", paper.abstract));
    if (paper.summaryZh) {
      var guide = element("div", "radar-summary");
      var label = element("div", "radar-summary-label", "AI 中文导读");
      if (paper.summarySource === "title-only") label.appendChild(element("span", "radar-summary-caveat", "基于标题"));
      guide.appendChild(label);
      var summaryText = String(paper.summaryZh).replace(/\\r\\n|\\n|\\r/g, "\n");
      summaryText.split(/\r?\n/).filter(Boolean).forEach(function (line) {
        var match = line.match(/^(.+?)[？?]?\s*[：:]\s*(.+)$/);
        var row = element("p", "radar-summary-text");
        row.lang = "zh-CN";
        if (match) {
          var strong = element("strong", "", match[1] + "：");
          row.appendChild(strong);
          row.appendChild(document.createTextNode(match[2]));
        } else {
          row.textContent = line;
        }
        guide.appendChild(row);
      });
      article.appendChild(guide);
    }
    return article;
  }

  function renderPapers() {
    list.replaceChildren();
    var papers = (data.papers || []).filter(function (paper) {
      return active === "All" || (paper.matchedTopics || []).indexOf(active) !== -1;
    });
    var guideCount = papers.filter(function (paper) { return Boolean(paper.summaryZh); }).length;
    status.textContent = papers.length + " paper" + (papers.length === 1 ? "" : "s") + " · " + guideCount + " Chinese guide" + (guideCount === 1 ? "" : "s") + (data.generatedAt ? " · Updated " + new Date(data.generatedAt).toLocaleDateString("en") : "");
    if (!papers.length) {
      list.appendChild(element("p", "radar-empty", "No matching papers in the current archive."));
      return;
    }
    var dates = [];
    papers.forEach(function (paper) { if (dates.indexOf(paper.publicationDate) === -1) dates.push(paper.publicationDate); });
    dates.sort().reverse().forEach(function (dateValue) {
      var section = element("section", "radar-day");
      var heading = element("div", "radar-day-heading radar-date");
      var paperList = element("div", "radar-papers");
      var datePapers = papers.filter(function (paper) { return paper.publicationDate === dateValue; });
      heading.appendChild(element("h2", "radar-day-date", formatDate(dateValue)));
      heading.appendChild(element("span", "radar-day-count", datePapers.length + " paper" + (datePapers.length === 1 ? "" : "s")));
      section.appendChild(heading);
      datePapers.forEach(function (paper) { paperList.appendChild(paperNode(paper)); });
      section.appendChild(paperList);
      list.appendChild(section);
    });
  }

  fetch("assets/data/paper-radar.json?v=" + Date.now(), {cache: "no-store"})
    .then(function (response) { if (!response.ok) throw new Error("HTTP " + response.status); return response.json(); })
    .then(function (payload) { data = payload; renderFilters(); renderPapers(); })
    .catch(function () { status.textContent = "Data unavailable"; list.appendChild(element("p", "radar-empty", "Paper data could not be loaded.")); });
});
