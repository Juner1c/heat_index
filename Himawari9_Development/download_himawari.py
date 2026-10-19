import requests
from pathlib import Path

# ==========================================
# HIMAWARI-9 DOWNLOADER
# ==========================================

YEAR = 2024
MONTH = 8
DAY = 15
TIME = "0430"

# Bands to download
BANDS = ["B08", "B13", "B14", "B15"]

# Himawari Full Disk has 10 segments
SEGMENTS = range(1, 11)

# Create output folder
OUTPUT = Path("downloads")
OUTPUT.mkdir(exist_ok=True)

BASE_URL = "https://noaa-himawari9.s3.amazonaws.com/AHI-L1b-FLDK"


for band in BANDS:

    print()
    print("=" * 60)
    print(f"Downloading {band}")
    print("=" * 60)

    for segment in SEGMENTS:

        filename = (
            f"HS_H09_{YEAR:04d}{MONTH:02d}{DAY:02d}_"
            f"{TIME}_{band}_FLDK_R20_S{segment:02d}10.DAT.bz2"
        )

        url = (
            f"{BASE_URL}/"
            f"{YEAR:04d}/{MONTH:02d}/{DAY:02d}/{TIME}/"
            f"{filename}"
        )

        output_file = OUTPUT / filename

        print(f"\n[{band}] Segment {segment}/10")
        print(filename)

        try:

            response = requests.get(
                url,
                stream=True,
                timeout=60
            )

            if response.status_code == 200:

                with open(output_file, "wb") as f:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):

                        if chunk:
                            f.write(chunk)

                size_mb = output_file.stat().st_size / (1024 * 1024)

                print(f"Downloaded: {size_mb:.2f} MB")

            else:

                print(
                    f"FAILED - HTTP {response.status_code}"
                )

        except Exception as e:

            print(f"ERROR: {e}")


print()
print("=" * 60)
print("DOWNLOAD COMPLETE")
print("=" * 60)