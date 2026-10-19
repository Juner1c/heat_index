"""Render the React chart component using JSON records, ready for Phase 2 reuse."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

BUILD_DIRECTORY = Path(__file__).parent / "frontend" / "dist"


def chart_records(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    """Insert a null marker after hourly gaps so lines never imply missing observations."""
    data = frame[["timestamp", *columns]].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce", utc=True)
    data = data.dropna(subset=["timestamp"]).sort_values("timestamp", kind="stable")
    for column in columns:
        data[column] = pd.to_numeric(data[column], errors="coerce").replace([float("inf"), -float("inf")], float("nan"))
    rows = []
    previous = None
    for row in data.to_dict("records"):
        timestamp = row["timestamp"]
        if previous is not None and timestamp - previous > pd.Timedelta(hours=1):
            rows.append({"timestamp": (previous + pd.Timedelta(hours=1)).isoformat(), **{column: None for column in columns}})
        rows.append({"timestamp": timestamp.isoformat(), **{column: None if pd.isna(row[column]) else float(row[column]) for column in columns}})
        previous = timestamp
    return rows


def time_series_chart(frame: pd.DataFrame, columns: list[str], *, title: str, key: str) -> None:
    if not columns or frame.empty:
        st.info("No observations are available for this chart selection.")
        return
    if not (BUILD_DIRECTORY / "index.html").is_file():
        st.error("The Recharts component needs to be built before charts can be displayed.")
        st.code("cd dashboard/components/recharts/frontend\nnpm ci\nnpm run build", language="powershell")
        return
    unit = "K" if all(column.endswith("_K") for column in columns) else ""
    component = components.declare_component("thermocast_recharts", path=str(BUILD_DIRECTORY))
    component(records=chart_records(frame, columns), columns=columns, title=title, unit=unit, key=key, default=None)
