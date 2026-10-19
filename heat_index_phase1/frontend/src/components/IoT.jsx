import React, { useState } from "react";
import { Radio, Thermometer, Droplets, Activity, Download } from "lucide-react";
import { useIoT, IOT_REFRESH_MS } from "../hooks/useIoT";
import { Panel, Stat, State, Empty, number, timestamp } from "./UI";
import { TimeSeriesChart } from "../../../dashboard/components/recharts/frontend/src/TimeSeriesChart.jsx";

function SensorConnection({ latest }) {
  const freshness = latest?.measurement?.freshness || "unknown";
  return <div className="iot-connection"><span className={`badge ${latest?.server_reachable ? "" : "amber"}`}>Server {latest?.server_reachable ? "reachable" : "unavailable"}</span><span className={`badge ${freshness === "fresh" ? "" : "amber"}`}>Sensor freshness: {freshness}</span></div>;
}

function MeasurementTime({ reading }) {
  const quality = {time_only:"time only; date and timezone unknown", timezone_unverified:"timezone unverified", invalid:"invalid source timestamp", missing:"timestamp unavailable"};
  return <>{reading?.measurement_timestamp_utc ? timestamp(reading.measurement_timestamp_utc) : reading?.timestamp_raw ? `${reading.timestamp_raw} · ${quality[reading.timestamp_quality] || "timestamp unverified"}` : "Measurement timestamp unavailable"}</>;
}

function SensorNotes({ latest }) {
  return <div className="iot-notes"><p><strong>Measurement time: </strong><MeasurementTime reading={latest?.measurement}/></p><p>Server checked: {timestamp(latest?.checked_at_utc)}{latest?.cache_age_seconds > 0 ? ` · cached ${number(latest.cache_age_seconds)}s` : ""}. This is not the measurement time.</p><p>Automatic refresh: {number(IOT_REFRESH_MS / 1000)} seconds after each completed request. Server connectivity does not establish sensor freshness.</p></div>;
}

function ReadingCards({ reading }) {
  return <div className="stats-grid iot-stats"><Stat label="Latest reported temperature" value={reading?.temperature_c == null ? "—" : `${number(reading.temperature_c)} °C`} icon={Thermometer} note="IoT sensor air temperature"/><Stat label="Latest reported humidity" value={reading?.humidity_percent == null ? "—" : `${number(reading.humidity_percent)}%`} icon={Droplets} note="Relative humidity"/><Stat label="Sensor-derived heat index" value={reading?.heat_index_c == null ? "—" : `${number(reading.heat_index_c)} °C`} icon={Activity} note="Calculated/reported by the IoT server"/></div>;
}

export function IoTCharts({ history }) {
  const records = history?.records || [];
  if (!records.length) return <Empty>No sensor history is available.</Empty>;
  const verified = records.every((row) => row.measurement_timestamp_utc);
  const ordered = verified ? [...records].sort((a,b) => a.measurement_timestamp_utc.localeCompare(b.measurement_timestamp_utc)) : [...records].reverse();
  const chart = ordered.map((row, index) => ({ ...row, timestamp: verified ? row.measurement_timestamp_utc : row.timestamp_raw || `Returned row ${index + 1} · time unavailable` }));
  return <div className="iot-charts" data-testid="iot-charts"><p className="chart-caption">{verified ? "Verified offset-bearing timestamps · UTC." : "Reversed upstream record order. Source timestamps are unverified; spacing is categorical, not elapsed time. No date or timezone is inferred."}</p><TimeSeriesChart records={chart} columns={["temperature_c", "heat_index_c"]} title="IoT temperature and heat-index history" unit="°C" timestampMode={verified ? "utc" : "raw"}/><TimeSeriesChart records={chart} columns={["humidity_percent"]} title="IoT relative-humidity history" unit="%" timestampMode={verified ? "utc" : "raw"}/></div>;
}

