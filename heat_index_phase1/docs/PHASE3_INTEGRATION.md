# Original-model forecasting integration

## Current status

Both original checkpoints load with the exact custom time-constant architecture, preserve saved preprocessing, and reproduce the saved test predictions. They support a one-hour prototype forecast. No training script, dataset, checkpoint, or satellite download was changed, and no training was run.

The React AI Forecasting page now supports model selection, readiness details, a Forecast button, loading/error/success states, source/issue/target timestamps, model version, forecast °C, a predicted target point alongside recent observations, and paginated retrospective evaluation records. The API reports `scientifically_validated: false`; persistence is better on the verified common holdout.

## Implementation

- `backend/services/model_loader.py`: allowlisted checkpoints, exact architecture, safe loading, saved scalers, CPU inference.
- `backend/services/preprocessing.py`: source feature extraction, timestamps, finite values, positive Kelvin values, ground-weather range screening, exact sequence length and hourly continuity.
- `backend/services/model_audit.py`: replay of stored test predictions and fair common-period baseline comparisons.
- `backend/services/model_training_audit.py`: read-only training sample/target and saved-scaler audits; no scaler fitting.
- `backend/services/forecasting.py`: prerequisite verification, timestamped predictions, bounded in-memory issue history.
- `backend/routers/forecasting.py` and `backend/schemas/forecasting.py`: validated API contract.
- `backend/middleware.py`: 4,096-byte prediction request limit, including streamed bodies.
- `frontend/src/pages/Forecasting.jsx`: original-model UI using the shared Recharts component.

The earlier experimental `ml/model.py` uses ncps LTC and is a separate model format. It is not used to load original checkpoints. Older Phase 1 experimental routes remain separate for compatibility; the React forecasting page calls only the new audited service.

## API

`GET /api/models/status` and `GET /api/models/metadata` return per-model readiness, classification, feature order, saved scaler values, sequence length, model version, latest source input, and retrospective evaluation findings. Missing PyTorch dependencies or failed checkpoint/data verification make inference explicitly unavailable.

`POST /api/forecast/predict` accepts:

```json
{
  "model": "sequence_time_constant",
  "forecast_horizon_hours": 1,
  "as_of": "2024-08-11T23:00:00Z"
}
```

`as_of` is optional; if omitted, the latest source observation is used. It must carry a UTC offset. The model identifier may also be `single_time_constant`. Clients cannot supply arbitrary files, features, scaler settings, or checkpoint paths. Unsupported horizons, unknown/extra fields, incomplete or gapped windows, and non-finite features are rejected rather than filled or extrapolated.

Successful responses contain `model`, `model_version` (checkpoint SHA-256), `status`, `issued_at`, `forecast_horizon_hours`, `input_start`, `last_input_observation`, `source`, `forecast_mode`, `scientifically_validated`, a single prediction timestamp/value, and recent observed heat-index values. The target timestamp is always the final input timestamp plus one hour. Issue time is when the request was processed and is separate from the historical target time. A history-based prediction does not describe current 2026 weather.

HTTP 422 reports invalid requests or input windows; 503 reports missing/incompatible/unverified model prerequisites; 413 reports oversized bodies. No synthetic fallback is returned.

`GET /api/forecast/history?model=sequence_time_constant&limit=50` returns bounded replay records plus recently issued API responses. Replay records are clearly marked retrospective; issue history is kept in process memory only (maximum 100 responses) and clears on restart. `limit` is 1–200. This endpoint does not claim to provide a durable post-deployment validation archive.

## Windows PowerShell

From `ThermoCast\heat_index_phase1`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-inference.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

If no virtual environment exists, first run `python -m venv .venv`. In another terminal, from `heat_index_phase1\frontend`:

```powershell
npm ci
npm run dev
```

Dashboard: http://127.0.0.1:5173/forecasting · API docs: http://127.0.0.1:8000/docs.

No new Python dependency was needed in the already-provisioned workspace. Original-model inference requires PyTorch, NumPy, Pandas, FastAPI, and Uvicorn; sklearn and ncps are not needed by this service. Dataset location is configured by the existing `THERMOCAST_DATA_DIR` and `HEAT_INDEX_CSV` environment variables. Browser users cannot choose arbitrary paths.

## Verification commands

```powershell
python -m pytest -q -k 'not training_pipeline'
python -m scripts.audit_models
python -m compileall -q backend dashboard scripts
```

From `frontend`:

```powershell
npm run build
npm test
```

From `dashboard\components\recharts\frontend`:

```powershell
npm run build
npm run test:browser
```

The existing synthetic model-training smoke test is deliberately excluded for this no-training task. Architecture reference tests execute only original class definitions, never their training scripts. Original checkpoint loading, saved-scaler reconstruction, invalid requests/windows, missing checkpoints, request-body limits, output units, exact one-hour timestamp alignment, repeatability, original result replay, and responsive frontend forecast states are verified.

### Final verification — October 14, 2026

- Python: 29 tests passed; the one training-pipeline test was intentionally deselected. Backend, dashboard, and audit scripts passed byte-compilation.
- React dashboard: production build passed and all five browser tests passed, including real model inference, loading/errors, unavailable models, and responsive navigation/charts.
- Shared Recharts/Streamlit component: production build passed and all three browser tests passed.
- Live API: model status, metadata, both original-model prediction requests, and history returned HTTP 200. The frontend forecasting route also returned HTTP 200.
- Both predictions used the last source observation, August 11, 2024 at 23:00 UTC, and targeted August 12 at 00:00 UTC. These are historical-origin estimates, not current-weather forecasts.
- SHA-256 comparison of all 44 protected original Python, CSV, checkpoint, and JSON files found no changes. No retraining was run.
- Non-blocking build warnings remain for bundle size; Python emitted a TestClient dependency deprecation warning.

## Remaining research and deployment work

1. Review whether the thesis requires canonical LTC/CfC rather than the current custom time-constant RNN classification. Any architecture change/retraining needs approval.
2. Collect more consecutive, temporally aligned satellite and suitable ground-weather data across seasons, with their operational availability documented.
3. Define independent chronological validation/test splits and evaluate against persistence on new dates. Existing training used 80/20 train/test without independent validation.
4. Establish prospective performance and uncertainty calibration before presenting operational heat-risk forecasts.
5. Add durable prediction logging if post-deployment forecast verification is required. Current issue history is intentionally ephemeral.
