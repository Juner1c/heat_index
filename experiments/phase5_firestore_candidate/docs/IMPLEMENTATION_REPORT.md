# Phase 5 isolated implementation report

## Decision

The candidate is ready for a **separately approved synthetic staging/emulator test**. It is not cleared for production migration, Render configuration changes, model validation, or cutover. Real SDK RPCs, IAM, indexes, deployed checkpoint compatibility, and a production ingestion/rollback rehearsal remain untested.

Candidate: `ThermoCast/experiments/phase5_firestore_candidate/`.

No original application, original SQLite database, original checkpoint, firmware, production Firestore data, or Render settings were modified. No real database or checkpoint was copied. No service-account file or secret environment file was copied or read. No production backup, connectivity probe, migration, dual-write, or deployment was performed.

## 1. Files and source verification

[README](../README.md#layout) contains the candidate tree and local commands. Every implementation file is new under this experiment. The only source references copied are the original application text and requirements; application logic/templates were derived from those references. Entry points, providers, tools, tests, example configuration, index definition, and documentation are new candidate files.

Original source SHA-256 was captured and rechecked unchanged:

```text
Heat_Index/app.py
e013737120e0bf81d252e5b1f20156a467270335a845db93b6e3283632409a68
```

The original `requirements.txt`, `thermocast.db`, and `lnn_heat_index_model.pth` hashes also match their captured values. See [source_manifest.json](../provenance/source_manifest.json) for all hashes, copied files, exclusions, and reference-copy newline normalization. The reference copies are not falsely described as byte-identical backups. These checks prove local file preservation, not deployed Render artifact identity or production database provenance.

## 2. Storage architecture

`Reading` is the shared validated schema; `Storage` defines insert/latest/bounded history. App writes go to exactly one selected provider. SQLite is the default. Application creation initializes neither SQLite nor Firebase.

SQLite reads the legacy `sensor_readings` table without rebuilding it. New readings are stored in `candidate_readings`, with the complete canonical payload, because a missing forecast must be nullable while the legacy forecast column is `NOT NULL`. A metadata table records stable lineage. IDs allocate above both tables' maximum under `BEGIN IMMEDIATE`; history merges by descending ID and detects overlaps.

This is **read compatibility with the legacy schema, not mixed-binary write compatibility**. An old Flask process must not run alongside this candidate on the same file. The original binary cannot see canonical-table-only readings; rollback directly to that binary is not safe without an approved conversion/merge.

Firestore is lazy. Remote access uses Firebase Admin Application Default Credentials, explicit project/database/lineage, and separate remote/write permissions. The loopback-only `demo-` emulator path uses anonymous credentials and rejects environment/argument mismatch. No credentials or Firebase client are initialized at import. The [Firebase Admin setup documentation](https://firebase.google.com/docs/admin/setup) describes ADC setup; actual staging credentials and IAM remain to be verified.

The SDK gateway uses transactions to create immutable sensor documents and advance a per-lineage counter in `sensor_reading_counters`. Historical imports preserve IDs and advance that counter; live allocation continues above them. Existing matching imported content is skipped; conflicting content is never overwritten. No measurement document is deleted by migration.

`source_lineage_id` must stay constant across snapshots of the same logical database. Imported document ID is `reading_` plus SHA-256 of `lineage:record_id`, not a hash of the changing backup file. The counter is namespace-specific, not a global ordering across devices/databases. A replacement database with reused IDs requires an explicit lineage decision.

History uses `source_record_id DESC, document-name DESC`, lineage filtering, opaque lineage-bound cursors, and a maximum page size of 200. Import time is never used for observation ordering. The index is supplied in `firestore.indexes.json` but has not been deployed. Transaction and query behavior were inspected against the installed SDK and tested offline, not exercised against a Firebase service; see [the transaction reference](https://docs.cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.transaction).

An uncertain cloud write returns 503; it may already have committed. There is no SQLite fallback, outbox, dual-write, automatic retry of the whole telemetry request, or claim of exactly-once device delivery. A later device retry can produce a duplicate because the unchanged payload has no event ID.

## 3. Schema and timestamps

Every canonical document includes:

```text
device_id, temperature_c, humidity_percent, heat_index_c,
experimental_forecast_c, advisory, legacy_timestamp_raw,
measured_at_utc, received_at_utc, imported_at_utc,
source, schema_version, source_lineage_id, source_record_id
```

Legacy timestamp strings are retained exactly. Their measurement and receipt timestamps remain `null`; no timezone is guessed. `imported_at_utc` records the actual import operation and is excluded from source-content fingerprints so resumes do not conflict merely because the import time changed.

For unchanged ESP32 payloads there is no device measurement timestamp or verified device identity. New readings therefore have `measured_at_utc=null`, a server `received_at_utc`, and the explicitly unverified placeholder device ID. Measurement freshness stays unknown. New `timestamp` API values can be null; receipt time is a separate field. Legacy `timestamp` remains its exact original text. No timestamp is fabricated from migration time.

## 4. API and pages

| Endpoint | Result verified locally |
| --- | --- |
| `POST /api/telemetry` | Original temperature/humidity payload; exact 200 JSON `{"status":"success","db_logged":true}` only after selected backend acknowledges |
| `GET /api/v1/latest` | Original display/category/action/color/status fields preserved; reads persistent storage and survives app recreation |
| `GET /api/v1/history` | Original count/readings and row fields preserved; default limit 20, maximum 200, added `next_cursor` |
| `/`, `/logs` | Flask test client returns 200 and renders the copied/adapted pages, with experimental labels and absent-forecast handling |

Compatibility is **field-level**, with deliberate safety-related nullable semantics: unavailable `forecast_hi` / `forecast_3hr_c` are null, and absent measurement time is null. The existing FastAPI/Pydantic IoT normalizer accepts these responses, marks freshness unknown, and accepts a missing forecast. Other deployed clients still need staging verification. Stored legacy forecast values are preserved as experimental historical values, not retroactively validated.

Inputs are checked before inference: finite non-boolean numeric temperature in [-90,60] Celsius and humidity in [0,100], JSON object, bounded body. Numeric strings remain accepted. Invalid input is 400; oversized body is 413. Storage unavailability is 503; content/identity conflict is 409. Authentication remains off by default; optional/required token modes are tested but were not activated for production.

The existing React/Recharts application was not changed. Preserving the original Flask homepage means retaining its Chart.js implementation and external assets; a browser/CDN availability test has not been completed for this candidate.

## 5. Model and scientific compatibility

This Flask IoT model is **CfC**, not the Phase 4 canonical LTC research model:

```text
input [batch, 24 samples, 3 features]
  -> ncps.torch.CfC(input_size=3, units=32, batch_first=True)
  -> last sequence output -> Linear(32,1)
  -> experimental_forecast = current_heat_index + 0.2 * raw_output
```

Feature order is raw `[temperature, humidity, current_heat_index]`, float32, without scaling. The rolling window contains 24 accepted samples; short history is left-padded with the current sample, preserving the original behavior. This is not 24 hours, and the legacy field name `forecast_3hr_c` does not establish a validated three-hour horizon. History is process-local and resets after restart; a multi-worker deployment would have divergent model contexts. A future staging test should use one worker until that design is reviewed.

Checkpoint loading is lazy, CPU-only, `weights_only=True`, strict state-dict loading, finite-weight check, then `eval()`. The candidate model is assigned as active only after all checks succeed. Missing/incompatible/nonfinite weights leave the active model `None`; forecast remains null, while valid sensor readings still persist. Inference failures/nonfinite output also yield no forecast. No current-heat-index fallback is presented as a prediction.

No real checkpoint was copied, loaded, rewritten, or claimed compatible. Structural parity is tested from the original source and the original class is preserved, but actual deployed checkpoint + pinned-runtime compatibility needs separately approved staging. A checkpoint incompatibility will fail closed rather than activate random weights.

The original heat-index function and category function are retained. The latter has open decimal gaps `(32,33)`, `(41,42)`, `(51,52)`; examples 32.5, 41.5, 51.5 fall into its final `EXTREME DANGER` branch. These defects are documented and covered by parity tests, not silently corrected. No scientific validation, alert authority, horizon validation, training, or canonical LTC improvement was performed.

## 6. Migration tooling and evidence

Backup uses `sqlite3.Connection.backup`, not a raw file copy; SQLite's [online backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup) supports a consistent snapshot while other connections operate. The tool opens the source read-only, writes a new backup, checks integrity, and records SHA-256, row count, high-water mark, and lineage. A partial backup is retained and marked failed. A successful snapshot is not an ingestion freeze.

Migration defaults to local-only dry-run. It verifies the immutable backup/manifest, then validates the entire source before any destination call. Applying requires explicit target confirmation/access/write flags. Reports preserve failed IDs/reasons, successful/skipped fingerprints, conflicts, and uncertain outcomes. Rerunning with the same lineage creates missing IDs and skips matching IDs. Content conflicts stop that record without overwrite. Nothing deletes or changes the source.

Verification compares the entire expected lineage against bounded destination pages: missing, extra, duplicate, and content-mismatched IDs all fail. Count alone is insufficient. A live destination changing during verification is not a cutover certificate. Counter/IAM/index integrity and a frozen-ingestion reconciliation remain staging/production gates.

The connection probe defaults to no operation. An explicitly approved probe uses `thermocast_connectivity_tests/probe_<random-id>`, reads its own content, then conditionally deletes only that document using its update-time precondition. It reports unconfirmed cleanup after an uncertain write and never bulk-deletes or touches sensor readings. Only fake-client probe tests were executed.

Synthetic artifact directory:

`artifacts/synthetic_20261014T090747Z_47721bf4/`

| Evidence | Result |
| --- | --- |
| Native backup | 5 synthetic records; integrity/hash manifest generated |
| Migration dry-run and standalone CLI dry-run | 5 validated, 0 failed, 0 created, no destination contacted |
| Standalone local verification | `local_backup_verified` |
| Connectivity CLI without `--execute` | No connection made |

These are fake records, not a count or sample of production data. Artifact filenames use the execution clock in UTC and are not a production migration date.

## 7. Tests actually executed

- Candidate: `python -m pytest -q` using the isolated `.venv`: **36 passed** (latest run 4.87 seconds).
- Existing `heat_index_phase1` backend: `python -m pytest -q -k 'not training_pipeline'`: **65 passed, 1 deselected**, one dependency deprecation warning. Training was excluded; no model training/checkpoint rewrite was requested.
- Candidate `compileall`: passed.
- Synthetic backup/dry-run and independent local CLI verification: passed.

Coverage includes legacy SQLite read-through, nullable canonical persistence, restart recovery, both provider contracts, bounded/cross-lineage cursors, stable ordering, validation before inference, lazy Firebase, missing credentials (mocked), no remote access by default, exact success JSON, malformed/oversized requests, token rollout, absent/incompatible/nonfinite model loads, synthetic in-memory finite-weight activation, original scientific-function parity, raw 24x3 model inputs, migration idempotency/conflict/replay, tampering, uncertain commits, owned-probe cleanup and refusal after concurrent modification, FastAPI consumer compatibility, and uploads committed at/after backup completion.

The transaction gateway is exercised with a fake transaction client; real SDK query construction is checked offline. Network connections are blocked by the candidate test fixture. This is not a substitute for real emulator transaction contention, ADC/IAM, index, timeout, and multi-process tests. Browser regression was not completed: the existing local API/frontend listeners were not running; no full browser pass is claimed.

## 8. Unresolved risks and approval gates

The [cutover and rollback runbook](CUTOVER_AND_ROLLBACK.md) is mandatory. In particular:

- The first backup excludes later accepted uploads. A final ingestion barrier, drained requests, final snapshot/delta, and content reconciliation are required.
- HTTP 503 does not establish ESP32 retry. With no proven device buffering or durable upstream queue, uninterrupted capture cannot be guaranteed during a pause/outage.
- With no approved mirror, Firestore-only readings make an immediate environment-toggle rollback incomplete. Lossless rollback needs a separately reviewed export/merge/import tool and an ingestion barrier. That tool has not been implemented here.
- A cloud outage can prevent obtaining that export. Zero-loss immediate rollback is then unavailable; retain evidence and await recovery or obtain an explicit, documented loss decision.
- App auth is off for legacy compatibility. IAM, least privilege, read privacy, request rate/abuse limits, SDK/dependency pinning, secret deployment, monitoring, and production capacity remain unverified.
- Existing advisory defects and CfC scientific limitations prohibit using this candidate as a validated heat-risk alert system.

Owner approval is required before: (1) any emulator/staging process or external staging connection/write; (2) reading/backing up/exporting production SQLite and independently verifying deployed source/database identity; (3) creating production indexes/IAM or running a production probe/import; (4) pausing devices/ingress or introducing durable buffering; (5) building/activating any dual-write or reverse migration mechanism; (6) changing device auth/firmware; (7) approving scientific/category changes or using a real checkpoint; and (8) any Render redeploy, environment switch, cutover, or rollback.

Current work stops at local implementation/tests. No owner approval has been inferred for those future actions.
