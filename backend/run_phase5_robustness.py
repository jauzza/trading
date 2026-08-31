from pathlib import Path

from open_ten.phase5_robustness import run_c01_robustness


if __name__ == "__main__":
    result = run_c01_robustness(Path("data"))
    center = result["parameter_surface"]["ema_200:volume_1.0"]
    print({"surface_runs": len(result["parameter_surface"]), "center_net": center["net_profit"],
           "roll_included_net": result["roll_sensitivity"]["include_roll_sessions"]["net_profit"],
           "raw_cache_immutable": result["raw_cache_immutable"]})
