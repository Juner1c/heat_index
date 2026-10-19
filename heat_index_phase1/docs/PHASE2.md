# Phase 2: React environmental monitoring dashboard

This guide records the Phase 2 baseline. The original forecasting placeholder has since been replaced by audited one-hour prototype inference; see `PHASE3_INTEGRATION.md` and `LNN_MODEL_AUDIT.md` for the current API and scientific limitations.

The original `Himawari9_Development` directory remains the read-only scientific source. The existing FastAPI app in `heat_index_phase1/backend` now includes a separate Phase 2 router and data service. The Streamlit UI remains available; the new `frontend` folder is the React/Vite application. The React pages reuse the pure `TimeSeriesChart` component from the Streamlit integration rather than introducing another chart implementation.

## Windows PowerShell startup

From `ThermoCast\heat_index_phase1`, create a project virtual environment (if one does not already exist):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dashboard.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window, from `ThermoCast\heat_index_phase1\frontend`:

```powershell
npm ci
npm run dev
```

Use Node.js 22.12+ or Node.js 24. Open **http://127.0.0.1:5173/**. API documentation is at **http://127.0.0.1:8000/docs**. The Vite development server proxies `/api` to port 8000. The API also allows the two loopback Vite origins through CORS.

No model training, downloads, or source CSV generation commands are necessary to use this dashboard. Python ML dependencies are not imported by the Phase 2 routes.

To continue using Streamlit, install `requirements.txt` in the same virtual environment and run in another terminal:

```powershell
python -m streamlit run dashboard/historical.py --server.port 8501
```

## Data sources and science

| Page | Existing source | Meaning |
| --- | --- | --- |
| Overview / Historical / Quality | `mariveles_hourly/himawari_mariveles_hourly.csv` | B08/B13/B14/B15 brightness temperatures, in Kelvin |
| Weather | `open_meteo_clean.csv` | Historical gridded air temperature in °C and relative humidity in %; not a local sensor station |
| Heat index | `heat_index_dataset.csv` | Existing `heat_index_C`, with ground-weather inputs `temperature_C` and `humidity_percent` |
| Quality archives | `data_coverage_results/*.csv` | Existing pipeline reports, explicitly labeled archived |
| Forecasting | File-presence checks only | Inference disabled; no predictions or confidence values are generated |

`merge_weather_data.py` performs an inner join on matching hourly timestamps. `prepare_heat_index.py` uses the NWS preliminary index averaged with air temperature, the Rothfusz regression when that result is at least 80 °F, and low/high humidity adjustments, then converts the result to °C. Phase 2 reads that stored column rather than recomputing or replacing the scientific data. The one-hour-ahead training target is never displayed as an observation or forecast.

The original Open-Meteo file identifies GMT, offset zero. Naive CSV timestamps are interpreted as UTC; timestamps with offsets are converted to UTC without changing their represented instant. Date-only end filters include the entire UTC day. Existing coverage archives are stale relative to the current CSV; live metrics are calculated independently and take precedence.

## Configuration

The default dataset directory is `ThermoCast/Himawari9_Development`, anchored to the backend file location, not the terminal directory. Optional backend environment variables:

```powershell
$env:THERMOCAST_DATA_DIR = 'C:\path\to\Himawari9_Development'
# Optional per-source overrides:
$env:HIMAWARI_CSV = 'C:\path\to\himawari_mariveles_hourly.csv'
$env:GROUND_WEATHER_CSV = 'C:\path\to\open_meteo_clean.csv'
$env:HEAT_INDEX_CSV = 'C:\path\to\heat_index_dataset.csv'
```

Frontend `VITE_API_BASE_URL` can override `/api` when serving frontend and API separately. Copy `frontend/.env.example` to an untracked `.env.local` if needed. Never put credentials into Vite variables, which are public browser configuration. API clients cannot select filesystem paths. Responses display source filenames only.

## API contract

- `GET /api/health`
- `GET /api/himawari/summary`
- `GET /api/himawari/history`
- `GET /api/himawari/quality`
- `GET /api/himawari/export` — filtered CSV, maximum 100,000 rows
- `GET /api/himawari/missing-hours.csv` — live missing-hour report
- `GET /api/himawari/reports/{report}` — allowlisted archived CSV reports
- `GET /api/weather/history`
- `GET /api/heat-index/history`
- `GET /api/models/status` — `inference_ready: false`

History requests support `start`, `end`, `page`, `page_size` (default 100, maximum 1,000), and `max_points` (default 800, maximum 2,000). Satellite history also accepts comma-separated `bands` and `statistic=mean|min|max|all`. Invalid dates, unsupported bands, missing files, and invalid schemas return structured errors. Invalid numeric values become JSON nulls. Invalid timestamps are excluded from history and counted by quality checks; duplicate source rows remain visible and are counted, while charts use the first record per timestamp.

Record pages preserve source values. Larger charts use labeled time bins: minimum for min-band columns, maximum for max-band columns, mean for other values. Empty bins remain gaps. Small charts use source observations with null break markers for genuine missing hours. The raw CSV is never changed. Cache keys include file modification time and size, checked on every request, so manual refresh detects processed data updates.

## Verification

Install the development/test dependencies in the project virtual environment:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m compileall -q backend frontend
```

From `frontend`:

```powershell
npm run build
# With FastAPI on port 8000 and Vite on port 5173:
npm test
```

Browser tests use the already-installed Microsoft Edge in headless mode. They check all six routes, actual source statistics, chart rendering and units, filtering, exports, unavailable-data states, and mobile navigation. The existing Streamlit browser checks remain under `dashboard/components/recharts/frontend` (`npm run test:browser`).

## Phase 3 and current limits

- Inference is deliberately disabled in the new UI and `/api/models/status`. Older Phase 1 experimental baseline/model routes remain for compatibility with the older forecasting prototype; the Phase 2 UI does not call them.
- Original model architectures and their original scaler/feature metadata still need an inference audit, validation against matching chronological splits, and timestamped prediction endpoints. Checkpoint existence is not scientific validation.
- The application reads local CSVs. It does not download satellite data, regenerate stale coverage archives, or maintain a historical file-change log. The activity panel reports the current source modification time.
- The Vite dev server is the local Phase 2 runtime. A public deployment and authentication are outside this phase. Production output is generated by `npm run build`.
