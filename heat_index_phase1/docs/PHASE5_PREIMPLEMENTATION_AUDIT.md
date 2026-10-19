# Phase 5 pre-implementation audit — October 14, 2026

## Status: source confirmation required

This is an inspection report, **not a completed Firestore implementation or migration-safety certification**. No Firestore provider, migration command, connectivity writer, storage-mode switch, or deployment was executed or represented as complete.

The requested GitHub repository, `https://github.com/Jhunric/ThermoCast-AI`, could not be cloned: GitHub returned `Repository not found`. This may indicate a private repository, missing access, or a different URL. GitHub integration is available but was not connected during this audit.

A matching local Flask application was found at:

```text
C:\Users\Jhonric Gorillo\Desktop\JHONRIC_FILES\CAPSTONE\Heat_Index\app.py
```

That directory is outside the current writable ThermoCast workspace. It has no visible Git metadata or Render configuration establishing that it matches the deployed revision. Source SHA-256 at inspection:

```text
e013737120e0bf81d252e5b1f20156a467270335a845db93b6e3283632409a68
```

Before implementation, confirm this as the authoritative source and authorize either an isolated candidate inside the ThermoCast workspace or editing the actual working copy, or provide access to the deployed repository. No service-account file or private key is needed for this confirmation.

## Inspected local contracts

The Flask file was read as text, not imported: importing it would initialize SQLite and attempt model loading at module import time.

- Entry point: global `app = Flask(__name__)`; direct execution binds to the environment's `PORT`, default 5000.
- `POST /api/telemetry`: JSON keys `temperature` and `humidity`, currently coerced with `float(...)`; success is HTTP 200 with `{"status":"success","db_logged":true}`.
- `GET /api/v1/latest`: formatted string fields used by the separate FastAPI adapter; values currently live in a process-global dictionary.
- `GET /api/v1/history`: SQLite query ordered by descending `id`; response uses `count` and `readings` with `id`, `timestamp`, `temperature_c`, `humidity_pct`, `heat_index_c`, `forecast_3hr_c`, and `pagasa_advisory`.
- `/` and `/logs`: existing embedded Flask HTML dashboards.
- `requirements.txt`: unpinned `flask`, `torch`, `ncps`, and `gunicorn`. Firebase Admin is not installed in the inspected execution environment.
- No authoritative Render build/start configuration, deployed commit, or ESP32 firmware was identified in this local source folder. Payload compatibility can be inspected, but firmware retry/buffering behavior cannot be asserted.

## Existing SQLite records

The local `Heat_Index\thermocast.db` was opened in read-only/query-only mode. At inspection it contained **4,512 rows**, IDs 1–4,512. **This is not evidence of the production database's count or contents.** No backup or migration was performed.

Existing table:

| Column | SQLite type | Nullable |
| --- | --- | --- |
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Primary key |
| `timestamp` | TEXT | No |
| `temperature` | REAL | No |
| `humidity` | REAL | No |
| `heat_index` | REAL | No |
| `forecast_3hr_hi` | REAL | No |
| `pagasa_advisory` | TEXT | No |

The local source generates timestamps with host-local `time.strftime`, without recording a timezone. Neither host configuration nor legacy UTC measurement/receipt times have been verified.

Migration requirements for these records:

1. Preserve `timestamp` exactly as `legacy_timestamp_raw`; never attach an assumed UTC offset.
2. Keep `measured_at_utc` null unless independently verified evidence exists. Do not infer device measurement time from migration time or HTTP request time.
3. Distinguish a known future server receipt from a legacy import timestamp. Legacy rows have no proven UTC receipt time; the final schema must explicitly represent that uncertainty, e.g. a nullable historical receipt plus a separate `imported_at_utc`. Do not silently claim import time was original sensor receipt time.
4. Use one stable source-database lineage identifier plus legacy row ID for document identity. Hashing the entire backup to form the namespace would produce different identities for later snapshots and risk duplicates.
5. Preserve imported values, validate every row, record failures/conflicts, and use create-or-verify idempotency rather than overwriting an existing document with different contents.
6. Order history by a documented stable event/sequence key with an explicit tie-breaker. Importing old rows later must not make them the newest sensor measurement merely because they have newer import timestamps.
7. The old forecast column is NOT NULL. Handling missing model output needs an explicit storage/API design; simply inserting a nullable Firestore value into the existing SQLite schema is not compatible.

## Compatibility and safety concerns

