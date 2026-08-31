from __future__ import annotations

from run import load_local_env
from open_ten.phase4_audit import run_phase4_audit


if __name__ == "__main__":
    load_local_env()
    result = run_phase4_audit()
    print(result["inspection_status"])
