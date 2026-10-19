"""Focused historical-data monitoring dashboard for ThermoCast."""

from __future__ import annotations

import os
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
from components.recharts import time_series_chart

st.set_page_config(page_title="ThermoCast | Historical Data", page_icon="TC", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f5f7f6; }
    .block-container { max-width: 1500px; padding-top: 1.5rem; }
    .hero { padding: 1.4rem 1.6rem; border-radius: 18px; color: white;
            background: linear-gradient(120deg, #123c3a, #176b63 58%, #dc7b35); margin-bottom: 1rem; }
    .hero h1 { margin: 0; font-size: 2rem; letter-spacing: -0.03em; }
    .hero p { margin: .4rem 0 0; color: #e5f4f1; }
    .status-ready { color: #136f52; font-weight: 700; }
    .status-warning { color: #a95418; font-weight: 700; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #dde6e3; padding: 1rem;
                                  border-radius: 14px; box-shadow: 0 4px 18px rgba(18,60,58,.05); }
    div[data-testid="stMetricLabel"] { color: #506663; }
    </style>
    <div class="hero">
      <h1>Historical Data Dashboard</h1>
      <p>Phase 1 · Himawari-9 dataset monitoring for Mariveles, Bataan</p>
    </div>
    """,
    unsafe_allow_html=True,
)

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


def restore_selection(key: str, values: list[str]) -> None:
    st.session_state[key] = values


def api_get(endpoint: str):
    try:
        response = requests.get(API_URL + endpoint, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        detail = str(exc)
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
        st.error(f"Cannot load the dataset: {detail}")
        st.caption("Start the backend from heat_index_phase1. It defaults to the original Himawari hourly CSV; WEATHER_CSV can override the path.")
        st.code("python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000", language="powershell")
        st.stop()


with st.sidebar:
    st.header("Dataset controls")
    # Buttons already rerun the script. An extra early rerun discards later widget state.
    st.button("Refresh dataset", width="stretch")
    stations_payload = api_get("/api/stations")
    station_names = [item["name"] for item in stations_payload["stations"]]
    if not station_names:
        st.warning("The CSV contains no named stations. Check the station column before filtering.")
        st.stop()
    selected_station = st.selectbox("Station / location", station_names)
    selected_station_info = next(item for item in stations_payload["stations"] if item["name"] == selected_station)
    station_query = f"station={quote(selected_station)}" if stations_payload["station_column"] else ""
    station_suffix = f"?{station_query}" if station_query else ""
    st.divider()
    st.caption("API connection")
    st.code(API_URL, language=None)
    if selected_station_info["latitude"] is not None and selected_station_info["longitude"] is not None:
        st.caption(f"{selected_station_info['latitude']:.5f}, {selected_station_info['longitude']:.5f}")
    st.caption("Hourly observations · All timestamps are shown in UTC.")

summary = api_get("/api/summary" + station_suffix)
quality = api_get("/api/quality" + station_suffix)
gaps = api_get("/api/gaps" + station_suffix)

status_class = "status-ready" if quality["status"] == "ready" else "status-warning"
status_label = "Ready" if quality["status"] == "ready" else "Attention required"
st.markdown(f"Dataset status: <span class='{status_class}'>{status_label}</span>", unsafe_allow_html=True)
st.caption(f"{selected_station} · {summary['start'] or 'Unknown start'} to {summary['end'] or 'Unknown end'}")
st.caption(f"{len(summary['columns'])} columns · {len([p for p in quality['column_profiles'] if 'min' in p])} numeric measurements · Original CSV is read on each refresh")

completeness = 100.0
cell_count = max(1, summary["rows"] * len(summary["columns"]))
completeness -= summary["null_cells"] / cell_count * 100

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Observations", f"{summary['rows']:,}")
m2.metric("Completeness", f"{completeness:.1f}%")
m3.metric("Missing hours", f"{gaps['missing_count']:,}")
m4.metric("Duplicate timestamps", "N/A" if summary["duplicate_timestamps"] is None else f"{summary['duplicate_timestamps']:,}")
m5.metric("Invalid timestamps", "N/A" if summary["invalid_timestamps"] is None else f"{summary['invalid_timestamps']:,}")

progress = quality["download_progress"]
if progress["configured"]:
    st.progress(progress["completion_pct"] / 100, text=f"Collection progress: {progress['completion_pct']:.1f}% — {progress['observed_hours']:,} of {progress['expected_hours']:,} expected hours")
else:
    st.caption("Missing hours are checked between the earliest and latest observations; cell completeness measures non-empty CSV cells.")

if quality["issues"]:
    readable_issues = ", ".join(issue.replace("_", " ") for issue in quality["issues"])
    st.warning(f"Quality checks found: {readable_issues}.")
else:
    st.success("All configured quality checks passed.")
if not quality["heat_index_available"]:
    st.caption("This dataset contains satellite measurements. Ground-weather temperature, humidity, and heat index are not present in the source CSV.")

trend_tab, gaps_tab, columns_tab, satellite_tab, records_tab = st.tabs(
    ["Measurement history", "Timestamp gaps", "Column quality", "Himawari bands", "Records"]
)

numeric_endpoint = "/api/numeric?limit=10000" + (f"&{station_query}" if station_query else "")
numeric_payload = api_get(numeric_endpoint)
numeric_frame = pd.DataFrame(numeric_payload["records"])
if not numeric_frame.empty and "timestamp" in numeric_frame:
    numeric_frame["timestamp"] = pd.to_datetime(numeric_frame["timestamp"], utc=True, errors="coerce")
    numeric_frame = numeric_frame.dropna(subset=["timestamp"]).sort_values("timestamp")

with trend_tab:
    measurements = [column for column in numeric_frame.columns if column != "timestamp"]
    if measurements:
        defaults = [column for column in measurements if column.endswith("_mean_K")]
        if not defaults:
            defaults = [column for column in ("temperature_c", "relative_humidity", "heat_index_c") if column in measurements]
        defaults = defaults or measurements[:1]
        selection_scope = (summary["file"], selected_station, tuple(measurements))
        if st.session_state.get("history_selection_scope") != selection_scope:
            st.session_state["history_measurements"] = defaults
            st.session_state["history_selection_scope"] = selection_scope
            st.session_state.pop("history_date_range", None)
        selected_measurements = st.multiselect("Measurements", measurements, key="history_measurements", placeholder="Select measurements to plot")
        st.button("Restore default measurements", on_click=restore_selection, args=("history_measurements", defaults), disabled=selected_measurements == defaults)
        if not selected_measurements:
            st.info("Select at least one measurement to display the chart, or restore the default measurements above.")
        if not numeric_frame.empty:
            start_date, end_date = numeric_frame["timestamp"].dt.date.min(), numeric_frame["timestamp"].dt.date.max()
            saved_dates = st.session_state.get("history_date_range")
            if saved_dates and any(value < start_date or value > end_date for value in saved_dates):
                st.session_state.pop("history_date_range", None)
            chosen_dates = st.date_input("Date range", value=(start_date, end_date), min_value=start_date, max_value=end_date, key="history_date_range")
            if len(chosen_dates) != 2:
                st.info("Choose an end date to apply the date range and display the chart.")
            else:
                filtered = numeric_frame[(numeric_frame["timestamp"].dt.date >= chosen_dates[0]) & (numeric_frame["timestamp"].dt.date <= chosen_dates[1])]
                if selected_measurements:
                    time_series_chart(filtered, selected_measurements, title="Historical numeric measurements", key="historical_measurements")
                    st.caption(f"Showing {len(filtered):,} observations in the selected period.")
    else:
        st.info("No numeric measurements are available in this dataset.")

with gaps_tab:
    left, right = st.columns(2)
    with left:
        st.subheader("Missing periods")
        periods = pd.DataFrame(gaps["gap_periods"])
        if periods.empty:
            st.success("No missing hourly periods were detected.")
        else:
            st.dataframe(periods, width="stretch", hide_index=True)
    with right:
        st.subheader("Duplicate timestamps")
        duplicates = pd.DataFrame({"timestamp": gaps["duplicate_timestamps"]})
        if duplicates.empty:
            st.success("No duplicate timestamps were detected.")
        else:
            st.dataframe(duplicates, width="stretch", hide_index=True)
    if gaps["truncated"]:
        st.warning("The displayed issue list was truncated. Use the API with a larger limit for the full list.")
    if gaps["missing_timestamps"]:
        missing_frame = pd.DataFrame({"missing_timestamp_utc": gaps["missing_timestamps"]})
        st.subheader("Exact missing timestamps")
        st.dataframe(missing_frame, width="stretch", hide_index=True)
        st.download_button("Download missing timestamps", missing_frame.to_csv(index=False).encode("utf-8"), "missing_timestamps.csv", "text/csv")
    st.caption(f"Exact duplicate rows: {summary['duplicate_rows']:,} · Invalid timestamp rows: {gaps['invalid_rows']:,}")

with columns_tab:
    profiles = pd.DataFrame(quality["column_profiles"])
    st.dataframe(
        profiles,
        width="stretch",
        hide_index=True,
        column_config={"complete_pct": st.column_config.ProgressColumn("Complete", min_value=0, max_value=100, format="%.1f%%")},
    )
    st.caption("Detected roles: " + ", ".join(f"{role} → {column}" for role, column in quality["detected_columns"].items() if column))
    if quality["range_issues"]:
        st.subheader("Out-of-range weather values")
        st.dataframe(pd.DataFrame(quality["range_issues"]), width="stretch", hide_index=True)

with satellite_tab:
    satellite_endpoint = "/api/satellite?limit=10000" + (f"&{station_query}" if station_query else "")
    satellite = api_get(satellite_endpoint)
    bands = satellite["bands"]
    if bands:
        band_frame = pd.DataFrame(satellite["records"])
        band_frame["timestamp"] = pd.to_datetime(band_frame["timestamp"], utc=True, errors="coerce")
        default_bands = [column for column in bands if column.endswith("_mean_K")] or bands[: min(3, len(bands))]
        band_scope = (summary["file"], selected_station, tuple(bands))
        if st.session_state.get("band_selection_scope") != band_scope:
            st.session_state["spectral_bands"] = default_bands
            st.session_state["band_selection_scope"] = band_scope
        selected_bands = st.multiselect("Spectral bands", bands, key="spectral_bands", placeholder="Select spectral bands to plot")
        st.button("Restore default bands", on_click=restore_selection, args=("spectral_bands", default_bands), disabled=selected_bands == default_bands)
        if selected_bands:
            time_series_chart(band_frame, selected_bands, title="Himawari-9 brightness temperatures", key="himawari_bands")
        else:
            st.info("Select at least one spectral band to display the chart, or restore the default bands above.")
        st.caption("Columns ending in _K are satellite brightness temperatures in Kelvin.")
    else:
        st.info("No recognized Himawari-9 band columns were found.")

with records_tab:
    preview_limit = st.selectbox("Preview rows", [25, 100, 500, 1000], index=1)
    records_endpoint = f"/api/records?limit={preview_limit}" + (f"&{station_query}" if station_query else "")
    records = pd.DataFrame(api_get(records_endpoint)["records"])
    st.dataframe(records, width="stretch", hide_index=True)
    st.download_button("Download displayed records", records.to_csv(index=False).encode("utf-8"), f"{selected_station.lower().replace(' ', '_')}_historical_records.csv", "text/csv")

st.caption(f"Source: {summary['file']}")
