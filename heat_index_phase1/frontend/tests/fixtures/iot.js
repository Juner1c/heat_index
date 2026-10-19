// Synthetic UI fixtures only. They are never imported into application code.
export const measurement = { temperature_c:31.2, humidity_percent:62, heat_index_c:37.4,
  timestamp_raw:"12:34:56", measurement_timestamp_utc:null, timestamp_quality:"time_only", freshness:"unknown", age_seconds:null,
  advisory:"MOCK ADVISORY", action:"Mock upstream advisory text", experimental_forecast_c:38.8,
  forecast_label:"Experimental IoT forecast — unvalidated", forecast_horizon_verified:false, issues:[] };
export const latest = { source:"IoT Weather Sensor", provider:"render_flask", status:"available", server_reachable:true,
  checked_at_utc:"2026-10-14T07:00:00Z", cache_age_seconds:0, measurement, invalid_fields:0, invalid_readings:0, unverified_timestamps:1 };
export const history = { source:"IoT Weather Sensor", status:"available", server_reachable:true, checked_at_utc:latest.checked_at_utc,
  requested_limit:100, returned_count:3, invalid_fields:0, invalid_readings:0, duplicate_timestamps:0, unverified_timestamps:3,
  records:[0,1,2].map((offset) => ({...measurement,id:3-offset, timestamp_raw:`2024-01-01 12:3${4-offset}:56`, timestamp_quality:"timezone_unverified"})) };
export const unavailable = { source:"IoT Weather Sensor", provider:"render_flask", status:"unavailable", server_reachable:false,
  checked_at_utc:latest.checked_at_utc, cache_age_seconds:0, measurement:null, records:[], returned_count:0,
  invalid_fields:0, invalid_readings:0, duplicate_timestamps:0, unverified_timestamps:0, message:"IoT server is unavailable; no readings were generated." };
export async function mockIoT(page, latestResponse=latest, historyResponse=history) {
  await page.route("**/api/iot/**", (route) => route.fulfill({ contentType:"application/json",
    body:JSON.stringify(route.request().url().includes("/history") ? historyResponse : latestResponse) }));
}
