# Phase 4 research method

## Scope and separation

`research/phase4/` is an offline research package inside `heat_index_phase1`. It reuses the existing feature definitions, default data root, and read-only original-model replay service. Nothing in the FastAPI/React forecasting path imports this package. New artifacts go only into unique directories below `experiments/phase4/`; existing checkpoint directories cannot be overwritten by the artifact saver.

There is no promotion API or automatic model selection. Explicit owner approval is required before any integration into the forecasting service.

## Models and verified library API

Installed and inspected: Python 3.12, PyTorch 2.13.0, ncps 1.0.1, NumPy 2.4.6, Pandas 2.3.3, Matplotlib 3.11.1, PyYAML 6.0.3. CUDA is unavailable; the experiment used CPU.

The actual `ncps.torch.LTC` and `CfC` constructors, forward signatures, and installed LTC ODE solver source were inspected before implementation. Both return `(output, state)` and accept batch-first `[batch,time,features]` inputs. Integer `units` selects fully-connected wiring. The adapter consumes the final sequence output and applies a linear scalar readout.

| Model | Architecture | Six-hour input | Total / trainable parameters in executed configuration |
| --- | --- | --- | ---: |
| Persistence | Last observed origin-time heat index | Last observation only | 0 / 0 |
| Window MLP | Flatten 6×7 → Linear(42,12) → Tanh → Linear(12,1) | Yes | 529 / 529 |
| Canonical LTC | `ncps.torch.LTC(7,12)`, six ODE unfolds, no mixed memory → Linear(12,1) | Yes | 1,227 / 999 |
| Optional canonical CfC | `ncps.torch.CfC(7,12)`, default mode, one 12-unit backbone layer, zero dropout, no mixed memory → Linear(12,1) | Yes | 877 / 877 |

The LTC total includes fixed wiring masks registered as non-trainable parameters. Hidden states reset to zero for each independent input window. One default numerical time step represents one hour; irregular windows are rejected, not passed through as uniform hourly data. Sequence length is configurable; default six hours. Every model predicts one hour after the final input timestamp.

The canonical LTC has state/input-dependent conductances and a numerical differential-equation solver. It is distinct from the original custom fixed-time-constant RNNs. CfC is a separate closed-form continuous-time comparison, not an LTC alias.

Primary references:

