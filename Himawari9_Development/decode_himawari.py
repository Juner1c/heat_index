from pathlib import Path
from satpy import Scene
import glob

# ==========================================
# HIMAWARI-9 DECODER
# ==========================================

DATA_DIR = Path("downloads")

# Find all downloaded Himawari files
files = glob.glob(
    str(DATA_DIR / "*.DAT.bz2")
)

print(f"Found {len(files)} files")

if len(files) == 0:
    raise FileNotFoundError(
        "No Himawari .DAT.bz2 files found!"
    )

# ==========================================
# Load Himawari data
# ==========================================

print("Loading Himawari-9 data...")

scene = Scene(
    filenames=files,
    reader="ahi_hsd"
)

print("Available datasets:")

for dataset in scene.available_dataset_names():
    print("  ", dataset)

# ==========================================
# Load bands
# ==========================================

print("\nLoading B08, B13, B14 and B15...")

scene.load(
    ["B08", "B13", "B14", "B15"]
)

print("Bands loaded successfully!")

# ==========================================
# Save full-disk data
# ==========================================

OUTPUT_DIR = Path("processed")
OUTPUT_DIR.mkdir(exist_ok=True)

print("\nSaving data...")

scene.save_datasets(
    writer="cf",
    datasets=["B08", "B13", "B14", "B15"],
    base_dir=str(OUTPUT_DIR)
)

print("\nDONE!")
print(f"Output saved to: {OUTPUT_DIR}")