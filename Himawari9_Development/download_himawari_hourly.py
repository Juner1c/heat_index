import requests
from pathlib import Path
from datetime import datetime, timedelta
import time

# =========================
# SETTINGS
# =========================

DATE = "2024-08-11"

TIMES = [
    f"{hour:02d}00"
    for hour in range(24)
]

BANDS = ["B08", "B13", "B14", "B15"]
SEGMENTS = range(1, 11)

BASE_URL = "https://noaa-himawari9.s3.amazonaws.com"
OUTPUT_DIR = Path("downloads_hourly")

MAX_RETRIES = 3
RETRY_DELAY = 3

OUTPUT_DIR.mkdir(exist_ok=True)


# =========================
# DOWNLOAD FUNCTION
# =========================

def download_file(url, output_path):

    if output_path.exists():
        print(f"SKIP: {output_path.name}")
        return True

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            print(
                f"Downloading: {output_path.name} "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )

            response = requests.get(
                url,
                timeout=(20, 60)
            )

            if response.status_code == 200:

                with open(output_path, "wb") as f:
                    f.write(response.content)

                print(f"OK: {output_path.name}")
                return True

            elif response.status_code == 404:

                print(f"NOT FOUND: {output_path.name}")
                return False

            else:

                print(
                    f"HTTP {response.status_code}: "
                    f"{output_path.name}"
                )

        except requests.exceptions.RequestException as e:

            print(f"ERROR: {e}")

        if attempt < MAX_RETRIES:
            print(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)

    print(f"FAILED: {output_path.name}")
    return False


# =========================
# MAIN
# =========================

total = len(TIMES) * len(BANDS) * len(SEGMENTS)

print("=" * 60)
print(f"Himawari-9 downloader")
print(f"Date: {DATE}")
print(f"Expected files: {total}")
print("=" * 60)

downloaded = 0
skipped = 0
failed = 0

for time_str in TIMES:

    print()
    print("=" * 60)
    print(f"Processing {DATE} {time_str} UTC")
    print("=" * 60)

    for band in BANDS:

        for segment in SEGMENTS:

            filename = (
                f"HS_H09_{DATE.replace('-', '')}_"
                f"{time_str}_{band}_FLDK_R20_S{segment:02d}10.DAT.bz2"
            )

            output_path = OUTPUT_DIR / filename

            url = (
                f"{BASE_URL}/AHI-L1b-FLDK/"
                f"{DATE[:4]}/"
                f"{DATE[5:7]}/"
                f"{DATE[8:10]}/"
                f"{time_str}/"
                f"{filename}"
            )

            if output_path.exists():
                skipped += 1
                print(f"SKIP: {filename}")
                continue

            success = download_file(url, output_path)

            if success:
                downloaded += 1
            else:
                failed += 1

print()
print("=" * 60)
print("DOWNLOAD COMPLETE")
print("=" * 60)
print(f"Downloaded : {downloaded}")
print(f"Skipped    : {skipped}")
print(f"Failed     : {failed}")
print(f"Total      : {downloaded + skipped}")
print("=" * 60)