import xarray as xr
import pandas as pd
from pathlib import Path

# Find the Mariveles NetCDF
file = next(Path("mariveles").glob("*.nc"))

ds = xr.open_dataset(file)

bands = ["B08", "B13", "B14", "B15"]

data = {}

for band in bands:
    if band in ds:
        data[f"{band}_mean_K"] = float(ds[band].mean())
        data[f"{band}_min_K"] = float(ds[band].min())
        data[f"{band}_max_K"] = float(ds[band].max())

# Observation time
data["timestamp"] = ds["B13"].attrs.get("start_time")

ds.close()

# Create table
df = pd.DataFrame([data])

# Put timestamp first
columns = ["timestamp"] + [
    col for col in df.columns if col != "timestamp"
]

df = df[columns]

# Save
output = Path("mariveles") / "himawari_features.csv"
df.to_csv(output, index=False)

print("\nHimawari features:")
print(df.to_string(index=False))

print(f"\nSaved to: {output}")