
import pandas as pd
from pathlib import Path

# Input files
HIMAWARI_FILE = Path(
    "mariveles_hourly/himawari_mariveles_hourly.csv"
)
OPEN_METEO_FILE = Path("open_meteo_clean.csv")

# Output file
OUTPUT_FILE = Path("merged_weather_dataset.csv")

# Load datasets
himawari = pd.read_csv(HIMAWARI_FILE)
weather = pd.read_csv(OPEN_METEO_FILE)

# Normalize timestamps
himawari["timestamp"] = pd.to_datetime(
    himawari["timestamp"], errors="coerce"
)
weather["time"] = pd.to_datetime(
    weather["time"], errors="coerce"
)

# Remove invalid timestamps
himawari = himawari.dropna(subset=["timestamp"])
weather = weather.dropna(subset=["time"])

# Ensure one row per timestamp before merging
himawari = himawari.drop_duplicates(
    subset=["timestamp"], keep="first"
)
weather = weather.drop_duplicates(
    subset=["time"], keep="first"
)

# Merge on matching hourly timestamps
merged = pd.merge(
    himawari,
    weather,
    left_on="timestamp",
    right_on="time",
    how="inner"
)

# Remove redundant timestamp column
merged = merged.drop(columns=["time"])

# Sort chronologically
merged = merged.sort_values("timestamp").reset_index(drop=True)

# Save merged data
merged.to_csv(OUTPUT_FILE, index=False)

# Report results
print("=" * 55)
print("WEATHER DATA MERGE COMPLETE")
print("=" * 55)
print(f"Himawari rows: {len(himawari)}")
print(f"Open-Meteo rows: {len(weather)}")
print(f"Matched rows: {len(merged)}")
print(f"Columns: {len(merged.columns)}")
print(f"Missing values: {merged.isna().sum().sum()}")
print(f"Output: {OUTPUT_FILE.resolve()}")

print("\nFirst 5 rows:")
print(merged.head().to_string(index=False))

print("\nDate range:")
if not merged.empty:
    print(merged["timestamp"].min(), "to",
          merged["timestamp"].max())
else:
    print("No matching timestamps. Check timestamp formats.")