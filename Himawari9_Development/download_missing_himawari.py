import os
import time
import requests
from datetime import datetime, timedelta

# =========================
# CONFIGURATION
# =========================

BASE_URL = "https://noaa-himawari9.s3.amazonaws.com/AHI-L1b-FLDK"
DOWNLOAD_DIR = "downloads_hourly"

START_DATE = datetime(2024, 8, 1, 0, 0)
END_DATE = datetime(2024, 8, 11, 23, 0)

BANDS = ["B08", "B13", "B14", "B15"]
SEGMENTS = range(1, 11)

MAX_RETRIES = 3
RETRY_DELAY = 3

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Himawari-Data-Recovery/1.0"})

# =========================
# DOWNLOAD FUNCTION
# =========================

def download_file(timestamp, band, segment):
    date_path = timestamp.strftime("%Y/%m/%d")
    date_text = timestamp.strftime("%Y%m%d")
    time_text = timestamp.strftime("%H%M")

    filename = (
        f"HS_H09_{date_text}_{time_text}_{band}_"
        f"FLDK_R20_S{segment:02d}10.DAT.bz2"
    )

    local_path = os.path.join(DOWNLOAD_DIR, filename)

    # Never overwrite an existing file
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return "skipped"

    url = f"{BASE_URL}/{date_path}/{time_text}/{filename}"

    for attempt in range(1, MAX_RETRIES + 1):
        temp_path = local_path + ".part"

        try:
            response = session.get(url, timeout=60, stream=True)

            if response.status_code == 404:
                response.close()
                return "not_found"

            response.raise_for_status()

            with open(temp_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file.write(chunk)

            response.close()

            if os.path.getsize(temp_path) == 0:
                os.remove(temp_path)
                raise IOError("Downloaded file is empty")

            os.replace(temp_path, local_path)
            return "downloaded"

        except Exception as error:
            if os.path.exists(temp_path):
                os.remove(temp_path)

            if attempt < MAX_RETRIES:
                print(
                    f"  Retry {attempt}/{MAX_RETRIES - 1}: "
                    f"{filename} — {error}"
                )
                time.sleep(RETRY_DELAY)
            else:
                with open("himawari_download_errors.txt", "a") as log:
                    log.write(f"{url}\t{error}\n")

    return "failed"


# =========================
# RECOVER MISSING FILES
# =========================

def main():
    timestamp = START_DATE

    total_hours = 0
    hours_with_missing_files = 0
    downloaded = 0
    skipped = 0
    not_found = 0
    failed = 0

    print("Himawari-9 Missing Data Recovery")
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Folder: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 55)

    while timestamp <= END_DATE:
        total_hours += 1
        hour_missing = 0

        for band in BANDS:
            for segment in SEGMENTS:
                date_text = timestamp.strftime("%Y%m%d")
                time_text = timestamp.strftime("%H%M")
                filename = (
                    f"HS_H09_{date_text}_{time_text}_{band}_"
                    f"FLDK_R20_S{segment:02d}10.DAT.bz2"
                )
                path = os.path.join(DOWNLOAD_DIR, filename)

                if not os.path.exists(path) or os.path.getsize(path) == 0:
                    hour_missing += 1

        if hour_missing == 0:
            skipped += 40
        else:
            hours_with_missing_files += 1
            print(
                f"\n[{timestamp:%Y-%m-%d %H:%M}] "
                f"Recovering {hour_missing} missing files..."
            )

            for band in BANDS:
                for segment in SEGMENTS:
                    result = download_file(timestamp, band, segment)

                    if result == "downloaded":
                        downloaded += 1
                    elif result == "skipped":
                        skipped += 1
                    elif result == "not_found":
                        not_found += 1
                    else:
                        failed += 1

            print(
                f"Progress: {timestamp:%Y-%m-%d %H:%M} complete"
            )

        timestamp += timedelta(hours=1)

    print("\n" + "=" * 55)
    print("RECOVERY SUMMARY")
    print(f"Hours checked: {total_hours}")
    print(f"Hours needing recovery: {hours_with_missing_files}")
    print(f"Files downloaded: {downloaded}")
    print(f"Existing files skipped: {skipped}")
    print(f"Files not found (404): {not_found}")
    print(f"Failed downloads: {failed}")
    print("Error log: himawari_download_errors.txt")
    print("=" * 55)


if __name__ == "__main__":
    main()
