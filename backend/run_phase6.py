from __future__ import annotations

import argparse
from pathlib import Path

from open_ten.phase6 import run_phase6


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the bounded Phase 6 causal C01 audit and discovery research")
    parser.add_argument("--bootstrap-samples", type=int, default=50_000)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("phase6"))
    arguments = parser.parse_args()
    result = run_phase6(arguments.data_root, arguments.output, arguments.bootstrap_samples)
    print({"corrected_net": result["corrected"]["net_profit"], "trades": result["corrected"]["trades"],
           "registry": result["registry"], "holdout_candidates": result["holdout_candidates"],
           "raw_cache_immutable": result["raw_cache_immutable"]})
