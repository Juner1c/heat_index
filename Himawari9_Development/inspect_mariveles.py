import xarray as xr
from pathlib import Path

file = next(Path("mariveles").glob("*.nc"))

ds = xr.open_dataset(file)

print("\n=== Mariveles Himawari-9 Data ===\n")

for band in ["B08", "B13", "B14", "B15"]:
    if band in ds:
        data = ds[band]

        print(f"{band}")
        print(f"  Shape: {data.shape}")
        print(f"  Dimensions: {data.dims}")
        print(f"  Minimum: {float(data.min())}")
        print(f"  Maximum: {float(data.max())}")
        print(f"  Mean: {float(data.mean())}")
        print(f"  Units: {data.attrs.get('units', 'Not specified')}")
        print()

ds.close()