
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

FILES = [
    BASE_DIR / "mariveles_hourly" / "himawari_mariveles_hourly.csv",
    BASE_DIR / "open_meteo_clean.csv",
    BASE_DIR / "merged_weather_dataset.csv",
    BASE_DIR / "heat_index_dataset.csv",
]

for file_path in FILES:
    print("\n" + "=" * 70)
    print(file_path.name)
    print("=" * 70)

    if not file_path.exists():
        print("FILE NOT FOUND")
        continue

    df = pd.read_csv(file_path)
    print("Rows:", len(df))
    print("Columns:", list(df.columns))

    time_column = next(
        (
            col for col in ["timestamp", "time", "datetime"]
            if col in df.columns
        ),
        None,
    )

    if time_column is None:
        print("No recognized timestamp column.")
        continue

    timestamps = pd.to_datetime(df[time_column], errors="coerce")
    timestamps = timestamps.dropna().sort_values()

    if timestamps.empty:
        print("No valid timestamps.")
        continue

    print("First:", timestamps.min())
    print("Last: ", timestamps.max())
    print("Unique timestamps:", timestamps.nunique())

    # Inspect the specific period containing the large gaps.
    period = timestamps[
        (timestamps >= "2024-08-01")
        & (timestamps < "2024-08-05")
    ]

    print("Records from Aug 1 through Aug 4:", len(period))
    print("First 30 timestamps in that period:")
    print(period.drop_duplicates().head(30).to_string(index=False))

    unique_times = pd.DatetimeIndex(period.unique()).sort_values()
    if len(unique_times) > 1:
        gaps = unique_times.to_series().diff().dropna()
        print("Largest gap in this period:")
        print(gaps.sort_values(ascending=False).head(5).to_string())