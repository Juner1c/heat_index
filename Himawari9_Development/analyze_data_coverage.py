
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "heat_index_dataset.csv"
OUTPUT_DIR = BASE_DIR / "data_coverage_results"

OUTPUT_DIR.mkdir(exist_ok=True)

if not DATA_FILE.exists():
    raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

df = pd.read_csv(DATA_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
df = df.drop_duplicates(subset=["timestamp"], keep="first")

# Create the full hourly timeline between the first and last records.
start = df["timestamp"].min().floor("h")
end = df["timestamp"].max().floor("h")
expected = pd.date_range(start=start, end=end, freq="h")

observed = pd.DatetimeIndex(df["timestamp"])
missing_hours = expected.difference(observed)

# Count observations and missing hours by calendar day.
observed_counts = (
    df.assign(date=df["timestamp"].dt.date)
    .groupby("date")
    .size()
)

missing_df = pd.DataFrame({"missing_timestamp": missing_hours})
missing_df["date"] = missing_df["missing_timestamp"].dt.date
missing_counts = missing_df.groupby("date").size()

daily = pd.DataFrame(index=pd.Index(expected.date, name="date"))
daily = daily[~daily.index.duplicated()]
daily["expected_hours"] = 24
daily["observed_hours"] = observed_counts
daily["missing_hours"] = missing_counts
daily = daily.fillna(0).astype(int)
daily["coverage_percent"] = (
    daily["observed_hours"] / daily["expected_hours"] * 100
).round(2)

# Calculate gaps between consecutive observations.
df["gap_hours"] = (
    df["timestamp"].diff().dt.total_seconds() / 3600
)

gaps = df.loc[
    df["gap_hours"] > 1,
    ["timestamp", "gap_hours"]
].copy()

gaps["missing_hours_between_records"] = (
    gaps["gap_hours"] - 1
).astype(int)

# Check how many records have valid one-hour-ahead targets.
if "target_heat_index_1h_C" in df.columns:
    target_valid = df["target_heat_index_1h_C"].notna().sum()
    target_missing = df["target_heat_index_1h_C"].isna().sum()
else:
    target_valid = None
    target_missing = None

# Save reports.
daily.to_csv(OUTPUT_DIR / "daily_coverage.csv")
missing_df.to_csv(OUTPUT_DIR / "missing_hours.csv", index=False)
gaps.to_csv(OUTPUT_DIR / "time_gaps.csv", index=False)

print("\n========== DATA COVERAGE ==========")
print(f"First timestamp: {df['timestamp'].min()}")
print(f"Last timestamp:  {df['timestamp'].max()}")
print(f"Unique observations: {len(df)}")
print(f"Expected hourly timestamps: {len(expected)}")
print(f"Missing hours: {len(missing_hours)}")

coverage = (
    (len(expected) - len(missing_hours)) / len(expected) * 100
    if len(expected) else 0
)
print(f"Overall hourly coverage: {coverage:.2f}%")

print("\n========== DAILY COVERAGE ==========")
print(daily.to_string())

print("\n========== LARGEST TIME GAPS ==========")
if gaps.empty:
    print("No gaps larger than one hour.")
else:
    print(
        gaps.sort_values("gap_hours", ascending=False)
        .head(15)
        .to_string(index=False)
    )

if target_valid is not None:
    print("\n========== FORECAST TARGET ==========")
    print(f"Valid one-hour targets: {target_valid}")
    print(f"Missing targets: {target_missing}")

print("\nReports saved in:")
print(OUTPUT_DIR)