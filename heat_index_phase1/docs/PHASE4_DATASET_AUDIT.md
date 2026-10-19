# Phase 4 dataset audit — October 14, 2026

## Decision summary

**Collect additional satellite-aligned historical data before selecting an improved model or proceeding to operational heat-risk alerts.** The limiting factor is satellite coverage, not the size of the weather CSV. The current data support a reproducible engineering smoke test only.

Executed run: `20261014T064400Z_smoke_684a3a82` under `experiments/phase4/`. Machine-readable evidence is in its `reports/dataset_audit.json`, `dataset_manifest.json`, `splits.json`, and `hourly_coverage.csv`.

## Available source data

All date ranges below are UTC; all four sources have zero duplicate, invalid, or off-hour timestamps.

| Dataset | Rows / unique hours | First observation | Last observation | Missing hours within range |
| --- | ---: | --- | --- | ---: |
| `mariveles_hourly/himawari_mariveles_hourly.csv` | 262 | 2024-08-01 00:00 | 2024-08-11 23:00 | 2 |
| `merged_weather_dataset.csv` | 262 | 2024-08-01 00:00 | 2024-08-11 23:00 | 2 |
| `heat_index_dataset.csv` | 262 | 2024-08-01 00:00 | 2024-08-11 23:00 | 2 |
| `open_meteo_clean.csv` | 49,680 | 2021-01-01 00:00 | 2026-09-01 23:00 | 0 |

The satellite range contains 264 expected hours: **99.242424% coverage**. Missing timestamps:

- August 1, 2024, 12:00 UTC.
- August 2, 2024, 00:00 UTC.

There are no missing/non-finite input features in the current satellite-aligned records. The heat-index file has three missing targets: the two observations immediately before missing satellite hours, and the final observation without a next-hour target. These are expected exclusions, not values to interpolate.

## Provenance, units, and alignment

- Satellite: Himawari-9 AHI brightness-temperature exports, using the original Satpy processing script's fixed 20×20 pixel crop. Band means B08/B13/B14/B15 are Kelvin. Spatial registration and crop representativeness were not independently validated in Phase 4; this remains a research prerequisite.
- Weather: Open-Meteo historical gridded data, not verified local weather-station sensor readings. The raw export identifies 14.446397°N, 120.528275°E, elevation 6 m, GMT, UTC offset zero. It does not preserve the exact originating weather model, retrieval query, or publication timestamps.
- Open-Meteo's [Historical Weather API documentation](https://open-meteo.com/en/docs/historical-weather-api) describes reanalysis/model-based historical products. The exact product used for this existing export cannot be inferred from the CSV alone.
- Source-naive timestamps are explicitly interpreted as UTC; offset-bearing timestamps convert to UTC. No timestamps are rounded into hourly bins.
- All 262 satellite timestamps have exact matching weather timestamps. Weather outside satellite coverage does not create additional satellite-weather examples.
- Air temperature and dew point stay °C; relative humidity stays percent. Satellite brightness temperature is never used as a substitute for air temperature.
- Heat index is derived from air temperature and humidity with the original preliminary NWS/Rothfusz and humidity-adjustment procedure. Rebuilt values agree with all 262 stored heat indices within `7.11e-15 °C`; the 259 valid next-hour targets also agree within that tolerance. Feature reconstruction differences are at most `8.53e-14` from CSV floating-point serialization.
- Aligned input ranges: air temperature 25.0–30.8°C; humidity 73–98%; dew point 23.5–26.8°C. Heat index spans 25.5442–38.5382°C. There are no examples at or above 41°C heat index, so higher-range alert behavior cannot be evaluated here.

## Supervised examples and split dates

Required feature order: `temperature_C`, `humidity_percent`, `dew_point_C`, `B08_mean_K`, `B13_mean_K`, `B14_mean_K`, `B15_mean_K`.

The target is `target_heat_index_1h_C`: the actual heat index at origin + one hour. The builder joins by exact timestamps, checks against the actual next-hour row, and never interpolates targets or fills missing features.

- Single-observation examples: **259**.
- Six-hour sequence examples: **244**.
- Excluded six-hour origins: 5 lack sufficient initial context, 10 cross hourly gaps, and 3 lack a valid next-hour target. No additional origins were excluded for invalid features.

The fixed 70%/15%/remaining split uses integer-floor training/validation counts:

| Partition | Samples | First target UTC | Last target UTC |
| --- | ---: | --- | --- |
| Training | 170 | 2024-08-01 06:00 | 2024-08-08 21:00 |
| Validation | 36 | 2024-08-08 22:00 | 2024-08-10 09:00 |
| Test | 38 | 2024-08-10 10:00 | 2024-08-11 23:00 |

Targets are disjoint and chronological. Input windows may reuse earlier historical context across partition boundaries; they never contain observations later than their forecast origin. This is not a purged independent-window design. Input scalers use only flattened training windows (1,020 feature rows, including repeated historical context); the output scaler uses only the 170 training targets.

## Availability and sufficiency findings

Historical valid-time alignment passes, but **operational availability at issue time is unverified**. There are no release/ingestion timestamps establishing when each gridded weather estimate and satellite product became available. A retrospective gridded value must not be presented as an operational observation just because its valid time precedes the target.

The configurable screening policy requires at least 500 training, 168 validation, 168 test examples and 30 days of coverage. All four checks fail here. These are engineering screening thresholds, not guarantees of statistical reliability; passing them would still require multi-season coverage, new holdouts, and operational availability review.

The 38-hour test slice is less than two days. Its dates were already examined in Phase 3; it is not a newly untouched holdout. There is no independent local station target validation, no seasonal generalization evidence, and no calibrated uncertainty.

## Expansion preparation

The builder accepts configured lists of satellite and weather CSVs with the same schemas. It records source SHA-256 hashes, provenance, units, coverage, target exclusions, and a path-independent dataset fingerprint. Duplicate timestamps, including overlapping files, are rejected for explicit review rather than silently keeping one version. Invalid numeric observations remain unavailable so windows cannot bridge them.

Next data collection should add consecutive satellite dates overlapping the existing weather coverage, verify the satellite crop, preserve retrieval/model metadata, and log product availability. Reserve a new chronological final holdout before tuning; include materially different weather conditions/seasons and suitable local observations where obtainable. Do not treat the current eleven-day slice as a reusable final test set.

No additional data were downloaded. No original dataset, training script, checkpoint, or satellite download was modified.
