# Live IoT sensor integration — October 14, 2026

## Status and separation

The existing React dashboard now reads the existing Flask Render API through a server-side FastAPI adapter. The sidebar, layout, historical satellite/Open-Meteo sources, original forecasting routes, and Phase 4 research package remain in place. No Flask deployment, SQLite database, ESP32 upload route, historical dataset, or trained model checkpoint was modified.

The frontend calls only the local `/api/iot/*` contract. It does not connect directly to Render and receives no private credentials. No new model is promoted and sensor measurements are not automatically inserted into Phase 3/4 model inputs.

## Files created

- `backend/schemas/iot.py`: validated upstream and normalized measurement/response schemas.
- `backend/services/iot.py`: `SensorProvider` interface, read-only `RenderSensorProvider`, validation, timestamp/freshness checks, bounded single-flight cache, explicit unavailable states.
- `backend/routers/iot.py`: three IoT endpoints.
- `frontend/src/hooks/useIoT.js`: bounded configurable polling with request deadlines, complete-batch settlement, abort/unmount cleanup, and manual-refresh integration.
- `frontend/src/components/IoT.jsx`: sensor cards, advisory labeling, history charts/table/CSV export, connection/freshness indicators, quality section.
- `frontend/src/pages/ConnectedDashboard.jsx`: wrappers that add IoT content without rewriting the existing historical pages.
- `tests/test_iot.py`, `frontend/tests/iot.spec.js`, `frontend/tests/fixtures/iot.js`: mocked automated integration/regression coverage.
- This integration report.

## Files modified

- `backend/main.py`: registers the IoT router; existing model/data routes are unchanged.
- `frontend/src/App.jsx`: uses the connected wrappers for the same existing routes.
- `frontend/src/style.css`: scoped responsive IoT styles.
- `dashboard/components/recharts/frontend/src/TimeSeriesChart.jsx`: optional raw categorical timestamp mode; default verified historical UTC behavior is unchanged.
- `frontend/tests/dashboard.spec.js`: mocks external IoT responses so existing regressions remain deterministic.
- `.env.example`, `frontend/.env.example`, `compose.yaml`: configuration examples/pass-through.
- `requirements-dashboard.txt`: declares the already-installed Requests dependency.
- `README.md`: links this guide.

Rebuilt generated React and shared Recharts bundles reflect the source changes. No dependency installation or frontend re-creation was required.

## Backend API

| Endpoint | Behavior |
| --- | --- |
| `GET /api/iot/latest` | Normalized latest values, source timestamp quality, freshness, server reachability, validation issues |
| `GET /api/iot/history?limit=100` | Bounded history; accepted limit 1–200; record-level quality and returned-window counts |
| `GET /api/iot/status` | Latest/history availability, server reachability, latest sensor freshness, nested quality details |

State endpoints return HTTP 200 with `status` equal to `available`, `partial`, `no_data`, or `unavailable`. HTTP 200 indicates the ThermoCast state endpoint worked, **not** that the upstream sensor is fresh. Invalid query limits return HTTP 422. Upstream failures produce structured `error_code`/`message`, no fabricated values, and no stale-success fallback.

Mappings:

| Latest Flask field | History Flask field | ThermoCast field |
| --- | --- | --- |
| `temperature` | `temperature_c` | `temperature_c` |
| `humidity` | `humidity_pct` | `humidity_percent` |
| `current_hi` | `heat_index_c` | `heat_index_c` |
| `forecast_hi` | `forecast_3hr_c` | `experimental_forecast_c` |
| `timestamp` | `timestamp` | `timestamp_raw` |
| `cur_category` | `pagasa_advisory` | `advisory` |
| `cur_action` | Not provided | `action` |
| `status` | Not provided | `upstream_status` |

Numerical strings and supported °C/% suffixes are converted to numbers. Boolean/object/array numeric fields fail schema validation; non-finite or invalid numeric strings become unavailable fields. Humidity outside 0–100% and air temperature outside the broad −90–60°C screening range are rejected. A reported heat index is not displayed as valid if its accompanying temperature/humidity is invalid. Missing values are never filled with zero.

