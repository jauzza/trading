from __future__ import annotations

from run import load_local_env
from open_ten.research import run_research


if __name__ == "__main__":
    load_local_env()
    result=run_research()
    print(f"Research complete: {result['conclusion']}")
    print(f"Accepted sessions: {result['accepted_sessions']}")
    print(f"Credible candidates: {result['credible_candidates']}")
