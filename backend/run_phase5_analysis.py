from pathlib import Path
from open_ten.phase5_analysis import analyze


if __name__ == "__main__":
    result = analyze(Path("data"), 50_000)
    chosen = result["proposed_filter"]
    print({"strategy": result["strategy"], "sessions": result["sessions"], "proposed_filter": chosen["plain_english_rule"] if chosen else None})
