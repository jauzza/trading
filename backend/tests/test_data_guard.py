import tempfile
import unittest
from pathlib import Path

from open_ten.data import DataRequest, DataVault


class DataGuardTests(unittest.TestCase):
    def test_download_requires_matching_estimate_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=DataVault(Path(tmp)); request=DataRequest()
            with self.assertRaises(PermissionError): vault.download(request,None)
            with self.assertRaises(PermissionError): vault.download(request,"wrong")

    def test_fingerprint_is_reproducible(self):
        self.assertEqual(DataRequest().fingerprint,DataRequest().fingerprint)
        self.assertNotEqual(DataRequest().fingerprint,DataRequest(symbol="MNQ.v.0").fingerprint)


if __name__=="__main__": unittest.main()
