import React, { useEffect, useState } from "react";
import { BrainCircuit, CalendarClock, Clock3, Thermometer, Database } from "lucide-react";
import { useData } from "../hooks/useData";
import { API_BASE } from "../services/api";
import { Panel, Stat, State, Chart, DataTable, number, timestamp } from "../components/UI";

const labels = { single_time_constant: "Single-observation time-constant RNN", sequence_time_constant: "Six-hour time-constant RNN" };

export default function ForecastingPage() {
  const status = useData("/models/status");
  const [model, setModel] = useState("sequence_time_constant");
  const [pending, setPending] = useState(false);
  const [forecast, setForecast] = useState(null);
  const [error, setError] = useState(null);
  const [historyPage, setHistoryPage] = useState(1);
  const history = useData("/forecast/history", { model, limit: 200 });
  const selected = status.data?.models?.find((entry) => entry.identifier === model);
  useEffect(() => { setForecast(null); setError(null); setHistoryPage(1); }, [model]);

  async function runForecast() {
    const requestedModel = model;
    setPending(true); setError(null); setForecast(null);
    try {
      const response = await fetch(`${API_BASE}/forecast/predict`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: requestedModel, forecast_horizon_hours: 1 }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail?.message || "Forecast prerequisites could not be verified.");
      setForecast(result);
    } catch (failure) { setError(failure.message); }
    finally { setPending(false); }
  }

  const prediction = forecast?.predictions?.[0];
  const chart = forecast ? [...forecast.observations.map((row) => ({ ...row, predicted_heat_index_c: null })), { timestamp: prediction.timestamp, actual_heat_index_c: null, predicted_heat_index_c: prediction.predicted_heat_index_c }] : [];
  const records = history.data?.records || [];
  const tableData = { columns: ["timestamp", "actual_heat_index_c", "predicted_heat_index_c", "persistence_heat_index_c"], records: records.slice((historyPage - 1) * 15, historyPage * 15), total: records.length, page: historyPage, pages: Math.max(1, Math.ceil(records.length / 15)) };

  return <>
    <div className="forecast-banner"><BrainCircuit size={34}/><span className="eyebrow">ORIGINAL CHECKPOINT INFERENCE · RESEARCH PROTOTYPE</span><h1>One hour ahead, from observed data.</h1><p>Custom time-constant RNNs reconstructed from the existing training code and saved preprocessing.</p></div>
    <Panel title="Forecast controls" subtitle="Forecasts are issued relative to the latest source observation. The current source contains historical observations, not live weather.">
      <State loading={status.loading} error={status.error}>
        <div className="forecast-controls">
          <label>Model<select aria-label="Forecast model" value={model} disabled={pending} onChange={(event) => setModel(event.target.value)}>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Trained forecast horizon<select aria-label="Forecast horizon" value="1" disabled><option value="1">1 hour</option></select></label>
          <button className="button" onClick={runForecast} disabled={pending || !selected?.inference_ready}>{pending ? "Generating forecast…" : "Generate forecast"}</button>
        </div>
        <p className="chart-caption" role="status">{selected?.message || status.data?.message}</p>
        {selected?.metadata && <p className="chart-caption">Version: {selected.metadata.version.slice(0, 12)} · {selected.metadata.sequence_length} input observation{selected.metadata.sequence_length === 1 ? "" : "s"} · CPU inference · Saved scalers</p>}
        {error && <div className="state error" role="alert">{error}</div>}
        {pending && <div className="state" role="status">Running the original checkpoint on the validated source window…</div>}
      </State>
    </Panel>
    <div className="stats-grid">
      <Stat label="Predicted heat index" value={prediction ? `${number(prediction.predicted_heat_index_c)} °C` : "—"} note="Prototype estimate · not prospectively validated" icon={Thermometer}/>
      <Stat label="Forecast timestamp" value={prediction ? timestamp(prediction.timestamp) : "—"} note="Last input observation + 1 hour" icon={CalendarClock}/>
      <Stat label="Last input observation" value={forecast ? timestamp(forecast.last_input_observation) : selected?.last_input_observation ? timestamp(selected.last_input_observation) : "—"} note="Historical source timestamp · UTC" icon={Database}/>
      <Stat label="Issue time" value={forecast ? timestamp(forecast.issued_at) : "—"} note="When this inference request was processed" icon={Clock3}/>
    </div>
    <Panel title="Forecast and recent observations" subtitle="Observed heat index and the single predicted target point · °C">
      {forecast ? <><span className="badge amber">Historical-origin forecast · research prototype</span><p className="chart-caption">Data source: {forecast.source}. {forecast.note}</p><Chart data={chart} columns={["actual_heat_index_c", "predicted_heat_index_c"]} title="Observed and predicted heat index" unit="°C"/></> : <div className="empty">Select an available model and generate a forecast to display its timestamped estimate.</div>}
    </Panel>
    <Panel title="Retrospective checkpoint verification" subtitle="Replayed original held-out results. These are historical test predictions, not forecasts collected after deployment.">
      {selected?.evaluation && <><div className="evaluation-metrics"><span>Model MAE: <strong>{number(selected.evaluation.metrics.mae_c)} °C</strong></span><span>Model RMSE: <strong>{number(selected.evaluation.metrics.rmse_c)} °C</strong></span><span>Persistence MAE: <strong>{number(selected.evaluation.persistence.mae_c)} °C</strong></span></div><p className="chart-caption">{selected.evaluation.metrics.samples} test targets · {timestamp(selected.evaluation.test_target_start)} to {timestamp(selected.evaluation.test_target_end)}. Persistence has lower error on this test period; model superiority has not been established.</p></>}
      <State {...history}>{history.data && <DataTable data={tableData} onPage={setHistoryPage}/>}</State>
    </Panel>
  </>;
}
