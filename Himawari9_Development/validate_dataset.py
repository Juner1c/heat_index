
import pandas as pd
from pathlib import Path

file_path = Path("merged_weather_dataset.csv")

df = pd.read_csv(file_path)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

print("=" * 55)
print("DATASET VALIDATION")
print("=" * 55)

print(f"Rows: {len(df)}")
print(f"Columns: {len(df.columns)}")
print(f"Duplicate timestamps: {df['timestamp'].duplicated().sum()}")
print(f"Missing values: {df.isna().sum().sum()}")
print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

print("\nColumn data types:")
print(df.dtypes.to_string())

print("\nWeather feature summary:")
print(df.describe().round(2).to_string())

print("\nHourly timestamp gaps:")
time_diff = df["timestamp"].sort_values().diff()
print(time_diff.value_counts().head(10).to_string())

print("\nValidation complete.")