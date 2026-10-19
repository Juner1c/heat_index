import xarray as xr
from pathlib import Path

# ==========================================
# MARIVELES HIMAWARI EXTRACTION
# ==========================================

# Nearest Mariveles pixel we found
CENTER_ROW = 1974
CENTER_COL = 1701

# Extract 20 x 20 pixels
HALF_SIZE = 10

# Open NetCDF
file = next(Path("processed").glob("*.nc"))

print("Opening:")
print(file)

ds = xr.open_dataset(file)

# Calculate extraction boundaries
row_start = CENTER_ROW - HALF_SIZE
row_end = CENTER_ROW + HALF_SIZE

col_start = CENTER_COL - HALF_SIZE
col_end = CENTER_COL + HALF_SIZE

print()
print("======================================")
print("EXTRACTION AREA")
print("======================================")

print(f"Rows: {row_start} → {row_end}")
print(f"Cols: {col_start} → {col_end}")

# Extract the area
subset = ds.isel(
    y=slice(row_start, row_end),
    x=slice(col_start, col_end)
)

# Create output directory
output_dir = Path("mariveles")
output_dir.mkdir(exist_ok=True)

output_file = (
    output_dir /
    "himawari_mariveles_20240815_0430.nc"
)

# Save
subset.to_netcdf(output_file)

print()
print("======================================")
print("DONE")
print("======================================")

print(f"Saved to:")
print(output_file)

print()
print("Original dimensions:")
print(ds.sizes)

print()
print("New dimensions:")
print(subset.sizes)

ds.close()