import json

import pandas as pd

from dashboard.components.recharts import chart_records


def test_chart_preserves_missing_values_and_hourly_gaps_as_breaks():
    frame = pd.DataFrame({
        "timestamp": ["2024-08-01T03:00:00Z", "2024-08-01T00:00:00Z", "2024-08-01T04:00:00Z"],
        "B13_mean_K": [280.5, 270.0, float("inf")],
    })
    records = chart_records(frame, ["B13_mean_K"])
    assert len(records) == 4
    assert records[0]["B13_mean_K"] == 270.0
    assert records[1] == {"timestamp": "2024-08-01T01:00:00+00:00", "B13_mean_K": None}
    assert records[2]["B13_mean_K"] == 280.5
    assert records[3]["B13_mean_K"] is None
    json.dumps(records, allow_nan=False)
