import os
from pathlib import Path

import uvicorn


def load_local_env() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

if __name__ == "__main__":
    load_local_env()
    uvicorn.run("open_ten.api:app", host="127.0.0.1", port=8000)
