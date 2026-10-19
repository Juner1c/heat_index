import React, { useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib";
import { TimeSeriesChart } from "./TimeSeriesChart";
import "./style.css";

function StreamlitChart({ args, theme }) {
  const container = useRef(null);
  useEffect(() => {
    let lastHeight = 0;
    const observer = new ResizeObserver(() => {
      const height = Math.ceil(container.current?.getBoundingClientRect().height ?? 0);
      if (height > 0 && height !== lastHeight) {
        lastHeight = height;
        Streamlit.setFrameHeight(height + 2);
      }
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const records = args.records ?? [];
  const columns = args.columns ?? [];
  const filterKey = JSON.stringify([columns, records[0]?.timestamp, records.at(-1)?.timestamp, records.length]);
  return <div ref={container}><TimeSeriesChart key={filterKey} records={records} columns={columns} title={args.title ?? "Historical measurements"}
    unit={args.unit ?? ""} dark={theme?.base === "dark"} /></div>;
}

const ConnectedChart = withStreamlitConnection(StreamlitChart);
createRoot(document.getElementById("root")).render(<ConnectedChart />);
