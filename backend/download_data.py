from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_ten.data import DataRequest, DataVault
from run import load_local_env


APPROVED = {
    "e0ae8898e1f56f76": DataRequest(symbol="NQ.v.0", start="2016-01-01", end="2026-01-01"),
    "a136a761bbf3d8a0": DataRequest(symbol="MNQ.v.0", start="2019-05-06", end="2026-01-01"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download only previously estimated and explicitly approved Databento requests")
    parser.add_argument("fingerprints", nargs="+", choices=sorted(APPROVED))
    args = parser.parse_args()
    load_local_env()
    vault = DataVault(Path("data"))
    for fingerprint in args.fingerprints:
        result = vault.download(APPROVED[fingerprint], fingerprint)
        print(json.dumps({"status": result["status"], "fingerprint": fingerprint, "partitions": len(result["partitions"])}), flush=True)


if __name__ == "__main__":
    main()