- **Latest values are lost on restart:** the current latest endpoint returns only RAM state, despite durable SQLite history. Persistent recovery needs implementation.
- **No ingress validation beyond float conversion:** booleans, non-finite values, and implausible humidity/temperature need explicit rejection before inference or storage.
- **Model-load failure can leave a random model active:** the source assigns a model instance before loading weights, then catches load exceptions without resetting it. A failed checkpoint load must not produce forecasts from randomly initialized weights.
- **The existing model is CfC, not the original Phase 3 custom RNN:** three raw inputs, 32 hidden units, 24-sample windows, startup padding with repeated current input, and `current_hi + 0.2 * pred_raw`. No verified three-hour forecast target alignment is established. Its weights, feature ordering, and normal inference preprocessing must not be silently changed in a storage migration.
- **Model unavailable fallback:** the current code substitutes current heat index as the forecast. Future code must not present that as a validated forecast.
- **Advisory interval gaps:** compiling only the pure advisory function confirmed that 32.5°C, 41.5°C, and 51.5°C all fall through to `EXTREME DANGER`. This was not changed; it requires a separately reviewed methodology fix, not silent preservation as validated alert guidance.
- **Per-process sequence history:** multiple Gunicorn workers have independent inference windows/latest dictionaries. Deployment settings and concurrency behavior must be confirmed.
- **History has no strict limit cap:** bounded queries and stable pagination need implementation while preserving existing response fields.
- **Existing firmware retries are unverified:** repeated temperature/humidity pairs cannot safely identify duplicate uploads because consecutive legitimate readings can be identical. Exactly-once device ingestion cannot be claimed without a stable device event/idempotency identifier.

## Production backup prerequisite

Render documents that its default filesystem is ephemeral; only paths on an attached persistent disk survive relevant lifecycle events. Do not redeploy or add a disk before securing the current database: the existing data may otherwise be lost. See [Render persistent-disk documentation](https://render.com/docs/disks).

After explicit owner approval and access to the running production instance:

1. Identify the actual running SQLite path, current app revision, instance count, and any WAL/journal files.
2. Create a consistent database snapshot using SQLite's online backup API or another verified SQLite-native backup procedure, not an ordinary file copy of an actively written database.
3. Run integrity checks on that snapshot and capture row count, minimum/maximum IDs, schema, stable source identity, and SHA-256.
4. Transfer the backup and manifest securely off the ephemeral host using the service's approved access/export mechanism. Verify the received hash, integrity, count, and high-water mark again before any deployment.
5. Retain immutable original backups. Do not overwrite a backup with another snapshot or treat the development database as the production backup.

No production backup/export command was run, and there is no implemented migration command to execute yet.

## Incoming ESP32 uploads during migration — decision required

A consistent snapshot only covers committed rows through its own high-water mark. Uploads can continue to create records after that point; an initial matching count is not proof that cutover is lossless.

Two possible strategies require owner review:

### Approved short pause

Backfill a consistent snapshot while SQLite remains authoritative, then explicitly pause/queue ingestion, take a final consistent snapshot, migrate the delta using the same stable document IDs, verify all rows/counts/values through the final high-water mark, switch the read/write backend, and resume ingestion after endpoint checks.

An HTTP 503 pause alone does **not** guarantee preservation of ESP32 uploads. The firmware or an upstream queue must retain/retry them. An operator must confirm this before choosing a pause. Old workers that do not obey a write gate cannot remain active at the barrier.

### Durable capture/outbox or mirrored writes

An explicitly approved design can journal receipts transactionally in durable SQLite/outbox storage, replicate to deterministic Firestore documents, and track pending/completed writes and retries. A simple pair of independent SQLite/Firestore writes is not a distributed transaction and must not be advertised as atomic.

This reduces pause requirements but adds failure recovery, idempotency, replay, monitoring, and persistent-storage prerequisites. An outbox on Render's ephemeral filesystem is not a durable safety guarantee. No dual-write strategy has been enabled or implemented on the unconfirmed source.

## Firestore rollback — not just an environment toggle

Changing `STORAGE_BACKEND=sqlite` cannot recover readings accepted only by Firestore after cutover.

A safe rollback must establish one of the following before promotion:

- A verified durable SQLite mirror containing every acknowledged Firestore-era reading, plus reconciliation of pending/in-flight writes; or
- An approved pause and verified idempotent export/merge of Firestore-only records into SQLite before switching back.

If Firestore is unavailable and no durable up-to-date mirror exists, immediate lossless rollback cannot be guaranteed. A stale pre-cutover backup is insufficient. Never delete Firestore documents or reset counters as an automatic rollback step. Preserve both stores, manifests, lineage, and checkpoints for reconciliation.

## Firebase configuration — not changed

The user supplied an existing Render secret-file path for `GOOGLE_APPLICATION_CREDENTIALS`. Its contents were not accessed, printed, copied, or validated. The SDK should eventually use [Application Default Credentials](https://firebase.google.com/docs/admin/setup), with an explicitly verified project/database selection and least-privilege server-side access.

No production connection, test document, migration write, collection deletion, authentication change, or `STORAGE_BACKEND` change was made. A future connectivity CLI must require explicit approval and isolate its create/read/delete operation to one uniquely identified temporary test document outside `sensor_readings`.

## Executed checks and next input

Completed: filesystem/source inspection; GitHub clone attempt; read-only local schema/count query; AST-only advisory checks; inspection of existing FastAPI IoT contract; official Firebase/Render documentation review. These are audit checks, **not automated Firestore tests**.

Not executed: Firebase SDK integration tests, emulator tests, connectivity writes, SQLite migration/dry-run, production backup, cutover, rollback, or deployment. No claims of passing those tests are made.

**Required next input:** confirm whether the local `Heat_Index` Flask source should be used to prepare an isolated candidate inside this writable ThermoCast workspace, or provide access to the actual deployed repository. The pause-versus-durable-capture cutover approach must also be approved before it is operated.
