import React, { useState } from "react";
import { AlertCircle, Download, LoaderCircle, CalendarDays } from "lucide-react";
import { download } from "../services/api";
import { TimeSeriesChart } from "../../../dashboard/components/recharts/frontend/src/TimeSeriesChart.jsx";

export const number = (value) => value == null ? "—" : Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
export const timestamp = (value) => value ? new Date(value).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC" : "Unavailable";
export function Panel({ title, subtitle, action, children, className = "" }) { return <section className={`panel ${className}`}><div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>; }
export function Stat({ label, value, note, icon: Icon }) { return <div className="stat-card"><span className="stat-icon">{Icon && <Icon size={20}/>}</span><span className="eyebrow">{label}</span><strong>{value}</strong><span className="stat-note">{note}</span></div>; }
export function State({ loading, error, children }) { if (loading) return <div className="state" role="status"><LoaderCircle className="animate-spin"/>Loading source data…</div>; if (error) return <div className="state error" role="alert"><AlertCircle/><div><h3>Data unavailable</h3><p>{error}</p><small>Use Refresh data to retry after the source is available.</small></div></div>; return children; }
export function Empty({ children }) { return <div className="empty" role="status">{children}</div>; }
export function Export({ path, params, label = "Export CSV" }) {
  const [error, setError] = useState(null); const [busy, setBusy] = useState(false);
  return <div><button className="button secondary" disabled={busy} onClick={async () => { setBusy(true); setError(null); try { await download(path, params); } catch (e) { setError(e.message); } finally { setBusy(false); } }}><Download size={15}/>{busy ? "Preparing…" : label}</button>{error && <p className="error-text" role="alert">{error}</p>}</div>;
}
export function Dates({ onApply }) { const [start, setStart] = useState(""); const [end, setEnd] = useState(""); const invalid = start && end && start > end;
  return <form className="filters" onSubmit={(e) => { e.preventDefault(); if (!invalid) onApply({ start, end }); }}><CalendarDays size={17}/><label>From<input type="date" aria-label="From date" value={start} onChange={(e) => setStart(e.target.value)}/></label><label>Through<input type="date" aria-label="Through date" value={end} onChange={(e) => setEnd(e.target.value)}/></label><button className="button" disabled={Boolean(invalid)}>Apply range</button><button type="button" className="button secondary" onClick={() => { setStart(""); setEnd(""); onApply({}); }}>All dates</button>{invalid && <span role="alert" className="error-text">Start date must precede end date.</span>}</form>;
}
export function Chart({ data, columns, title, unit = "K", aggregation }) {
  if (!data?.length || !columns?.length) return <Empty>No observations match this selection.</Empty>;
  return <><TimeSeriesChart key={JSON.stringify([columns, data[0]?.timestamp, data.at(-1)?.timestamp, data.length])} records={data} columns={columns} title={title} unit={unit}/>{aggregation && aggregation !== "observed" && <p className="chart-caption">{aggregation} Chart rendering is bounded for responsiveness.</p>}</>;
}
export function DataTable({ data, onPage }) { if (!data) return null; return <><div className="table-scroll"><table><thead><tr>{data.columns.map((column) => <th key={column}>{column === "timestamp" ? "Observation · UTC" : column}</th>)}</tr></thead><tbody>{data.records.map((row, index) => <tr key={`${row.timestamp}-${index}`}>{data.columns.map((column) => <td key={column}>{column === "timestamp" ? timestamp(row[column]) : number(row[column])}</td>)}</tr>)}</tbody></table>{!data.records.length && <Empty>No rows in the selected date range.</Empty>}</div><div className="pagination"><span>{number(data.total)} records · Page {data.page} of {data.pages}</span><div><button className="button secondary" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</button><button className="button secondary" disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)}>Next</button></div></div></>; }
