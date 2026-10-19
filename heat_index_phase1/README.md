# ThermoCast

Live IoT measurements from the existing Render service are now available in Overview, Weather Monitoring, Heat Index Analysis, Historical Data, and Data Quality. Sensor values remain separate from satellite/Open-Meteo history and research forecasts. Read the [IoT integration guide](docs/IOT_INTEGRATION.md) for API/configuration, timestamp limitations, tests, and the future Firebase boundary. The current upstream timestamps do not establish sensor freshness, and its separate forecast is explicitly unvalidated.

Phase 4 now has a separate offline research pipeline with canonical ncps LTC/CfC, persistence and MLP baselines, chronological validation, and reproducible artifacts. The executed experiment is an **engineering smoke test**, not scientific validation or approval for deployment. See the [dataset audit](docs/PHASE4_DATASET_AUDIT.md), [model comparison](docs/PHASE4_MODEL_COMPARISON.md), [research method](docs/PHASE4_RESEARCH_METHOD.md), and [Phase 4 report](docs/PHASE4_RESULTS.md). The current forecasting service is unchanged; additional aligned data and a new untouched holdout are required before model promotion.

Original-model forecasting is now available as a research prototype at **http://127.0.0.1:5173/forecasting**. The two original checkpoints and their saved scalers are used without retraining, for a **one-hour horizon only**. Read the [model audit](docs/LNN_MODEL_AUDIT.md), [Phase 2 exit audit](docs/PHASE2_AUDIT.md), and [Phase 3 integration guide](docs/PHASE3_INTEGRATION.md) for architecture classification, checkpoint compatibility, preprocessing, verified retrospective metrics, exact startup commands, and limitations. These forecasts are based on historical source observations and are not validated current-weather forecasts.

Phase 2 adds the full React/Vite dashboard at **http://127.0.0.1:5173/** with Tailwind CSS, Recharts, Lucide icons, and React Router. Start the existing FastAPI app on port 8000, then run `npm ci` and `npm run dev` from `frontend`. See [the Phase 2 guide](docs/PHASE2.md) for exact PowerShell commands, data provenance, API contracts, tests, configuration, and Phase 3 work. The historical Streamlit dashboard remains on port 8501.

ThermoCast Phase 1 uses FastAPI, Pandas, and Streamlit to monitor the existing Himawari-9 hourly CSV for Mariveles, Bataan. Interactive charts use React/Recharts embedded in Streamlit. The React chart itself has no Streamlit dependency and can be reused in the Phase 2 frontend.

The default data source is `../Himawari9_Development/mariveles_hourly/himawari_mariveles_hourly.csv`, resolved relative to this project rather than the terminal's current directory. The original CSV is read on every API request; it is never overwritten. `WEATHER_CSV` explicitly overrides this default. The earlier telemetry export is not the Phase 1 source.

## Current capabilities

- CSV quality summary: gaps, duplicates, nulls, invalid timestamps, and date coverage
- Per-column quality report and configurable historical-download completion tracking
- Recharts time-series charts with hover details, legend toggles, date filtering, and a zoom range
- Missing-hour breaks in chart lines and exact missing-timestamp export
- Normalized temperature, relative-humidity, and heat-index observations
- Heat-index derivation from temperature and humidity when the CSV has no heat-index column
- Explicitly labeled one-hour persistence baseline with 1–168 hour forecasts
- Walk-forward baseline MAE and RMSE
- Chronological 70/15/15 evaluation splits and per-timestamp prediction errors
- Forecast risk categories and safety guidance
- Dashboard tabs for history, forecasts, alerts, and evaluation
- Model-readiness endpoint that does not claim an unverified LNN is deployable
- Downloadable validation report containing dataset, quality, model, and evaluation evidence

The persistence forecast is a benchmark, not the target LNN. The included trainer packages the checkpoint, exact input feature order, scaling state, sequence length, architecture settings, evaluation metrics, and date coverage into a validated artifact directory.

## Windows PowerShell quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:WEATHER_CSV = 'C:\FULL\PATH\TO\himawari_mariveles_hourly.csv'
# Omit WEATHER_CSV to use the original CSV at the default project path.
python -m uvicorn backend.main:app --reload
```

Build the local chart bundle once (Node.js 22.12+ or 24 is required). Rebuild it only when changing the chart component:

```powershell
Set-Location dashboard\components\recharts\frontend
npm ci
npm run build
Set-Location ..\..\..\..
```

The bundle includes React and Recharts locally; opening the dashboard does not require a CDN or an additional frontend server.

In a second terminal, from `heat_index_phase1`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/historical.py
```

The broader forecasting prototype remains available separately:

```powershell
python -m streamlit run dashboard/app.py
```

Dashboard: <http://localhost:8501>  
API documentation: <http://127.0.0.1:8000/docs>

## Train and activate the LNN

Train the Liquid Time-Constant network with a chronological 70/15/15 split:

```powershell
python -m ml.train --csv 'C:\FULL\PATH\TO\himawari_mariveles_hourly.csv' --output artifacts\mariveles_lnn --epochs 100
```

Point the API to the resulting directory before starting Uvicorn:

```powershell
$env:LNN_MODEL_PATH = 'C:\FULL\PATH\TO\heat_index_phase1\artifacts\mariveles_lnn'
```

When the artifact validates, `/api/forecast?model=auto` and the alert dashboard use the LNN. Pass `model=baseline` to retain a direct benchmark.

## Supported columns

Column matching is case-insensitive. Common timestamp, temperature, humidity, and heat-index names are recognized in `backend/main.py`. Timestamps without a timezone are interpreted as UTC by pandas; verify the source convention before interpreting missing hours.

The original hourly CSV contains `timestamp` and mean/min/max brightness temperatures for B08, B13, B14, and B15, all in Kelvin. These satellite values are displayed in their original units. Ground temperature, humidity, and heat index are not expected columns and their absence does not fail historical quality checks.

Missing hours are checked between the earliest and latest observed UTC hours. Cell completeness counts non-empty CSV cells separately from timestamp coverage. For download progress across a planned collection interval, set both `COLLECTION_START` and `COLLECTION_END` as UTC timestamps; only observations within those bounds contribute.

## API

- `GET /health`
- `GET /api/summary`
- `GET /api/quality`
- `GET /api/gaps?limit=500`
- `GET /api/satellite?limit=1000`
- `GET /api/stations`
- `GET /api/records?limit=100`
- `GET /api/numeric?limit=1000`
- `GET /api/model/status`
- `GET /api/forecast?horizon=24`
- `GET /api/evaluation`
- `GET /api/alerts?horizon=24`
- `GET /api/report`

## Tests

```powershell
python -m pytest -q
```

With the API and historical dashboard running against the original CSV, verify the charts in the installed Microsoft Edge browser (headless):

```powershell
Set-Location dashboard\components\recharts\frontend
npm run test:browser
```

`PLAYWRIGHT_CHANNEL=chrome` selects installed Chrome; `DASHBOARD_URL` overrides the default dashboard URL. Browser tests verify rendered Recharts lines, missing-hour breaks, series toggles, record preview, refresh, and narrow-screen layout.

## Docker deployment

Copy `.env.example` to `.env`, set the host data and artifact directories, and place the CSV/artifact under those directories. Then run:

```powershell
docker compose up --build
```

The API is available at <http://localhost:8000/docs> and the dashboard at <http://localhost:8501>. Mounted data and model artifacts are read-only inside the containers.

Before project sign-off, complete [the user acceptance checklist](docs/USER_ACCEPTANCE.md) against the real Mariveles dataset and final trained model.
