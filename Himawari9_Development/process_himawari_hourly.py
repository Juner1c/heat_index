from pathlib import Path
import re
import pandas as pd
import numpy as np
import xarray as xr
from satpy import Scene


# ============================================================
# SETTINGS
# ============================================================

INPUT_DIR = Path("downloads_hourly")

OUTPUT_DIR = Path("mariveles_hourly")

OUTPUT_DIR.mkdir(exist_ok=True)


# Himawari bands
BANDS = [
    "B08",
    "B13",
    "B14",
    "B15",
]


# ============================================================
# MARIVELES CROP
# ============================================================

CENTER_ROW = 1974
CENTER_COL = 1701

HALF_SIZE = 10

ROW_START = CENTER_ROW - HALF_SIZE
ROW_END = CENTER_ROW + HALF_SIZE

COL_START = CENTER_COL - HALF_SIZE
COL_END = CENTER_COL + HALF_SIZE


# ============================================================
# FIND FILES
# ============================================================

files = sorted(
    INPUT_DIR.glob("*.DAT.bz2")
)

print("=" * 70)
print("HIMAWARI-9 HOURLY PROCESSOR")
print("=" * 70)

print(
    f"Raw files found: {len(files)}"
)


# ============================================================
# GROUP FILES BY DATE + TIME
# ============================================================

groups = {}


for file in files:

    filename = file.name

    match = re.search(
        r"H09_(\d{8})_(\d{4})_",
        filename
    )

    if not match:

        print(
            f"Skipping unrecognized file: "
            f"{filename}"
        )

        continue


    date = match.group(1)
    time = match.group(2)

    timestamp = f"{date}_{time}"


    if timestamp not in groups:

        groups[timestamp] = []


    groups[timestamp].append(
        str(file)
    )


print(
    f"Unique timestamps found: "
    f"{len(groups)}"
)


# ============================================================
# RESULTS
# ============================================================

results = []


# ============================================================
# PROCESS EACH TIMESTAMP
# ============================================================

for index, timestamp in enumerate(
    sorted(groups),
    start=1
):

    print()
    print("=" * 70)

    print(
        f"[{index}/{len(groups)}] "
        f"Processing {timestamp}"
    )

    print("=" * 70)


    timestamp_files = groups[timestamp]


    print(
        f"Files for timestamp: "
        f"{len(timestamp_files)}"
    )


    # --------------------------------------------------------
    # Check expected number of files
    # --------------------------------------------------------

    if len(timestamp_files) != 40:

        print(
            "WARNING: Expected 40 files "
            f"but found {len(timestamp_files)}"
        )


    try:

        # ====================================================
        # CREATE SATPY SCENE
        # ====================================================

        scene = Scene(
            filenames=timestamp_files,
            reader="ahi_hsd"
        )


        # ====================================================
        # LOAD BANDS
        # ====================================================

        print(
            "Loading B08, B13, B14, B15..."
        )

        scene.load(BANDS)


        # ====================================================
        # EXTRACT FEATURES DIRECTLY
        # ====================================================

        row = {
            "timestamp": (
                pd.to_datetime(
                    timestamp,
                    format="%Y%m%d_%H%M"
                )
            )
        }


        for band in BANDS:

            print(
                f"Processing {band}..."
            )


            # ------------------------------------------------
            # Get band data
            # ------------------------------------------------

            data_array = scene[band]


            # ------------------------------------------------
            # Convert to NumPy
            # ------------------------------------------------

            data = data_array.values


            # ------------------------------------------------
            # Crop Mariveles
            # ------------------------------------------------

            cropped = data[
                ROW_START:ROW_END,
                COL_START:COL_END
            ]


            # ------------------------------------------------
            # Remove invalid values
            # ------------------------------------------------

            valid = cropped[
                np.isfinite(cropped)
            ]


            if len(valid) == 0:

                print(
                    f"WARNING: "
                    f"No valid values for {band}"
                )

                row[
                    f"{band}_mean_K"
                ] = np.nan

                row[
                    f"{band}_min_K"
                ] = np.nan

                row[
                    f"{band}_max_K"
                ] = np.nan

                continue


            # ------------------------------------------------
            # Calculate statistics
            # ------------------------------------------------

            row[
                f"{band}_mean_K"
            ] = float(
                np.mean(valid)
            )


            row[
                f"{band}_min_K"
            ] = float(
                np.min(valid)
            )


            row[
                f"{band}_max_K"
            ] = float(
                np.max(valid)
            )


        # ====================================================
        # ADD RESULT
        # ====================================================

        results.append(row)


        print(
            "SUCCESS"
        )


    except Exception as error:

        print()
        print(
            f"ERROR processing {timestamp}"
        )

        print(
            str(error)
        )

        print(
            "Skipping this timestamp..."
        )

        continue


# ============================================================
# CREATE DATAFRAME
# ============================================================

if len(results) == 0:

    print()
    print(
        "ERROR: No timestamps were processed."
    )

    raise SystemExit


df = pd.DataFrame(
    results
)


# ============================================================
# SORT BY TIME
# ============================================================

df = df.sort_values(
    "timestamp"
)


# ============================================================
# SAVE CSV
# ============================================================

OUTPUT_FILE = (
    OUTPUT_DIR /
    "himawari_mariveles_hourly.csv"
)


df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("PROCESSING COMPLETE")
print("=" * 70)

print(
    f"Successful timestamps: "
    f"{len(df)}"
)

print(
    f"Columns: "
    f"{len(df.columns)}"
)

print()
print(
    f"Output file:"
)

print(
    OUTPUT_FILE.resolve()
)


# ============================================================
# CHECK MISSING VALUES
# ============================================================

print()
print("Missing values:")

print(
    df.isna().sum()
)


# ============================================================
# SHOW DATA
# ============================================================

print()
print("Processed dataset:")

print(
    df.to_string(
        index=False
    )
)