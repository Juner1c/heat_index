# Phase 4 model comparison — engineering smoke test

**This report does not establish scientific validation, model promotion eligibility, or Phase 5 readiness.**

Executed run: `20261014T064400Z_smoke_684a3a82`. Data fingerprint: `e8092a7f480b9c7f92e715dd9e421d5b0b820651a813c91cc350ef55de2859ef`.

## Comparison protocol

All six predictors were scored on exactly the same **38 target hours**, August 10, 2024 at 10:00 through August 11 at 23:00 UTC. Every forecast uses only observations whose valid times precede the target. Operational availability of those retrospective gridded inputs is not verified.

The MLP, canonical LTC, and CfC used the same six-hour seven-feature windows, 170 training targets, 36 validation targets, and eight-epoch maximum configuration fixed before execution. Validation loss, not final test scores, selected checkpoints. Both original custom RNNs were replayed without retraining and appear only as historical references; their original training splits/budgets differ.

## Results

| Predictor | Protocol | MAE °C | RMSE °C | Bias °C | R² |
| --- | --- | ---: | ---: | ---: | ---: |
| Persistence | Current smoke-test targets | 0.853550 | 1.284739 | −0.097739 | 0.834283 |
| Window MLP | Phase 4 smoke training | 1.155904 | 1.398423 | −0.511390 | 0.803658 |
| Canonical LTC | Phase 4 smoke training | 1.968771 | 2.425982 | −0.597097 | 0.409103 |
| Canonical CfC | Phase 4 smoke training | 1.206652 | 1.514009 | +0.297642 | 0.769859 |
| Original single time-constant RNN | Historical reference | 1.116373 | 1.426542 | +0.262476 | 0.795682 |
| Original sequence time-constant RNN | Historical reference | 1.254461 | 1.720311 | +0.312500 | 0.702867 |

Bias means prediction minus actual. Lower MAE/RMSE is better. Persistence is best on both metrics in this slice. All trained predictors have negative MAE skill relative to persistence. Different training protocols prevent interpreting the historical-reference rankings as controlled architectural evidence.

The original Phase 3 49-target comparison is unchanged and separate: persistence MAE/RMSE 0.941808/1.331892°C, single 1.121703/1.415527°C, sequence 1.278643/1.687439°C. Do not mix those scores with this table's 38-target scores.

## Training and checkpoint checks

| Experimental model | Epochs executed | Selected epoch | Validation MSE, scaled units² | Training loop seconds, CPU |
| --- | ---: | ---: | ---: | ---: |
| MLP | 8 | 8 | 0.179456 | 0.127 |
| LTC | 8 | 8 | 0.461480 | 1.172 |
| CfC | 8 | 6 | 0.124081 | 0.344 |

Durations exclude CSV preparation, imports, reports, and artifact loading. Each of the three saved checkpoints passed exact reconstruction/reload checks. Unit tests separately execute short synthetic training twice to verify deterministic same-environment weights and independence from changed test values; those fixture results are not included as scientific observations or metrics.

## Artifact locations

Under `experiments/phase4/20261014T064400Z_smoke_684a3a82/`:

- `checkpoints/{mlp,ltc,cfc}/weights.pt` and `metadata.json`.
- `metrics/model_comparison.csv`, three model loss CSVs, `error_by_hour_utc.csv`, `error_by_heat_index_range_c.csv`.
- `predictions/predicted_vs_actual.csv` and `prepared_dataset.csv`.
- `figures/training_loss.png`, `validation_loss.png`, `forecast_comparison.png`, `residual_distribution.png`.
- `reports/dataset_audit.json`, `dataset_manifest.json`, `hourly_coverage.csv`, `splits.json`, `results.json`, `model_comparison.md`.
- `config.json` and `run_status.json` (`completed`, `smoke_test`, promotion ineligible).

These experimental artifacts are not compatible replacements for the original Phase 3 custom-cell checkpoints, and no replacement was attempted.

## Interpretation and next decision

This run demonstrates working canonical LTC/CfC implementation, train-only scaling, validation selection, reproducibility, artifact integrity, and common-target evaluation. It does **not** establish that the canonical architecture is intrinsically worse; eight epochs on 170 examples cannot support that conclusion.

The test period is less than two days and was previously examined. There are only eleven satellite-covered days in one month, no independent station target evaluation, no verified issue-time input availability, and no higher heat-index examples at/above 41°C.

**Recommended next action: collect more aligned historical data first.** Then reserve a genuinely new final holdout, run pre-registered development-only walk-forward evaluation, and consider a modest validation-driven LTC improvement experiment. Do not proceed to operational Phase 5 alerts/deployment based on these smoke scores. No experimental model should be promoted without explicit approval and stronger evidence.
