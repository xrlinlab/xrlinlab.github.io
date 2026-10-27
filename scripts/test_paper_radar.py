"""Offline regression tests: python3 -m unittest discover -s scripts -p 'test_paper_radar.py'."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import update_paper_radar as r


class RadarTests(unittest.TestCase):
    def test_solid_electrolyte_word_order(self):
        for title in ("Transport in solid-state halide electrolytes",
                      "Transport in halide solid electrolytes",
                      "Transport in solid‐state sulfide electrolytes"):
            self.assertIn(r.TOPICS[1], r.matched_topics({"title": [title]}))

    def test_actual_joule_miss(self):
        title = "Regulating carrier transport and oxychloride interphase formation by increasing configurational complexity in solid-state halide electrolytes"
        self.assertIn(r.TOPICS[1], r.matched_topics({"title": [title]}))

    def test_registration_not_publication(self):
        x = {"published-print": {"date-parts": [[2026, 10]]},
             "created": {"date-parts": [[2026, 10, 26]]}}
        self.assertIsNone(r.publication_date(x))

    def test_publisher_date_precedes_issue(self):
        x = {"_publisherDate": "2026-09-20", "published-print": {"date-parts": [[2026, 10, 20]]}}
        self.assertEqual(str(r.publication_date(x)), "2026-09-20")

    def test_candidate_not_inclusion(self):
        x = {"title": ["Unusual battery behaviour"]}
        self.assertTrue(r.candidate(x))
        self.assertEqual(r.matched_topics(x), [])

    def test_rss_and_rdf(self):
        for xml in ('<rss><channel><item><title>Test battery</title><link>https://doi.org/10.1234/test</link></item></channel></rss>',
                    '<RDF><item><title>Test battery</title><identifier>doi:10.1234/test</identifier></item></RDF>'):
            with patch.object(r, "read_url", return_value=(xml, "https://publisher.test/rss")):
                self.assertEqual(r.feed_items("https://publisher.test/rss")[0]["DOI"], "10.1234/test")

    def test_empty_feed_is_error(self):
        with patch.object(r, "read_url", return_value=("<html>Site Unavailable</html>", "https://publisher.test")):
            with self.assertRaises(ValueError): r.feed_items("https://publisher.test")

    def test_directory(self):
        with patch.object(r, "read_url", return_value=('<a href="/articles/s41560-026-00000-0">A battery study</a>', "https://www.nature.com/nenergy/research-articles")):
            self.assertEqual(r.directory_items("test")[0]["DOI"], "10.1038/s41560-026-00000-0")

    def test_exclusions_unchanged(self):
        self.assertIn("10.1016/j.joule.2026.102706", r.EXCLUDED_DOIS)
        self.assertEqual(len(r.TOPICS), 4)
        self.assertEqual(len(r.JOURNALS), 12)

    def test_pending_preservation_and_idempotence(self):
        old = {"doi": "10.1234/old", "title": "Old solid-state battery",
               "journal": "Joule", "publicationDate": "2026-10-01",
               "authors": "Complete Author", "summaryZh": "既有导读",
               "summarySource": "publisher-abstract", "summaryGeneratedAt": "original",
               "summaryPromptVersion": 2, "abstract": "must be cleared",
               "correspondingAuthors": ["Verified Person"],
               "correspondingAuthorSource": "publisher", "correspondingAuthorVerifiedAt": "2026-10-02",
               "matchedTopics": [r.TOPICS[1]]}
        new = {"DOI": "10.1234/new", "title": ["New solid-state halide electrolytes"],
               "published-print": {"date-parts": [[2026, 10]]},
               "created": {"date-parts": [[2026, 10, 20]]}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            audit = Path(tmp) / "audit.json"
            output.write_text(json.dumps({"papers": [old]}))
            with patch.object(r, "OUTPUT", output), patch.object(r, "REVIEWS", Path(tmp)/"reviews.json"), \
                 patch.object(r, "fetch_issn", return_value=[new]), \
                 patch.object(r, "feed_items", side_effect=ValueError("blocked")), \
                 patch.object(r, "directory_items", side_effect=ValueError("blocked")), \
                 patch.object(r, "publisher_metadata", side_effect=ValueError("blocked")), \
                 patch.object(r.time, "sleep"), \
                 patch("sys.argv", ["radar", "--date", "2026-10-27", "--audit-path", str(audit)]):
                r.main()
                data = json.loads(output.read_text())
                self.assertEqual(len(data["papers"]), 1)
                self.assertEqual(data["papers"][0]["correspondingAuthors"], ["Verified Person"])
                self.assertEqual(data["papers"][0]["abstract"], "")
                self.assertFalse(json.loads(audit.read_text())["coverageComplete"])
                self.assertTrue(json.loads(audit.read_text())["pending"])
                before = output.read_bytes()
                r.main()
                self.assertEqual(output.read_bytes(), before)

if __name__ == "__main__":
    unittest.main()