Heat index is explicitly the IoT server's calculated/reported value, not a new independent calibration or formula validation. Latest values are rounded upstream more coarsely than history, so their displayed precision may differ. Upstream advisory/action text is displayed as unverified source text, not newly validated ThermoCast safety guidance.

History counts describe only the bounded returned window, not the full SQLite database. Invalid/schema-rejected readings, missing/invalid fields, duplicate source timestamp strings, and unverified timestamps are reported. Without a verified sampling cadence, missing time intervals cannot be counted reliably.

## Time handling and freshness

- The verified latest payload contains a time-of-day such as `07:52:12`. Its date and timezone are unknown. `measurement_timestamp_utc` is null and freshness remains `unknown`.
- The verified history payload contains SQLite-style strings such as `2026-10-14 07:52:12`, without timezone offsets. They are preserved verbatim, marked `timezone_unverified`, and never silently interpreted as UTC or Philippine time.
- Only complete timestamps with explicit offsets can become normalized UTC measurement times. `offset_verified` means a syntactically valid explicit offset was present, not independent verification of the device clock.
- For such timestamps, freshness is `fresh`, `stale`, or `future`; default stale threshold is 120 seconds and timestamps more than 30 seconds ahead are flagged future. Invalid/unrepresentable dates remain unknown rather than crashing the endpoint.
- `checked_at_utc` records the server request/check time. It is displayed separately and never substituted for measurement time. Cached responses retain their original check time and report cache age; trustworthy timestamp age is recomputed when served from cache.
- Server reachability is independent of freshness. An HTTP error or malformed payload can confirm reachability while sensor data remain unavailable.
- Latest and history are separate upstream snapshots. No date is inferred for latest by matching its time-of-day to a history row.

Unverified chart timestamps use the existing Recharts component in **categorical raw mode**. It does not call `Date.parse` on those strings or label them UTC. The chart reverses the returned upstream row order for display and explicitly says its spacing is not elapsed time. When every timestamp has a valid explicit offset, the component can use its normal UTC timeline. Missing numeric values break lines; no sensor/weather series are spliced together.

## React pages

- Overview: appended Live IoT Weather section; existing historical satellite statistics remain intact.
- Weather Monitoring: separate sensor cards, upstream advisory, temperature/heat-index chart, humidity chart, connection/freshness information, and automatic refresh; Open-Meteo history remains below.
- Heat Index Analysis: separate current reported sensor values/advisory above the existing historical heat-index analysis; no merged cross-source series.
- Historical Data: selector for Himawari-9, Open-Meteo, or IoT; IoT has a bounded paginated table and `iot_sensor_history.csv` export. CSV preserves raw/verified timestamps separately and escapes untrusted formula-like text.
- Data Quality: separate IoT reachability, returned history count, invalid/missing readings, timestamp warnings, and sensor freshness, plus the original satellite quality sections.
- AI Forecasting: unchanged; no IoT forecast is substituted into either research workflow.

The upstream value advertised as a three-hour forecast is labeled **“Experimental IoT forecast — unvalidated”** wherever shown. Its horizon/model/adjustment methodology was not independently validated and it remains separate from the original one-hour models.

## Configuration and startup

From `ThermoCast\heat_index_phase1` in Windows PowerShell:

