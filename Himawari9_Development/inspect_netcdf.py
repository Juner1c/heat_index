import xarray as xr
from pathlib import Path

file = next(Path("processed").glob("*.nc"))

print("Opening:")
print(file)
print()

ds = xr.open_dataset(file)

print("======================================")
print("DATASET INFORMATION")
print("======================================")

print(ds)

print()
print("======================================")
print("DIMENSIONS")
print("======================================")

for name, size in ds.sizes.items():
    print(f"{name}: {size}")

print()
print("======================================")
print("VARIABLES")
print("======================================")

for name, variable in ds.variables.items():

    print(f"\n{name}")
    print("  dimensions:", variable.dims)
    print("  shape:", variable.shape)

    if "units" in variable.attrs:
        print("  units:", variable.attrs["units"])

    if "long_name" in variable.attrs:
        print("  description:", variable.attrs["long_name"])

ds.close()