"""Export the existing ThermoCast SQLite telemetry log to the dashboard CSV format."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Export sensor_readings from the legacy ThermoCast SQLite database.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.database.is_file():
        raise SystemExit(f"Database not found: {args.database}")
    with sqlite3.connect(args.database) as connection:
        frame = pd.read_sql_query(
            """
            SELECT timestamp, temperature, humidity, heat_index,
                   forecast_3hr_hi, pagasa_advisory
            FROM sensor_readings
            ORDER BY timestamp ASC, id ASC
            """,
            connection,
        )
    if frame.empty:
        raise SystemExit("The sensor_readings table has no rows.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    print(f"Exported {len(frame):,} telemetry rows to {args.output}")


if __name__ == "__main__":
    main()
