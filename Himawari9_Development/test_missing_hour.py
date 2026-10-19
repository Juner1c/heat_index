
import requests

DATE = "2024-08-01"
TIME = "0000"

BASE_URL = "https://noaa-himawari9.s3.amazonaws.com"
BANDS = ["B08", "B13", "B14", "B15"]
SEGMENTS = range(1, 11)

available = 0
missing = 0
errors = 0

for band in BANDS:
    for segment in SEGMENTS:
        filename = (
            f"HS_H09_{DATE.replace('-', '')}_"
            f"{TIME}_{band}_FLDK_R20_S{segment:02d}10.DAT.bz2"
        )

        url = (
            f"{BASE_URL}/AHI-L1b-FLDK/"
            f"{DATE[:4]}/{DATE[5:7]}/{DATE[8:10]}/"
            f"{TIME}/{filename}"
        )

        try:
            response = requests.head(url, timeout=20)

            if response.status_code == 200:
                available += 1
            elif response.status_code == 404:
                missing += 1
                print(f"NOT FOUND: {filename}")
            else:
                errors += 1
                print(f"HTTP {response.status_code}: {filename}")

        except requests.RequestException as error:
            errors += 1
            print(f"ERROR: {filename} - {error}")

print("\n========== TEST SUMMARY ==========")
print(f"Available files: {available}")
print(f"Not found: {missing}")
print(f"Errors: {errors}")
print(f"Expected files: 40")