export function LiveIoT({ charts = false }) {
  const state = useIoT({ history: charts });
  const reading = state.latest?.measurement;
  return <Panel className="iot-panel" title="Live IoT Weather" subtitle="Data source: IoT Weather Sensor · Separate from satellite and Open-Meteo history" action={<SensorConnection latest={state.latest}/>}><State loading={state.loading} error={state.error}>{state.latest && <><ReadingCards reading={reading}/>{state.latest.status === "unavailable" || state.latest.status === "no_data" ? <p className="iot-warning" role="status">{state.latest.message || "No usable sensor measurements are available. No readings have been fabricated."}</p> : null}{state.latest.status === "partial" && <p className="iot-warning">Some reported measurements failed validation; invalid values are not displayed.</p>}<SensorNotes latest={state.latest}/>{reading?.advisory && <div className="iot-advisory"><strong>Upstream advisory — not independently verified: {reading.advisory}</strong>{reading.action && <p>{reading.action}</p>}</div>}{charts && <><IoTCharts history={state.history}/>{state.history?.status === "unavailable" && <p className="iot-warning">History unavailable: {state.history.message}</p>}{reading?.experimental_forecast_c != null && <p className="iot-warning"><strong>Experimental IoT forecast — unvalidated:</strong> {number(reading.experimental_forecast_c)} °C. The claimed three-hour horizon is unverified. This is separate from ThermoCast’s one-hour research models.</p>}</>}</>}</State></Panel>;
}

export function IoTQuality() {
  const state = useIoT({ history: true });
  const history = state.history;
  return <Panel className="iot-panel" title="IoT data quality" subtitle="Bounded sensor window; not a count of the complete upstream database" action={<SensorConnection latest={state.latest}/>}><State loading={state.loading} error={state.error}>{state.latest && <><div className="stats-grid iot-stats"><Stat label="Returned history records" value={history?.returned_count ?? "—"} icon={Radio} note="Up to 100 requested records"/><Stat label="Missing / invalid readings" value={history?.invalid_readings ?? "—"} icon={Activity} note={`${history?.invalid_fields ?? "—"} invalid/missing fields in returned history`}/><Stat label="Unverified history timestamps" value={history?.unverified_timestamps ?? "—"} icon={Radio} note="No UTC conversion without an offset"/></div><SensorNotes latest={state.latest}/><p className="iot-warning">Latest response: {state.latest.status}. History response: {history?.status || "unavailable"}. Latest invalid/missing fields: {state.latest.invalid_fields}. Duplicate source timestamp strings in this history window: {history?.duplicate_timestamps ?? "—"}.</p><p className="chart-caption">No expected sensor sampling cadence is configured, so missing time intervals cannot be quantified. A time-of-day or timezone-naive SQLite timestamp cannot establish age. The upstream model/horizon and advisory are unvalidated.</p>{state.latest.message && <p className="iot-warning">{state.latest.message}</p>}{history?.message && <p className="iot-warning">{history.message}</p>}</>}</State></Panel>;
}

function exportSensorRows(records) {
  const columns = ["timestamp_raw", "measurement_timestamp_utc", "timestamp_quality", "temperature_c", "humidity_percent", "heat_index_c", "advisory"];
  const escape = (value) => {
    let text = value == null ? "" : String(value);
    if (typeof value !== "number" && /^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [columns.join(","), ...records.map((row) => columns.map((column) => escape(row[column])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url; link.download = "iot_sensor_history.csv"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function IoTHistory() {
  const state = useIoT({ history: true });
  const [page, setPage] = useState(1);
  const records = state.history?.records || [];
  const pages = Math.max(1, Math.ceil(records.length/25)), current = Math.min(page, pages);
  return <Panel className="iot-panel" title="IoT sensor historical readings" subtitle="Original source timestamps are retained; no unverified UTC assumption" action={<button className="button secondary" disabled={!records.length} onClick={() => exportSensorRows(records)}><Download size={15}/>Export sensor CSV</button>}><State loading={state.loading} error={state.error}>{state.latest && <><SensorConnection latest={state.latest}/><SensorNotes latest={state.latest}/>{state.history?.message && <p className="iot-warning">{state.history.message}</p>}<div className="table-scroll"><table><thead><tr><th>Measurement timestamp · source</th><th>Timestamp quality</th><th>Temperature °C</th><th>Humidity %</th><th>Heat index °C</th><th>Upstream advisory</th></tr></thead><tbody>{records.slice((current-1)*25,current*25).map((row,index) => <tr key={`${row.id}-${index}`}><td>{row.timestamp_raw || "Unavailable"}</td><td>{row.timestamp_quality.replaceAll("_", " ")}</td><td>{number(row.temperature_c)}</td><td>{number(row.humidity_percent)}</td><td>{number(row.heat_index_c)}</td><td>{row.advisory || "Unavailable"}</td></tr>)}</tbody></table></div>{!records.length && <Empty>No sensor historical readings are available.</Empty>}<div className="pagination"><span>{records.length} returned records · Page {current} of {pages}</span><div><button className="button secondary" disabled={current <= 1} onClick={() => setPage(current-1)}>Previous</button><button className="button secondary" disabled={current >= pages} onClick={() => setPage(current+1)}>Next</button></div></div></>}</State></Panel>;
}
