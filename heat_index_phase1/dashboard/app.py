import os
import json
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="ThermoCast | Mariveles", page_icon="🌡️", layout="wide")
st.title("ThermoCast")
st.caption("Satellite-based heat-index monitoring and forecasting for Mariveles, Bataan")
api = os.getenv("API_URL", "http://127.0.0.1:8000")


def get(endpoint: str):
    try:
        response = requests.get(api + endpoint, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"Cannot load {endpoint}: {exc}")
        st.info("Check the API terminal and WEATHER_CSV path, then start the backend.")
        st.stop()


if st.button("Refresh data"):
    st.rerun()

station_payload = get("/api/stations")
station_names = [item["name"] for item in station_payload["stations"]]
selected_station = st.selectbox("Station / location", station_names, index=0)
station_query = f"station={quote(selected_station)}" if station_payload["station_column"] else ""
selected_details = next(item for item in station_payload["stations"] if item["name"] == selected_station)
if selected_details["latitude"] is not None and selected_details["longitude"] is not None:
    st.caption(f"Location: {selected_details['latitude']:.5f}, {selected_details['longitude']:.5f} · {selected_details['rows']:,} observations")

historical_tab, forecast_tab, alerts_tab, evaluation_tab = st.tabs(
    ["Historical data", "Forecast", "Risk alerts", "Model evaluation"]
)

with historical_tab:
    summary = get("/api/summary")
    quality = get("/api/quality")
    a, b, c, d = st.columns(4)
    a.metric("Records", f"{summary['rows']:,}")
    b.metric("Missing hours", "N/A" if summary["missing_hours"] is None else summary["missing_hours"])
    c.metric("Null cells", summary["null_cells"])
    d.metric("Duplicate timestamps", "N/A" if summary["duplicate_timestamps"] is None else summary["duplicate_timestamps"])
    st.caption(f"Source: {summary['file']}")
    st.write("**Date coverage:**", summary["start"] or "No timestamp", "→", summary["end"] or "—")
    progress = quality["download_progress"]
    if progress["configured"]:
        st.progress(progress["completion_pct"] / 100, text=f"Historical collection: {progress['completion_pct']:.1f}% ({progress['observed_hours']}/{progress['expected_hours']} hourly observations)")
    else:
        st.caption("Set COLLECTION_START and COLLECTION_END to show download completion progress.")
    if quality["issues"]:
        st.warning("Data-quality checks requiring attention: " + ", ".join(issue.replace("_", " ") for issue in quality["issues"]))
    with st.expander("Column quality details"):
        missing = pd.DataFrame([{"column": key, "missing_values": value} for key, value in quality["missing_by_column"].items()])
        st.dataframe(missing, use_container_width=True, hide_index=True)
    data = get("/api/numeric?limit=5000" + (f"&{station_query}" if station_query else ""))
    frame = pd.DataFrame(data["records"])
    if "timestamp" in frame:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        frame = frame.dropna(subset=["timestamp"]).set_index("timestamp")
    columns = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    if columns:
        selected = st.selectbox("Measurement", columns)
        st.line_chart(frame[[selected]])
    else:
        st.info("No numeric measurements were detected.")
    st.subheader("Latest records")
    st.dataframe(pd.DataFrame(get("/api/records?limit=100" + (f"&{station_query}" if station_query else ""))["records"]), use_container_width=True)
    st.subheader("Himawari-9 spectral bands")
    satellite = get("/api/satellite?limit=5000" + (f"&{station_query}" if station_query else ""))
    satellite_frame = pd.DataFrame(satellite["records"])
    if satellite["bands"]:
        chosen_bands = st.multiselect("Bands", satellite["bands"], default=satellite["bands"][:3])
        if chosen_bands:
            satellite_frame["timestamp"] = pd.to_datetime(satellite_frame["timestamp"], utc=True)
            st.line_chart(satellite_frame.set_index("timestamp")[chosen_bands])
    else:
        st.info("No recognized Himawari band columns are present in this dataset.")

with forecast_tab:
    model = get("/api/model/status")
    if not model["lnn_ready"]:
        st.warning("LNN checkpoint is not deployment-ready. Showing the persistence baseline, clearly labeled.")
    model_options = ["baseline", "lnn"] if model["lnn_ready"] else ["baseline"]
    selected_model = st.selectbox("Forecast model", model_options, index=len(model_options) - 1)
    horizon = st.slider("Forecast horizon (hours)", 1, 168, 24)
    forecast = get(f"/api/forecast?horizon={horizon}&model={selected_model}" + (f"&{station_query}" if station_query else ""))
    forecast_frame = pd.DataFrame(forecast["forecasts"])
    forecast_frame["timestamp"] = pd.to_datetime(forecast_frame["timestamp"], utc=True)
    st.caption(f"Model: {forecast['model']} · based on observation at {forecast['generated_from']}")
    st.line_chart(forecast_frame.set_index("timestamp")[["heat_index_c"]])
    st.dataframe(forecast_frame, use_container_width=True)

with alerts_tab:
    alert_model = "lnn" if get("/api/model/status")["lnn_ready"] else "baseline"
    alerts = pd.DataFrame(get(f"/api/alerts?horizon=24&model={alert_model}" + (f"&{station_query}" if station_query else ""))["alerts"])
    highest = alerts["heat_index_c"].max()
    st.metric("Highest forecast heat index", f"{highest:.1f} °C")
    st.dataframe(alerts, use_container_width=True, hide_index=True)

with evaluation_tab:
    evaluation = get("/api/evaluation" + (f"?{station_query}" if station_query else ""))
    a, b, c = st.columns(3)
    a.metric("MAE", f"{evaluation['mae_c']:.2f} °C")
    b.metric("RMSE", f"{evaluation['rmse_c']:.2f} °C")
    c.metric("Samples", evaluation["samples"])
    st.caption(f"{evaluation['model']} · {evaluation['strategy']} · {evaluation['start']} to {evaluation['end']}")
    st.info("These metrics are the baseline benchmark. LNN results must be evaluated on the same chronological holdout before deployment.")
    st.subheader("Chronological 70/15/15 split")
    st.dataframe(pd.DataFrame(evaluation["splits"]), use_container_width=True, hide_index=True)
    st.subheader("Model comparison")
    st.dataframe(pd.DataFrame(evaluation["comparisons"]), use_container_width=True, hide_index=True)
    errors = pd.DataFrame(evaluation["recent_errors"])
    if not errors.empty:
        errors["timestamp"] = pd.to_datetime(errors["timestamp"], utc=True)
        st.subheader("Recent prediction errors")
        st.line_chart(errors.set_index("timestamp")[["actual_c", "predicted_c"]])
        st.dataframe(errors, use_container_width=True, hide_index=True)
    report = get("/api/report")
    st.download_button("Download validation report (JSON)", data=json.dumps(report, indent=2), file_name="thermocast_validation_report.json", mime="application/json")
