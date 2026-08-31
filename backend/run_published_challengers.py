from pathlib import Path
from open_ten.published_challengers import run_published_challengers


if __name__ == "__main__":
    result=run_published_challengers(Path("data"),50_000)
    print({"noise_net":result["noise_area_vwap_shadow"]["metrics"]["net_profit"],"momentum":{k:v["net_profit"] for k,v in result["intraday_momentum_shadow"]["periods"].items()},"raw_cache_immutable":result["raw_cache_immutable"]})
