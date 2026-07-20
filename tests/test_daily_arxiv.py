import datetime
import unittest
from unittest.mock import MagicMock, patch

import daily_arxiv


class FakeResult:
    def __init__(self, paper_id):
        self._paper_id = paper_id
        self.title = "Test Paper"
        self.summary = "summary"
        self.authors = ["Author A", "Author B"]
        self.updated = datetime.datetime(2026, 7, 16)

    def get_short_id(self):
        return self._paper_id


class TestGetDailyPapers(unittest.TestCase):
    @patch("daily_arxiv.get_code_link", return_value=None)
    def test_uses_search_results_when_available(self, _):
        fake_search = MagicMock()
        fake_search.results.return_value = [FakeResult("1234.5678")]

        with patch("daily_arxiv.arxiv.Search", return_value=fake_search):
            data, _ = daily_arxiv.get_daily_papers("topic", query="q", max_results=1)

        self.assertIn("1234.5678", data["topic"])

    @patch("daily_arxiv.get_code_link", return_value=None)
    def test_falls_back_to_client_results_when_search_has_no_results(self, _):
        fake_search = object()
        fake_client = MagicMock()
        fake_client.results.return_value = [FakeResult("2345.6789")]

        with patch("daily_arxiv.arxiv.Search", return_value=fake_search), patch("daily_arxiv.arxiv.Client", return_value=fake_client):
            data, _ = daily_arxiv.get_daily_papers("topic", query="q", max_results=1)

        fake_client.results.assert_called_once_with(fake_search)
        self.assertIn("2345.6789", data["topic"])


if __name__ == "__main__":
    unittest.main()
