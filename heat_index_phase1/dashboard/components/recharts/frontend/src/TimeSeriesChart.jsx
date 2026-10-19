import React, { useMemo, useState } from "react";
import {
  Brush, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const colors = ["#13796e", "#dc7b35", "#347ac5", "#8a5fb5", "#bd4b63", "#648737"];
const tickTime = (value) => new Date(value).toLocaleString("en-GB", {
  day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC",
});

export function TimeSeriesChart({ records, columns, title, unit = "", dark = false, timestampMode = "utc" }) {
  const [hidden, setHidden] = useState([]);
  const rawTime = timestampMode === "raw";
  const formatTime = rawTime ? (value) => String(value) : tickTime;
  const data = useMemo(() => records.map((row) => ({ ...row, time: rawTime ? row.timestamp : Date.parse(row.timestamp) })), [records, rawTime]);
  const ink = dark ? "#d5e0dd" : "#4f6460";
  const grid = dark ? "#354943" : "#e5ede9";
  const allHidden = columns.length > 0 && columns.every((column) => hidden.includes(column));
  return (
    <section aria-label={title} className="chart-panel" style={{ color: ink, background: dark ? "#182822" : "#ffffff" }}>
      <header className="chart-header">
        <strong>{title}</strong>
        <span>{unit === "K" ? "Brightness temperature (K)" : unit ? `Observed values (${unit})` : "Observed values"} · {rawTime ? "Source timestamps · timezone unverified" : "UTC"}</span>
      </header>
      <div className="chart-container">
        {allHidden && (
          <div className="chart-empty" role="status">
            <p>All chart series are hidden.</p>
            <button type="button" onClick={() => setHidden([])}>Show all series</button>
          </div>
        )}
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={data} margin={{ top: 12, right: 24, left: 4, bottom: 12 }} accessibilityLayer>
            <CartesianGrid stroke={grid} vertical={false} />
            <XAxis dataKey="time" type={rawTime ? "category" : "number"} scale={rawTime ? "auto" : "time"} domain={rawTime ? undefined : ["dataMin", "dataMax"]}
              tickFormatter={formatTime} minTickGap={45} tick={{ fontSize: 11, fill: ink }} tickLine={false} axisLine={false} />
            <YAxis domain={["auto", "auto"]} tickFormatter={(value) => Number(value).toLocaleString("en-US", { maximumFractionDigits: 1 })}
              tick={{ fontSize: 11, fill: ink }} tickLine={false} axisLine={false} width={64} unit={unit ? ` ${unit}` : ""} />
            <Tooltip labelFormatter={(value) => rawTime ? `${value} · timezone unverified` : `${new Date(value).toISOString().replace("T", " ").slice(0, 16)} UTC`}
              formatter={(value, name) => [value == null ? "Missing" : `${Number(value).toFixed(3)}${unit ? ` ${unit}` : ""}`, name]}
              contentStyle={{ background: dark ? "#182822" : "white", border: `1px solid ${grid}`, borderRadius: 10 }} />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 14, cursor: "pointer" }}
              onClick={({ dataKey }) => setHidden((previous) => previous.includes(dataKey) ? previous.filter((key) => key !== dataKey) : [...previous, dataKey])} />
            {columns.map((column, index) => (
              <Line key={column} dataKey={column} name={column} type="linear" stroke={colors[index % colors.length]}
                strokeWidth={1.8} dot={data.filter((row) => row[column] != null && Number.isFinite(row[column])).length < 2} activeDot={{ r: 4 }} connectNulls={false} isAnimationActive={false} hide={hidden.includes(column)} />
            ))}
            {data.length > 24 && <Brush dataKey="time" tickFormatter={formatTime} height={28} stroke="#13796e" fill={dark ? "#223a31" : "#f1f7f4"} travellerWidth={8} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-note">Hover to inspect values. Click a legend label to hide a series. Gaps indicate missing observations.</p>
    </section>
  );
}
