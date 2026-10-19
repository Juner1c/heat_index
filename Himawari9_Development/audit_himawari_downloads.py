
from pathlib import Path
from collections import Counter
import re
import pandas as pd

RAW_DIR = Path("downloads_hourly")

if not RAW_DIR.exists():
    raise FileNotFoundError(f"Folder not found: {RAW_DIR.resolve()}")

pattern = re.compile(
    r"HS_H09_(\d{8})_(\d{4})_(B08|B13|B14|B15)_FLDK_R20_S(\d{2})10\.DAT\.bz2$"
)

files = list(RAW_DIR.glob("*.DAT.bz2"))
groups = {}
unrecognized = []

for path in files:
    match = pattern.search(path.name)

    if not match:
        unrecognized.append(path.name)
        continue

    date, time, band, segment = match.groups()
    timestamp = f"{date}_{time}"

    groups.setdefault(timestamp, []).append((band, int(segment)))

print("=" * 70)
print("HIMAWARI RAW DOWNLOAD AUDIT")
print("=" * 70)
print(f"Raw files found: {len(files)}")
print(f"Recognized files: {len(files) - len(unrecognized)}")
print(f"Unrecognized files: {len(unrecognized)}")
print(f"Unique timestamps: {len(groups)}")

expected_bands = {"B08", "B13", "B14", "B15"}
expected_segments = set(range(1, 11))

rows = []

for timestamp, entries in sorted(groups.items()):
    present = set(entries)
    missing = []

    for band in sorted(expected_bands):
        for segment in sorted(expected_segments):
            if (band, segment) not in present:
                missing.append(f"{band}_S{segment:02d}")

    rows.append({
        "timestamp": timestamp,
        "file_count": len(entries),
        "missing_file_count": len(missing),
        "missing_examples": ", ".join(missing[:8]),
    })

report = pd.DataFrame(rows)

if not report.empty:
    print("\n========== FILES PER TIMESTAMP ==========")
    print(report["file_count"].value_counts().sort_index().to_string())

    print("\n========== INCOMPLETE TIMESTAMPS ==========")
    incomplete = report[report["missing_file_count"] > 0]

    if incomplete.empty:
        print("All recognized timestamps have the expected 40 files.")
    else:
        print(incomplete.to_string(index=False))

    # Check the expected hourly timeline from August 1 to August 11.
    expected = pd.date_range(
        "2024-08-01 00:00",
        "2024-08-11 23:00",
        freq="h"
    )

    actual = pd.to_datetime(
        report["timestamp"],
        format="%Y%m%d_%H%M",
        errors="coerce"
    ).dropna()

    missing_hours = expected.difference(pd.DatetimeIndex(actual))

    print("\n========== MISSING HOURLY TIMESTAMPS ==========")
    print(f"Expected hours: {len(expected)}")
    print(f"Hours with at least one raw file: {len(actual.unique())}")
    print(f"Hours with no recognized raw files: {len(missing_hours)}")
    print(missing_hours.to_series().to_string(index=False))

    report.to_csv("himawari_raw_audit.csv", index=False)
    print("\nDetailed report saved: himawari_raw_audit.csv")

if unrecognized:
    print("\nFirst unrecognized filenames:")
    print("\n".join(unrecognized[:10]))