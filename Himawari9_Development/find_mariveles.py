import xarray as xr
import numpy as np
from pathlib import Path

# ==========================================
# FIND MARIVELES PIXEL
# ==========================================

# Approximate center of Mariveles, Bataan
TARGET_LAT = 14.43
TARGET_LON = 120.49

# Open the NetCDF
file = next(Path("processed").glob("*.nc"))

print("Opening:")
print(file)
print()

ds = xr.open_dataset(file)

# Get latitude and longitude arrays
lat = ds["latitude"].values
lon = ds["longitude"].values

print("Finding nearest Himawari pixel...")
print(f"Target latitude : {TARGET_LAT}")
print(f"Target longitude: {TARGET_LON}")

# Calculate distance in degrees
distance = (
    (lat - TARGET_LAT) ** 2
    + (lon - TARGET_LON) ** 2
)

# Find nearest pixel
index = np.unravel_index(
    np.nanargmin(distance),
    distance.shape
)

row, col = index

nearest_lat = lat[row, col]
nearest_lon = lon[row, col]

print()
print("======================================")
print("NEAREST HIMAWARI PIXEL")
print("======================================")

print(f"Row              : {row}")
print(f"Column           : {col}")
print(f"Latitude         : {nearest_lat}")
print(f"Longitude        : {nearest_lon}")

distance_km = (
    np.sqrt(distance[row, col]) * 111
)

print(f"Approx. distance : {distance_km:.3f} km")

ds.close()