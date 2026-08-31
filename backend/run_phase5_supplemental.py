from pathlib import Path

from open_ten.phase5_supplemental import build_supplemental


if __name__ == "__main__":
    result = build_supplemental(Path("data"))
    c01 = result["run_audits"]["NQ:C01:matched_4R:fixed1"]
    print({"runs": len(result["run_audits"]), "c01_exposure": c01["exposure_fraction_nominal_rth"], "walk_forward": result["expanding_walk_forward"]})
