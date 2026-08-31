from __future__ import annotations

from run import load_local_env
from open_ten.opening_research import run_opening_research


if __name__ == "__main__":
    load_local_env()
    result = run_opening_research()
    print(result["plain_language_conclusion"])
