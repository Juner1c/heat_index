from pathlib import Path
import xarray as xr
import pandas as pd
from satpy import Scene

DOWNLOAD_DIR = Path("downloads")
OUTPUT_DIR = Path("mariveles_batch")

OUTPUT_DIR.mkdir(exist_ok=True)

BANDS = ["B08", "B13", "B14", "B15"]

# Mariveles pixel location
CENTER_ROW = 1974
CENTER_COL = 1701
HALF_SIZE = 10

ROW_START = CENTER_ROW - HALF_SIZE
ROW_END = CENTER_ROW + HALF_SIZE

COL_START = CENTER_COL - HALF_SIZE
COL_END = CENTER_COL + HALF_SIZE


# Find timestamps
timestamps = sorted({
    file.name.split("_")[2] + "_" + file.name.split("_")[3]
    for file in DOWNLOAD_DIR.glob("*.DAT.bz2")
})

print("Timestamps found:")

for timestamp in timestamps:
    print(" ", timestamp)


all_features = []


for timestamp in timestamps:

    date_part, time_part = timestamp.split("_")

    print(f"\n=== Processing {date_part} {time_part} UTC ===")

    pattern = f"HS_H09_{date_part}_{time_part}_*.DAT.bz2"

    files = list(DOWNLOAD_DIR.glob(pattern))

    print(f"Files found: {len(files)}")

    if len(files) < 40:
        print("WARNING: Expected 40 files.")
        continue

    # Load Himawari
    scene = Scene(
        filenames=[str(f) for f in files],
        reader="ahi_hsd"
    )

    print("Loading bands...")

    scene.load(BANDS)

    # Save temporary full-disk NetCDF
    temp_file = OUTPUT_DIR / f"himawari_{date_part}_{time_part}.nc"

    scene.save_datasets(
        writer="cf",
        datasets=BANDS,
        filename=str(temp_file)
    )

    print("Opening NetCDF...")

    ds = xr.open_dataset(temp_file)

    # Crop to Mariveles
    cropped = ds.isel(
        y=slice(ROW_START, ROW_END),
        x=slice(COL_START, COL_END)
    )

    print(
        f"Mariveles crop: "
        f"rows {ROW_START}:{ROW_END}, "
        f"columns {COL_START}:{COL_END}"
    )

    features = {
        "timestamp": (
            f"{date_part[:4]}-"
            f"{date_part[4:6]}-"
            f"{date_part[6:8]} "
            f"{time_part[:2]}:"
            f"{time_part[2:]}:00"
        )
    }

    for band in BANDS:

        data = cropped[band]

        # Remove invalid values
        valid = data.where(data.notnull())

        features[f"{band}_mean_K"] = float(valid.mean())
        features[f"{band}_min_K"] = float(valid.min())
        features[f"{band}_max_K"] = float(valid.max())

    cropped.close()
    ds.close()

    all_features.append(features)

    print("Features extracted.")


# Create dataframe
df = pd.DataFrame(all_features)

df = df.sort_values("timestamp")

output_csv = OUTPUT_DIR / "himawari_mariveles_features.csv"

df.to_csv(output_csv, index=False)


print("\n======================================")
print("FINAL MARIVELES HIMAWARI DATASET")
print("======================================")

print(df.to_string(index=False))

print(f"\nSaved to:")
print(output_csv)