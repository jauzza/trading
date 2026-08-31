from pathlib import Path

from dotenv import load_dotenv

from open_ten.fred import download_vix


if __name__ == "__main__":
    load_dotenv()
    print(download_vix(Path("data")))
