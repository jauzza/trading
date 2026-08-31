import argparse
from pathlib import Path

from open_ten.phase7 import run_phase7


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the bounded Phase 7 autonomous causal research lab")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--bootstrap-samples", type=int, default=50_000)
    args = parser.parse_args()
    print(run_phase7(args.project_root, args.bootstrap_samples))
