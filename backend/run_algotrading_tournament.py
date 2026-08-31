from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_ten.algotrading_tournament import run_algotrading_tournament


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen r/algotrading NQ/MNQ tournament on preserved 2018-2025 data.")
    parser.add_argument("--bootstrap-samples", type=int, default=50_000)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    result = run_algotrading_tournament(
        project_root=Path("."), data_root=Path("data"),
        bootstrap_samples=args.bootstrap_samples, write_outputs=not args.no_write,
    )
    compact = {
        "holdout": result["holdout_guard"],
        "proven_strategies": result["proven_strategies"],
        "classifications": {key: value["classification"]["label"] for key, value in result["results"].items()},
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
