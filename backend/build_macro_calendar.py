from open_ten.macro_calendar import build_calendar, validate_calendar


if __name__ == "__main__":
    payload = build_calendar()
    validate_calendar(payload)
    print({"events": len(payload["events"]), "coverage": payload["coverage"], "paid_data": payload["paid_data"]})
