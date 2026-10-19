# Phase 4 model comparison — 20261014T064400Z_smoke_684a3a82

Status: **smoke_test**. Promotion eligible: **false**.

This run is an engineering smoke test if labeled smoke_test, not scientific validation.
It did not change the ThermoCast forecasting service or original artifacts.

## Dataset and chronological partitions

Valid supervised sequence samples: 244; input length: 6 hours; forecast horizon: 1 hour.
Dataset fingerprint: `e8092a7f480b9c7f92e715dd9e421d5b0b820651a813c91cc350ef55de2859ef`.

| partition | samples | target_start_utc | target_end_utc | first_origin_utc | input_start_utc |
| --- | --- | --- | --- | --- | --- |
| train | 170 | 2024-08-01T06:00:00+00:00 | 2024-08-08T21:00:00+00:00 | 2024-08-01T05:00:00+00:00 | 2024-08-01T00:00:00+00:00 |
| validation | 36 | 2024-08-08T22:00:00+00:00 | 2024-08-10T09:00:00+00:00 | 2024-08-08T21:00:00+00:00 | 2024-08-08T16:00:00+00:00 |
| test | 38 | 2024-08-10T10:00:00+00:00 | 2024-08-11T23:00:00+00:00 | 2024-08-10T09:00:00+00:00 | 2024-08-10T04:00:00+00:00 |

## Identical-target comparison

All rows use the same final target timestamps. Bias is prediction minus actual.
Historical references retain their original 80/20 training protocol; they are not controlled Phase 4 retraining comparisons.

| model | protocol | samples | mae_c | rmse_c | mean_bias_c | r2 |
| --- | --- | --- | --- | --- | --- | --- |
| persistence | phase4_smoke | 38 | 0.853550 | 1.284739 | -0.097739 | 0.834283 |
| mlp | phase4_smoke | 38 | 1.155904 | 1.398423 | -0.511390 | 0.803658 |
| ltc | phase4_smoke | 38 | 1.968771 | 2.425982 | -0.597097 | 0.409103 |
| cfc | phase4_smoke | 38 | 1.206652 | 1.514009 | 0.297642 | 0.769859 |
| single_time_constant | original_historical_reference | 38 | 1.116373 | 1.426542 | 0.262476 | 0.795682 |
| sequence_time_constant | original_historical_reference | 38 | 1.254461 | 1.720311 | 0.312500 | 0.702867 |

## Limitations and next action

- Screening: train has 170 samples; screening minimum is 500; validation has 36 samples; screening minimum is 168; test has 38 samples; screening minimum is 168; Coverage is 10.96 days; screening minimum is 30
- Existing August 2024 targets were previously examined. This is not a newly untouched test set.
- Open-Meteo weather is retrospective gridded data, not verified local sensor observations. The raw export does not identify the exact originating model or publication times.
- Features are restricted by valid timestamp, but operational availability at issue time is unverified.
- Scalers use training windows/targets only; early stopping uses validation MSE only. Test scores never select epochs.
- Windows overlap historical context across splits; targets are disjoint. Earlier observations available at each origin may be reused as context.
- No confidence intervals, calibrated uncertainty, statistical superiority, or operational alert readiness is claimed.
- Collect additional aligned satellite/weather dates and reserve a new untouched holdout before model improvement decisions or Phase 5 deployment.

Full configuration, dependency versions, scaler values, periods, and dataset fingerprint are saved alongside each checkpoint.
See `dataset_audit.json`, `splits.json`, `metrics/`, `predictions/`, and `figures/` in this run.
