import unittest
from unittest.mock import patch
from urllib.error import URLError

from app import fetch_job_description


class FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


class FakeResponse:
    headers = FakeHeaders()

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class JobDescriptionUrlTests(unittest.TestCase):
    def test_public_html_extracts_text_and_ignores_script_content(self):
        body = (
            "<html><script>leaked fake requirements</script><h1>Operations Analyst</h1>"
            "<p>Build management dashboards and lead cross-functional business programs. "
            "Analyze trends, communicate insights, and improve processes.</p></html>"
        ).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=FakeResponse(body)) as urlopen:
            text = fetch_job_description("https://example.invalid/careers/operations")
        self.assertIn("Operations Analyst", text)
        self.assertIn("Build management dashboards", text)
        self.assertNotIn("fake requirements", text)
        urlopen.assert_called_once()

    def test_network_failure_is_propagated_for_ui_handling(self):
        with patch("urllib.request.urlopen", side_effect=URLError("blocked")):
            with self.assertRaises(URLError):
                fetch_job_description("https://example.invalid/careers/operations")

    def test_too_short_page_is_rejected(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(b"<h1>Careers</h1>")):
            with self.assertRaises(ValueError):
                fetch_job_description("https://example.invalid/careers")


if __name__ == "__main__":
    unittest.main()