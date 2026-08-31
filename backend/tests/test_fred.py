import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from open_ten.fred import download_vix, fred_status


class FredTests(unittest.TestCase):
    @patch("open_ten.fred.urlopen")
    def test_vix_cache_uses_server_key_and_discards_missing_values(self, open_url: Mock) -> None:
        payload = {"observations": [
            {"date": "2025-01-02", "value": "17.93"},
            {"date": "2025-01-03", "value": "."},
        ]}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        open_url.return_value = response
        with patch("open_ten.fred.json.load", return_value=payload):
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"FRED_API_KEY": "test-only"}):
                root = Path(directory)
                result = download_vix(root)
                self.assertEqual(result["observations"], 1)
                self.assertEqual(fred_status(root)["start"], "2025-01-02")
                self.assertIn("series_id=VIXCLS", open_url.call_args.args[0])
                self.assertNotIn("test-only", (root / "fred" / "vixcls.json").read_text())


if __name__ == "__main__":
    unittest.main()
