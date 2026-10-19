
import pandas as pd
import numpy as np
from pathlib import Path

INPUT_FILE = Path("merged_weather_dataset.csv")
OUTPUT_FILE = Path("heat_index_dataset.csv")

# Load dataset
df = pd.read_csv(INPUT_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

# Ensure required columns are numeric
df["temperature_C"] = pd.to_numeric(
    df["temperature_C"], errors="coerce"
)
df["humidity_percent"] = pd.to_numeric(
    df["humidity_percent"], errors="coerce"
)

# Remove rows without valid timestamps or required weather data
df = df.dropna(
    subset=["timestamp", "temperature_C", "humidity_percent"]
).copy()

# Sort chronologically before calculating targets
df = df.sort_values("timestamp").reset_index(drop=True)

# Convert temperature from Celsius to Fahrenheit
T = df["temperature_C"] * 9 / 5 + 32
RH = df["humidity_percent"].clip(lower=0, upper=100)

# Step 1: Calculate the preliminary Heat Index
HI_simple = 0.5 * (
    T
    + 61.0
    + ((T - 68.0) * 1.2)
    + (RH * 0.094)
)

# Average the preliminary result with air temperature
HI_simple = (HI_simple + T) / 2

# Use the preliminary Heat Index as the default
HI = HI_simple.copy()

# Step 2: Apply Rothfusz regression where preliminary HI >= 80°F
valid = HI_simple >= 80

HI_roth = (
    -42.379
    + 2.04901523 * T
    + 10.14333127 * RH
    - 0.22475541 * T * RH
    - 0.00683783 * T**2
    - 0.05481717 * RH**2
    + 0.00122874 * T**2 * RH
    + 0.00085282 * T * RH**2
    - 0.00000199 * T**2 * RH**2
)

HI = HI.where(~valid, HI_roth)

# Step 3: Low-humidity adjustment
low_humidity = (
    valid
    & (RH < 13)
    & (T >= 80)
    & (T <= 112)
)

sqrt_argument = np.maximum(
    (17 - np.abs(T - 95)) / 17,
    0
)

low_adjustment = (
    ((13 - RH) / 4)
    * np.sqrt(sqrt_argument)
).where(low_humidity, 0)

HI = HI - low_adjustment

# Step 4: High-humidity adjustment
high_humidity = (
    valid
    & (RH > 85)
    & (T >= 80)
    & (T <= 87)
)

high_adjustment = (
    ((RH - 85) / 10)
    * ((87 - T) / 5)
).where(high_humidity, 0)

HI = HI + high_adjustment

# Convert Heat Index from Fahrenheit to Celsius
df["heat_index_C"] = (HI - 32) * 5 / 9

# Create the one-hour-ahead prediction target
next_time = df["timestamp"].shift(-1)
consecutive = (
    (next_time - df["timestamp"])
    == pd.Timedelta(hours=1)
)

df["target_heat_index_1h_C"] = (
    df["heat_index_C"].shift(-1)
)

# Keep targets only when the next record is exactly one hour later
df.loc[
    ~consecutive,
    "target_heat_index_1h_C"
] = np.nan

# Save processed dataset
df.to_csv(OUTPUT_FILE, index=False)

# Display validation summary
print("HEAT INDEX PREPARATION COMPLETE")
print(f"Rows saved: {len(df)}")
print(
    "Valid one-hour-ahead targets: "
    f"{df['target_heat_index_1h_C'].notna().sum()}"
)
print(
    "Missing target values: "
    f"{df['target_heat_index_1h_C'].isna().sum()}"
)

print("\nHeat Index summary (°C):")
print(df["heat_index_C"].describe().round(2))

print("\nMissing values:")
print(
    df[[
        "temperature_C",
        "humidity_percent",
        "heat_index_C",
        "target_heat_index_1h_C"
    ]].isna().sum()
)

print(f"\nOutput: {OUTPUT_FILE.resolve()}")