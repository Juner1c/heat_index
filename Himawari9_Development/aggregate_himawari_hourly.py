import pandas as pd
from pathlib import Path


# ============================================================
# FILE PATHS
# ============================================================

INPUT_FILE = Path(
    "mariveles_batch/himawari_mariveles_features.csv"
)

OUTPUT_FILE = Path(
    "mariveles_batch/himawari_hourly_features.csv"
)


# ============================================================
# LOAD HIMAWARI DATA
# ============================================================

print("Loading Himawari data...")

df = pd.read_csv(INPUT_FILE)

print(f"Rows loaded: {len(df)}")


# ============================================================
# CONVERT TIMESTAMP
# ============================================================

df["timestamp"] = pd.to_datetime(
    df["timestamp"]
)


# ============================================================
# SET TIMESTAMP AS INDEX
# ============================================================

df = df.set_index("timestamp")


# ============================================================
# NUMERIC COLUMNS
# ============================================================

feature_columns = [
    "B08_mean_K",
    "B08_min_K",
    "B08_max_K",

    "B13_mean_K",
    "B13_min_K",
    "B13_max_K",

    "B14_mean_K",
    "B14_min_K",
    "B14_max_K",

    "B15_mean_K",
    "B15_min_K",
    "B15_max_K",
]


# ============================================================
# HOURLY AGGREGATION
# ============================================================

print("Aggregating to hourly data...")

hourly = df[feature_columns].resample("1h").agg({
    "B08_mean_K": "mean",
    "B08_min_K": "min",
    "B08_max_K": "max",

    "B13_mean_K": "mean",
    "B13_min_K": "min",
    "B13_max_K": "max",

    "B14_mean_K": "mean",
    "B14_min_K": "min",
    "B14_max_K": "max",

    "B15_mean_K": "mean",
    "B15_min_K": "min",
    "B15_max_K": "max",
})


# ============================================================
# RESET INDEX
# ============================================================

hourly = hourly.reset_index()


# ============================================================
# SAVE
# ============================================================

hourly.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# DISPLAY RESULTS
# ============================================================

print()
print("=" * 60)
print("HOURLY AGGREGATION COMPLETE")
print("=" * 60)

print(f"Rows: {len(hourly)}")
print(f"Columns: {len(hourly.columns)}")

print()
print(hourly)


print()
print(f"Saved to:")
print(OUTPUT_FILE)