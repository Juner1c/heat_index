import React, { useState } from "react";
import { Overview as SatelliteOverview, Historical as SatelliteHistory, Weather as HistoricalWeather, Quality as SatelliteQuality } from "./Dashboard";
import { LiveIoT, IoTHistory, IoTQuality } from "../components/IoT";
import { Panel } from "../components/UI";

export function Overview() { return <><SatelliteOverview/><LiveIoT/></>; }
export function Weather({ heatIndex = false }) { return <><LiveIoT charts={!heatIndex}/><HistoricalWeather heatIndex={heatIndex}/></>; }
export function Quality() { return <><IoTQuality/><SatelliteQuality/></>; }
export function Historical() {
  const [source, setSource] = useState("satellite");
  return <><Panel title="Historical data sources" subtitle="Sources remain separate; sensor timezone quality is preserved"><label className="iot-source-select">Data source<select aria-label="Historical data source" value={source} onChange={(event) => setSource(event.target.value)}><option value="satellite">Himawari-9 satellite</option><option value="weather">Open-Meteo historical weather</option><option value="iot">IoT Weather Sensor</option></select></label></Panel>{source === "iot" ? <IoTHistory/> : source === "weather" ? <HistoricalWeather/> : <SatelliteHistory/>}</>;
}
