# Paper Radar discovery and review

`update_paper_radar.py` is the sole journal/topic/exclusion configuration. The
existing twelve journals and four scientific topics are unchanged. Publisher
RSS and supported latest-research directories supplement Crossref discovery;
they do not expand the inclusion scope.

Run `python3 scripts/update_paper_radar.py --date YYYY-MM-DD` to backfill the
30-day Shanghai-date window. Read `paper-radar-audit.json` after every run.
The GitHub workflow retains it as an Actions artifact, not a public-site file.
Source success and coverage completeness are different. Latest feeds/directories
are not guaranteed complete archives; full 30-day publisher archive pagination
must be independently checked before claiming no missed papers.

Every new relevant candidate needs publisher review. Missing abstract/date/type
is pending, never an automatic rejection. `created` is a registration date and
must never be used as a first-online publication date. Confirm research type,
first-online date, scope, and all explicitly labelled corresponding authors on
the publisher page. Security blocks remain pending; do not bypass them or guess.

Record durable human verification in `assets/data/paper-radar-reviews.json`,
keyed by normalized lower-case DOI. An inclusion record has:

```json
{
  "10.xxxx/example": {
    "decision": "include",
    "articleType": "research",
    "publisherOnlineDate": "YYYY-MM-DD",
    "publisherSource": "https://publisher.example/article",
    "verifiedAt": "YYYY-MM-DD"
  }
}
```

These records contain verified evidence, not additional theme keywords. Exclusion
records use `decision: exclude` and a reason/source. Prefer the script's existing
explicit exclusions when permanently excluding clearly out-of-scope research.
Do not infer authorship from Crossref author order or email placement.

After inclusion, write a reliable Chinese guide, clear the English abstract,
validate DOI and normalized-title uniqueness, and rerun the updater to confirm
review/guide/author preservation. Do not commit timestamp-only changes. Keep
pending review separate from public papers and explicitly disclose unfinished
coverage. Tests: `python3 -m unittest discover -s scripts -p 'test_paper_radar.py'`.
