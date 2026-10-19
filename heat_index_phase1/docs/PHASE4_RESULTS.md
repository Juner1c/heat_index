# Phase 4 completion report — October 14, 2026

## Completion status

Phase 4 engineering deliverables are implemented and a bounded real-data **smoke-test experiment** completed. Scientific validation and model promotion remain blocked by data coverage, previously inspected holdout dates, and unverified operational input availability. No operational alert-readiness claim is made.

## Delivered

- Read-only audit of all four requested CSVs, exact-UTC multi-file dataset builder, source fingerprints/provenance, missing/duplicate/non-finite detection, hourly coverage, and exact next-hour target checking.
- Configurable consecutive-hour sequences, 70/15/15 chronological partitioning, train-only scaling, sufficiency gate, and development-only expanding walk-forward option.
- Persistence, same-window MLP, canonical ncps LTC, optional canonical ncps CfC; original custom models retained as replay-only references.
- CPU-first seeded training, Adam, gradient clipping, validation-selected best checkpoint, early stopping, loss histories, timing, and unique isolated run directories.
- Complete inference metadata, strict safe loading/integrity checks, checkpoint replay verification, common-target metrics, error breakdowns, four unit-labeled figures, and CSV/Markdown/JSON reports.
- A separate requirements file and research README. The optional application research page was not added; reports remain offline and clearly experimental.

## Executed experiment

`20261014T064400Z_smoke_684a3a82`: 262 aligned observations, 259 valid single-row examples, 244 six-hour windows. The chronological partitions contain 170/36/38 targets. Three experimental models trained for eight CPU epochs maximum with seed 42 and hidden size 12; no hyperparameter search ran. CfC's best validation checkpoint was epoch six; MLP/LTC selected epoch eight.

Persistence had the lowest MAE/RMSE on the common 38-hour test slice. Full scores, split dates, checkpoint locations, and limitations are in [PHASE4_MODEL_COMPARISON.md](PHASE4_MODEL_COMPARISON.md) and [PHASE4_DATASET_AUDIT.md](PHASE4_DATASET_AUDIT.md). Walk-forward training was not executed; its partitioning is implemented and tested separately.

## Verification

- 40 Python tests passed: 29 existing tests plus 11 Phase 4 tests. One older Phase 1 synthetic training-pipeline test was deliberately deselected.
- Phase 4 tests cover dataset loading, UTC conversion, duplicates/off-hour/non-finite records, missing hours, exact sequences/targets, chronological and walk-forward splits, train-only scaling, persistence/metrics, canonical model types/shapes, training, safe artifact reload/integrity, non-overwrite behavior, deterministic reproduction, and independence from perturbed test data.
- Five existing React browser tests passed, including original-model inference, missing-model handling, loading/errors, navigation, and mobile/tablet layouts.
- Three shared Recharts/Streamlit browser tests passed, including missing-hour display, narrow-screen charts, refresh, and hidden-series recovery.
- React production build and Python byte-compilation passed. Non-blocking existing bundle/directive warnings and a TestClient dependency deprecation warning remain.
- Original-model service and Streamlit are not modified by this offline package. No original training script was run or imported.
- Live API, React forecasting, and Streamlit returned HTTP 200. API metadata still lists only the original two custom time-constant models; no experimental model was promoted.
- All 44 protected original Python, CSV, checkpoint, and JSON files retained identical SHA-256 hashes. No satellite download was changed and no additional data were downloaded.
- Final independent reload of all three experimental checkpoints reproduced the saved test predictions within `7.11e-15 °C` of CSV serialization; all target timestamps are exactly one hour after their origins.
- A second audit-only execution, `20261014T065149Z_audit_0383d8f3`, verified the same dataset fingerprint without training.

## Files and reproducibility

New code is contained in `research/phase4/{config,data,models,training,reports,tests}`, `research/phase4/run.py`, and `walk_forward.py`. New outputs are isolated under `experiments/phase4/`. Documentation includes this report, dataset audit, research method, comparison, and the research README; dependencies are listed in `requirements-phase4.txt`.

See [PHASE4_RESEARCH_METHOD.md](PHASE4_RESEARCH_METHOD.md) for exact Windows commands, package versions, model specifications/citations, split/scaling methodology, and limitations.

## Recommended decision

1. Collect additional consecutive satellite dates overlapping weather coverage; validate crop/geolocation and preserve retrieval/model/publication metadata. The existing weather-only history cannot replace missing satellite features.
2. Define new independent chronological validation/final-test dates before tuning. Include diverse seasons/conditions and, where obtainable, suitable local weather observations for independent target assessment.
3. Use development-only walk-forward evaluation and modest validation-driven LTC changes; retain persistence as the benchmark. Do not repeatedly tune against the August 2024 final slice.
4. Revisit Phase 5 only after operational input availability, prospective performance, uncertainty/alert behavior, and explicit promotion approval are established. No experimental model was deployed.
