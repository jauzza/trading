from pathlib import Path
import argparse

from open_ten.phase5 import run_phase5


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the frozen Phase 5 strategy tournament")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--bootstrap-samples", type=int, default=50_000)
    args = parser.parse_args()
    result = run_phase5(Path("data"), smoke=args.smoke, bootstrap_samples=args.bootstrap_samples)
    print({"smoke": result["smoke"], "accepted_sessions": result["accepted_sessions"], "runs": len(result["summaries"]), "holdout": result["holdout_guard"]})
