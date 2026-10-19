# Phase 5: isolated Firestore candidate

Status: local implementation and offline tests complete. Ready for a **separately approved synthetic staging/emulator test**, not approved for production migration or cutover.

This is a candidate based on the owner-confirmed `CAPSTONE/Heat_Index/app.py`, not a replacement for that directory or the Render service. All implementation changes are under this experiment. No production database backup, Firebase connection, deployment, firmware change, or dual-write was performed.

Read [the implementation report](docs/IMPLEMENTATION_REPORT.md) and [the cutover/rollback gates](docs/CUTOVER_AND_ROLLBACK.md) before considering any external operation. Source hashes and exclusions are recorded in [the provenance manifest](provenance/source_manifest.json).

## Layout

```text
phase5_firestore_candidate/
  app.py                         # lazy Flask entry point
  application.py                 # routes, validation, acknowledged-write contract
  inference.py                   # guarded experimental CfC loading/inference
  legacy_logic.py                # original model class and scientific functions
  storage/
    base.py                      # Reading, protocol, identity, cursors, validation
    sqlite_provider.py           # legacy read-through + nullable canonical records
    firestore_provider.py        # provider + transactional SDK gateway
    factory.py                   # lazy backend/ADC/emulator configuration
  templates/{dashboard,logs}.html # existing Flask pages adapted for honest metadata
  scripts/
    backup_sqlite.py
    migrate_sqlite_to_firestore.py
    verify_migration.py
    test_firestore_connection.py
    synthetic_smoke.py
    common.py
  tests/                         # temporary SQLite + fake/offline SDK tests
  provenance/                    # normalized source references + hash manifest
  docs/                          # implementation report + approval-gated runbook
  firestore.indexes.json
  requirements.txt
  .env.example                   # documentation, not auto-loaded
  .gitignore
  artifacts/synthetic_*/          # generated fake data only; ignored by git
  .venv/                         # isolated local test environment; ignored by git
```

## Reproduce local tests

Run from this candidate directory. The existing `.venv` was created with `--system-site-packages`; it is not a deployable environment or a dependency lock. A clean, pinned environment still needs a staging test.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.synthetic_smoke
.\.venv\Scripts\python.exe -m scripts.test_firestore_connection
```

The tests block Python socket connections and require no Firebase credentials. The smoke script creates five fake records in a new, uniquely named local artifacts directory, performs a native SQLite backup, then validates a migration **without contacting Firebase**. The connection command above is deliberately a no-op without `--execute`.

For a new environment, create a virtual environment and install `requirements.txt`. Do not install these dependencies into the original service environment. `test_consumer.py` also checks compatibility against the existing sibling `heat_index_phase1` application's Pydantic adapter, which needs that application's test dependencies.

## Optional local application preview

Not started automatically. In a fresh local process, first check that no inherited `STORAGE_BACKEND`, `SQLITE_PATH`, Firebase, or model-path override points at a real resource. With no overrides the defaults are SQLite at this candidate's `data/candidate.sqlite`, local lineage `candidate-local`, port 5001, remote Firebase access off, and Firestore writes off.

```powershell
.\.venv\Scripts\python.exe app.py
```

Opening `/api/v1/latest` or `/logs` initializes the candidate SQLite file. Loading the module alone does not create a database or initialize Firebase. No checkpoint is bundled, so new readings have no forecast unless a separately reviewed compatible checkpoint is supplied. The homepage retains the original Flask/Chart.js implementation; the existing React/Recharts dashboard is unchanged.

## Tool behavior

Use `python -m scripts.<name> --help` from this directory. Every output/report path must be new; tools never overwrite reports or delete source readings.

| Tool | Safe default | External-operation gate |
| --- | --- | --- |
| `backup_sqlite` | No operation without explicit source/output/lineage/report paths | Real production source access needs separate owner approval |
| `migrate_sqlite_to_firestore` | Validate immutable backup + manifest only | `--apply`, explicit project and identical `--confirm-project`, plus loopback emulator or separately approved `--allow-remote` |
| `verify_migration` | Local hash, integrity, count, high-water-mark checks | `--read-destination` plus explicit target confirmation/access |
| `test_firestore_connection` | No connection | `--execute` plus explicit target confirmation/access; writes only its own test document |

An emulator must be loopback-only, use a `demo-` project, and have `FIRESTORE_EMULATOR_HOST` explicitly set to the same host supplied to the CLI. No emulator run was performed for this report.

For app storage, `STORAGE_BACKEND=firestore` is supported **in a future separately approved process**. It requires an explicit stable lineage/project; remote access and writes are separately guarded by `FIRESTORE_ALLOW_REMOTE` and `FIRESTORE_ALLOW_WRITES`. Remote credentials use Firebase Admin Application Default Credentials, never a hard-coded key. Do not change Render settings based on this README.