- Hasani et al., [Liquid Time-constant Networks](https://arxiv.org/abs/2006.04439).
- Hasani et al., [Closed-form Continuous-time Neural Models](https://arxiv.org/abs/2106.13898).
- Author-maintained [ncps repository](https://github.com/mlech26l/ncps), [quickstart](https://ncps.readthedocs.io/en/latest/quickstart.html), and [LTC source API](https://ncps.readthedocs.io/en/latest/_modules/ncps/torch/ltc.html).

## Data and leakage controls

1. Validate configured local CSV schemas; normalize UTC explicitly; reject invalid, duplicate, or off-hour timestamps. Missing/non-finite numeric values remain unavailable.
2. Left-join weather onto satellite timestamps with one-to-one validation. Screen air temperature −90–60°C, humidity 0–100%, dew point −100–60°C, and positive Kelvin values. These are broad data-quality screens, not a claim that the heat-index formula is physically valid across those entire ranges.
3. Derive current heat index from valid air temperature/humidity using the original preparation method; derive the target by exact lookup at +1 hour, never row-shifting across gaps.
4. Construct finite, consecutive input windows. Validate every target against its actual next-hour source row. Seven features are allowlisted; neither apparent temperature, target heat index, nor future weather enters the model input.
5. Split target timestamps chronologically: 70% training, 15% validation, remainder test by default. Historical input context may overlap splits; target sets do not.
6. Fit per-feature means/population standard deviations to flattened overlapping **training windows only** and target mean/std to training targets only. Repeated context retains its original window weighting. Zero-variance scales become one; no inference fitting occurs.
7. Optimize training batches only. Select the lowest validation MSE checkpoint; patience/minimum improvement affects stopping. Do not use final-test scores to select epochs, architecture, or hyperparameters.
8. Finish selecting all experimental checkpoints before evaluating the final partition. Assert saved/reloaded predictions reproduce validation outputs before test evaluation.

Availability leakage remains unresolved: the CSVs contain valid times, not publication/ingestion times. Results are retrospective, not operational forecasts.

## Fixed smoke-test protocol

Configuration is in `research/phase4/config/experiment.yaml`: six-hour sequence, hidden size 12, one-hour horizon, seed 42, Adam learning rate 0.003, batch size 32, gradient clipping 1.0, at most eight epochs, validation patience three, minimum improvement 0.0001, one CPU thread. No hyperparameter search was run.

Python, NumPy, and PyTorch seeds and deterministic algorithms are enabled. CPU duplicate-training tests verify exact same-environment weights, histories, scalers, and inference, even when final-test values are perturbed. Exact bitwise reproduction across dependency versions/hardware is not guaranteed.

The code blocks non-smoke training when screening fails or the configured final test was previously inspected. Smoke mode is limited to ten epochs. The current 244 examples fail minimum sufficiency screening and the August dates were previously inspected, so this run is **smoke_test**, never scientific validation.

## Original-model references

Original checkpoints are never retrained. Their saved held-out predictions are first reproduced with the Phase 3 loader. They enter a Phase 4 table only if every requested target lies inside their verified original held-out records and actual targets match. Otherwise they are explicitly excluded.

The executed 38-hour final slice is held out from both originals' training. However, their 80/20 training periods and training budgets differ from the new 70/15/15 protocol. Identical target timestamps permit descriptive score comparison, not a controlled claim that one architecture is superior. The prior 49-hour Phase 3 scores remain historical references, not interchangeable with these 38-hour scores.

## Metrics, artifacts, and optional walk-forward evaluation

Metrics: MAE, RMSE, mean prediction-minus-actual bias, R² where target variance/sample count permits, residual 5th/50th/95th percentiles, maximum absolute error, and MAE skill relative to persistence. Non-finite/misaligned vectors are rejected. R² is descriptive arithmetic, not evidence of statistical reliability on 38 hours.

Predicted/actual and residual records use UTC target times. Error breakdowns use target UTC hour and numeric heat-index bins `<27`, `27–<32`, `32–<41`, `41–<54`, `>=54 °C`. These bins are descriptive groups, not validated alerts. Empty bins have no scores. Four generated figures show training loss, validation loss, forecasts, and residual distributions with units.

Every new checkpoint records architecture, configuration, feature order, sequence length, horizon, units, fitted scalers, train/validation/test dates, seed, duration, dependency versions, dataset/source fingerprints, and weight SHA-256 model version. Loading uses CPU `weights_only=True`, strict tensor matching, scaler validation, artifact integrity checks, and evaluation/inference modes.

`python -m research.phase4.walk_forward --smoke` supports a separate expanding-window research option on development data only; the final chronological holdout is excluded. It refits scalers/model weights per fold, uses separate fold validation, and writes uniquely separated fold artifacts. The option is implemented and its split logic tested; **no walk-forward model experiment was executed for the reported results**.

There are no invented confidence intervals or calibrated uncertainty bands. No optional research dashboard page was added; CSV/Markdown reports and figures keep these incomplete experiments separate from operational forecasts.

## Reproduction

From `ThermoCast\heat_index_phase1` in Windows PowerShell:

```powershell
# Activate an existing environment, or create one first with python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-phase4.txt
python -m research.phase4.run --audit-only
python -m research.phase4.run --smoke
python -m pytest -q -k 'not training_pipeline'
python -m compileall -q research backend dashboard scripts
```

No dependency installation was needed in this already-provisioned workspace. Each invocation creates a new run ID; no automatic data download occurs. The excluded `training_pipeline` test belongs to the older Phase 1 synthetic training workflow, not the newly executed Phase 4 training tests.

For new locally acquired CSVs, update a separate copy of the YAML configuration with their paths/provenance and run the audit first. Configure `THERMOCAST_DATA_DIR` if sources live outside the default scientific directory. Set `final_test_previously_inspected: false` only for genuinely new, pre-registered holdout dates—not to bypass a failed gate on the existing dates.