```powershell
# Activate your existing environment if applicable:
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dashboard.txt
$env:IOT_RENDER_BASE_URL = 'https://thermocast-ai-2.onrender.com'
$env:IOT_CONNECT_TIMEOUT_SECONDS = '3'
$env:IOT_READ_TIMEOUT_SECONDS = '8'
$env:IOT_CACHE_SECONDS = '5'
$env:IOT_FRESHNESS_SECONDS = '120'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Use `requirements-inference.txt` in an environment that also needs original-model inference. The development workspace already had these dependencies. The `.env.example` files document settings; Uvicorn does not automatically load a copied `.env` without an explicit loader, so set PowerShell environment variables as above. Compose passes the documented server-side settings through its environment configuration.

In another terminal:

```powershell
Set-Location frontend
$env:VITE_IOT_REFRESH_MS = '10000'
npm run dev
```

Frontend interval is bounded to 1–300 seconds, default ten. Polling waits until **both latest/history requests settle**, then schedules the next interval. A 30-second browser deadline, abort on unmount/configuration/manual refresh, and timer cleanup prevent overlapping cycles and abandoned client requests. Only pages displaying IoT content poll.

Server defaults: connection timeout three seconds; read timeout eight seconds; cache TTL five seconds. Cache is per-process, bounded to eight response keys, includes failures, and coalesces concurrent requests. Upstream JSON bodies are capped at 1 MiB, history at 200 records, and redirects are not followed. Configure a trusted base URL server-side; browser/API clients cannot supply upstream URLs or credentials.

## Read-only live verification

At **2026-10-14 07:52:20 UTC**, the local FastAPI adapter successfully contacted Render and returned:

- Temperature: **30.5°C**.
- Humidity: **29%**.
- Reported heat index: **29.2°C**.
- Raw latest source time: **07:52:12**, date/timezone unverified.
- Server: reachable. Sensor freshness: unknown.
- Returned history example: `2026-10-14 07:52:12`, 30.5°C, 29%, heat index 29.15°C; timezone unverified.

These are a verification snapshot, not hardcoded UI values or a freshness assertion. The live Weather Monitoring page rendered cards and both sensor charts without page errors. Original satellite summary still returned 262 rows, and model status still listed only the two original custom time-constant models. The Flask service and ESP32 endpoints received only read-only GET requests; nothing was deployed remotely.

## Tests

```powershell
python -m pytest -q -k 'not training_pipeline'
python -m compileall -q backend dashboard scripts research
Set-Location frontend
npm run build
npm test
Set-Location ..\dashboard\components\recharts\frontend
npm run build
npm run test:browser
```

Automated IoT checks use mocked provider/HTTP/browser responses only. Actual Render calls were confined to read-only manual integration checks. The older Phase 1 synthetic model-training test remains intentionally excluded; no original model was retrained.

Coverage includes valid latest/history schemas, formatted numerical strings, missing/invalid values, humidity bounds, timeouts, unreachable/HTTP-error servers, malformed/oversized JSON, incomplete/unverified/invalid/future timestamps, empty history, caching/single-flight/no stale fallback, API limits, page separation, CSV export, polling non-overlap/unmount cleanup, chart rendering, and mobile/tablet responsiveness. Existing historical/model API and React regressions remain in the suite.

Final results: **65 Python tests passed** (25 IoT tests plus 40 existing tests), one legacy training test intentionally deselected; **10 React browser tests passed**; **three shared Recharts/Streamlit browser tests passed**. Both production builds and Python byte-compilation passed. No final test failures remain. Existing non-blocking bundle/directive warnings and a TestClient dependency deprecation warning remain.

SHA-256 checks confirmed all **44 protected original Python/CSV/checkpoint/JSON files unchanged**. All three previously saved Phase 4 experimental weight files also match their recorded model-version hashes. No original or experimental model was retrained or promoted as part of this integration; short existing Phase 4 regression training fixtures are confined to test/temporary artifacts.

## Firebase preparation and remaining work

No SQLite-to-Firestore migration, Firebase credentials, ingestion changes, or remote deployment were performed. `SensorProvider` plus the normalized response schema isolates the React UI from storage implementation. Render can retain its current API contract while its storage changes later; alternatively a new server-side provider can implement the same normalized `latest()`/`history()` methods without changing React components.

Before migration/operational use, agree on:

1. Full offset-bearing/UTC measurement timestamps, source/device clock synchronization, separate server receipt/ingestion timestamps, stable IDs, and documented cadence. Do not retroactively relabel legacy SQLite times as UTC without evidence.
2. Firestore collection/schema, pagination/retention, read/write permissions, service-account handling strictly server-side, and cost/rate limits.
3. A separately authorized migration/backfill, timestamp provenance review, reconciliation/duplicate handling, and staged cutover preserving ESP32/API compatibility.
4. Sensor siting/calibration and heat-index/advisory methodology validation. The existing IoT forecast and claimed three-hour horizon still require independent evaluation; no alert or forecasting model promotion is implied by this integration.
