from pathlib import Path
import xarray as xr
from satpy import Scene
import pandas as pd
import numpy as np


# ============================================================
# SETTINGS
# ============================================================

DOWNLOAD_DIR = Path("downloads")
OUTPUT_DIR = Path("mariveles_batch")

OUTPUT_DIR.mkdir(exist_ok=True)


# Himawari bands
BANDS = [
    "B08",
    "B13",
    "B14",
    "B15",
]


# Mariveles crop coordinates
CENTER_ROW = 1974
CENTER_COL = 1701

HALF_SIZE = 10

ROW_START = CENTER_ROW - HALF_SIZE
ROW_END = CENTER_ROW + HALF_SIZE

COL_START = CENTER_COL - HALF_SIZE
COL_END = CENTER_COL + HALF_SIZE


# ============================================================
# FIND HIMAWARI FILES
# ============================================================

files = sorted(
    DOWNLOAD_DIR.glob("*.DAT.bz2")
)

print(f"Total files found: {len(files)}")


# ============================================================
# GROUP FILES BY TIMESTAMP
# ============================================================

groups = {}

for file in files:

    name = file.name

    # Example:
    # HS_H09_20240815_0430_B13_FLDK_R20_S0110.DAT.bz2

    parts = name.split("_")

    date = parts[2]
    time = parts[3]

    timestamp = f"{date}_{time}"

    if timestamp not in groups:
        groups[timestamp] = []

    groups[timestamp].append(str(file))


print()
print(f"Total timestamps found: {len(groups)}")


# ============================================================
# FEATURE STORAGE
# ============================================================

results = []


# ============================================================
# PROCESS EACH TIMESTAMP
# ============================================================

for timestamp in sorted(groups):

    print()
    print("=" * 70)
    print(f"Processing: {timestamp}")
    print("=" * 70)

    timestamp_files = groups[timestamp]

    print(f"Files: {len(timestamp_files)}")

    try:

        # ----------------------------------------------------
        # Create Satpy Scene
        # ----------------------------------------------------

        scene = Scene(
            filenames=timestamp_files,
            reader="ahi_hsd"
        )


        # ----------------------------------------------------
        # Load bands
        # ----------------------------------------------------

        print("Loading bands...")

        scene.load(BANDS)


        # ----------------------------------------------------
        # Convert to NetCDF temporarily
        # ----------------------------------------------------

        temp_dir = OUTPUT_DIR / "temp"

        temp_dir.mkdir(exist_ok=True)

        scene.save_datasets(
            writer="cf",
            datasets=BANDS,
            base_dir=temp_dir
        )


        # ----------------------------------------------------
        # Find generated NetCDF
        # ----------------------------------------------------

        nc_files = list(temp_dir.glob("*.nc"))

        if not nc_files:

            print("ERROR: No NetCDF file generated.")
            continue


        nc_file = nc_files[-1]

        print(f"Opening: {nc_file.name}")


        # ----------------------------------------------------
        # Open NetCDF
        # ----------------------------------------------------

        ds = xr.open_dataset(nc_file)


        # ----------------------------------------------------
        # Crop Mariveles
        # ----------------------------------------------------

        print(
            f"Cropping rows {ROW_START}:{ROW_END}, "
            f"columns {COL_START}:{COL_END}"
        )


        cropped = ds.isel(
            y=slice(ROW_START, ROW_END),
            x=slice(COL_START, COL_END)
        )


        # ----------------------------------------------------
        # Calculate statistics
        # ----------------------------------------------------

        row = {
            "timestamp": timestamp
        }


        for band in BANDS:

            if band not in cropped:

                print(
                    f"WARNING: {band} not found."
                )

                continue


            data = cropped[band].values


            # Remove invalid values
            valid = data[
                np.isfinite(data)
            ]


            if len(valid) == 0:

                print(
                    f"WARNING: No valid values for {band}"
                )

                continue


            row[f"{band}_mean_K"] = float(
                np.mean(valid)
            )

            row[f"{band}_min_K"] = float(
                np.min(valid)
            )

            row[f"{band}_max_K"] = float(
                np.max(valid)
            )


        results.append(row)


        # ----------------------------------------------------
        # Save cropped dataset
        # ----------------------------------------------------

        output_nc = (
            OUTPUT_DIR /
            f"himawari_mariveles_{timestamp}.nc"
        )


        cropped.to_netcdf(
            output_nc
        )


        print(
            f"Saved: {output_nc.name}"
        )


        # ----------------------------------------------------
        # Close dataset
        # ----------------------------------------------------

        ds.close()


        # ----------------------------------------------------
        # Remove temporary NetCDF files
        # ----------------------------------------------------

        for temp_file in temp_dir.glob("*.nc"):

            try:
                temp_file.unlink()
            except:
                pass


    except Exception as error:

        print()
        print(
            f"ERROR processing {timestamp}:"
        )

        print(error)

        continue


# ============================================================
# SAVE FEATURE CSV
# ============================================================

if results:

    df = pd.DataFrame(results)

    output_csv = (
        OUTPUT_DIR /
        "himawari_mariveles_features.csv"
    )

    df.to_csv(
        output_csv,
        index=False
    )


    print()
    print("=" * 70)
    print("PROCESSING COMPLETE")
    print("=" * 70)

    print(
        f"Timestamps processed: {len(df)}"
    )

    print(
        f"Feature file: {output_csv}"
    )

    print()
    print(df)


else:

    print()
    print("No results were generated.")