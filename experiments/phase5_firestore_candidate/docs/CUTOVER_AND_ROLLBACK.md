# Approval-gated cutover and rollback runbook

This is a plan, not an executed migration. Do not run production commands or switch Render storage settings under the current authorization. There is no dual-write, durable outbox, device firmware change, or automatic reverse migration in this candidate.

## 1. Define what must be preserved

Preserve every committed source row, including a row whose HTTP acknowledgement may have been lost. For the candidate, accepted telemetry means a selected-backend write was acknowledged and the API returned the original success body. The caller may still miss that response; do not delete the corresponding row or assume a retry represents a new measurement.

Legacy requests have no verified device event ID or measurement time. Exact per-event delivery/deduplication cannot be reconstructed from timestamps alone. Source record IDs plus stable database lineage identify stored rows, not necessarily unique physical measurements. A high-water mark is not a substitute for comparing the actual ID set and canonical content; historical ID gaps can exist.

## 2. Production preflight — owner approval required

Before any redeploy, identify the currently deployed artifact, database path, journal mode, active writer processes/instances, filesystem/mount durability, and the authoritative production database. The owner-confirmed local source is useful provenance but is not itself proof of deployed binary/database identity. Never use the local `Heat_Index/thermocast.db` as an assumed production snapshot.

Check Render's current disk/service configuration against its [persistent disk documentation](https://render.com/docs/disks). Determine whether a redeploy/restart can remove the existing SQLite file and how a backup can be exported independently of that lifecycle. Do not redeploy merely to install a backup tool before securing the data being protected.

Approve a stable lineage such as a documented database-instance identifier. Record it with the manifest and keep it across every snapshot/delta. Do not derive lineage from backup SHA, export date, deployment version, or Firebase project name. Do not share the same lineage between unrelated databases that reuse IDs.

Also establish:

- A separately named staging Firebase project/database and explicit target confirmations.
- ADC/least-privilege IAM without copying credential files into source control or the candidate.
- Expected Firestore indexes, quota/cost, request timeouts, transaction contention and monitoring.
- A reviewed checkpoint/runtime test and single-worker inference policy, or an approved no-forecast mode.
- How to pause or durably queue incoming measurements, with an agreed maximum delay and a verified recovery/retry procedure. HTTP errors alone are not a queue.
- A rollback target that can read the canonical nullable schema. The original Flask binary cannot do so unchanged.

Stop if any of these choices are unresolved.

## 3. Back up before redeployment — owner approval required

Once the real source path and execution environment are approved, use a reviewed isolated helper accessible to that database. The backup implementation uses SQLite's native online backup API from a **read-only source connection**, not a copy of the main `.db` file that might omit journal/WAL state. It does not require importing or starting the Flask application.

The following is an argument template, not an instruction executed by this task:

```text
python -m scripts.backup_sqlite
  --source VERIFIED_PRODUCTION_SQLITE_PATH
  --output NEW_BACKUP_PATH
  --lineage APPROVED_STABLE_LINEAGE
  --report NEW_BACKUP_MANIFEST_PATH
```

Keep the original DB, its runtime journal/WAL files, and service configuration intact. Never truncate, delete, move, or replace a live SQLite database to perform the backup. The tool refuses to overwrite an output/report. Failed/partial outputs remain marked uncertified; choose new paths for another attempt.

Verify the backup manifest's completion status, SHA-256, SQLite integrity, count, and high-water mark. Export the backup and manifest to approved secure off-host storage before any redeploy. Independently hash and test-open the exported copy read-only. Restrict access because readings may be sensitive. Retain original source and deployment configuration too.

The first completed snapshot is only a snapshot. A source may accept more records immediately after its consistency point or even during the backup's completion callback. The candidate's automated test demonstrates this race with synthetic data.

## 4. Initial migration while SQLite remains authoritative

After separate staging validation and production-import approval, take the initial immutable snapshot and run a local dry-run against its matching manifest. Review every invalid record before any destination writes. Resolve source-quality issues explicitly; do not invent timezones, clip values, silently drop rows, or replace missing forecasts.

Applying a migration requires `--apply`, an explicit project and identical `--confirm-project`, and an explicit approved remote-access flag. A loopback `demo-` emulator is the only nonremote target supported by the CLI. Environment settings alone do not authorize CLI remote writes.

Imports are create-or-verify transactions under the same lineage. Reruns use the same deterministic document IDs and compare content; import time may change without changing original content. Conflicts must be investigated, never forced/overwritten. Save every run's new report, including failed IDs, uncertain writes, and fingerprints. After a lost acknowledgement, rerun idempotently rather than generating a new lineage or new source IDs.

Throughout this stage **SQLite remains the sole authoritative live writer**. Do not route telemetry to Firestore yet. Do not run both old and candidate SQLite writers against the same file. Do not activate dual-write or run a mixed-instance deployment with conflicting backend settings.

New ESP32 uploads continue entering SQLite after the first snapshot. Repeated online snapshots can reduce the final delta, but cannot prove the absence of further uploads and cannot replace the final barrier below.

## 5. Final ingestion barrier and reconciliation

Owner approval is required for the barrier and its device/upstream behavior. Choose a proven option: pause device transmission with durable retained samples, or use a separately approved durable ingress queue that keeps every arrival and replays it after cutover. Neither mechanism has been implemented by this candidate.

If neither is available, stop: no zero-loss ingestion claim is possible. A 503 or maintenance response may be discarded by the unchanged ESP32. Proceeding with an intentional capture gap would need an explicit documented loss decision, not an assumption that the sensor retries.

Once the approved mechanism is active:

1. Stop dispatching new uploads to the SQLite-writing service; keep any approved queue durable. Drain in-flight HTTP requests and all writers. Confirm no background, old-version, secondary-instance, or manual writer remains.
2. Take a **final** native backup and export its manifest/off-host copy. Record the final committed ID set/count/high-water mark and the time/writer barrier evidence. Keep SQLite authoritative until reconciliation passes.
3. Re-run the importer with the **same lineage** against the final backup. Matching initial rows are skipped; newly committed rows are created. Do not append only IDs greater than a guessed watermark without full reconciliation.
4. Run explicit destination verification while sensor writes remain frozen. Require no missing IDs, no extra unexpected IDs, no duplicate identities, and no canonical content mismatch for the complete final snapshot. Fingerprints include preserved values, raw legacy timestamp, source identity, and any original measured/received timestamps; import time is excluded.
5. Independently review the source manifest and all failed/uncertain migration records. Verify the per-lineage counter is at least the final maximum and live allocation continues above that maximum in staging. Check index readiness, target project/database, access permissions, and latest/history results.
6. Retain an auditable mapping of all committed rows, including any acknowledged request ledger available from the approved ingress mechanism. Count equality alone, or a successful dry-run against an older snapshot, is not proof that all accepted telemetry was migrated.

Any unexpected destination extras fail this candidate's strict snapshot verification. They may be legitimate staging/live rows or an incorrect target/lineage, but must be explained under the freeze. Never delete extras just to make a report pass. Never infer an ingestion barrier from a verification report; the report deliberately says it does not certify production cutover.

Only after every check and an explicit owner go-ahead may a separately approved deployment change the **single active writer** to Firestore. Avoid a rolling period with both SQLite and Firestore writers. Release the approved queue/resume transmission once the new writer is verified. Record new accepted readings and fresh post-cutover high-water marks.

## 6. Rollback — not an environment toggle

### Before Firestore accepts any live telemetry

If the sole live writer is still SQLite, abandon the cutover and continue using it. Keep its current original file and all snapshot evidence. Do not restore the initial backup over the newer source. Candidate imports need not be deleted. If rollback involves a changed binary, verify that binary can read every current canonical record.

### After Firestore accepts live telemetry

The frozen pre-cutover SQLite snapshot is now behind. Switching `STORAGE_BACKEND` back would hide Firestore-only readings and can reuse already allocated IDs. A Render redeploy does not itself reconcile that divergence.

A safe reverse path needs a separately reviewed and approved exporter/merger, **not implemented here**:

1. Establish a new approved ingress barrier and drain all Firestore writers. Preserve queued samples. Record the final cloud ID set/count and counter.
2. Export all documents in the affected lineage with full canonical values and identity into an immutable, independently hashed artifact. Preserve UTC receipt/measurement times separately from raw legacy text. Reconcile uncertain commits before finalizing this set.
3. Back up the retained SQLite rollback target first. Compare both stores by lineage/ID/content. Identical rows are matches; SQLite-only and Firestore-only rows are retained; conflicts block the merge for explicit resolution. Do not replace cloud-only null forecasts with invented numeric values merely to satisfy the old schema.
4. Build a **new** canonical-compatible SQLite target offline, preserving IDs and metadata. Populate all reconciled records, verify complete union counts/fingerprints, and test latest/history/restart and next-ID allocation above the final maximum. Do not overwrite the retained original or overwrite conflicting records.
5. Obtain explicit owner approval of the evidence and switch the sole writer to the verified canonical-compatible target. Resume approved queued uploads only after restart/read/write checks. Preserve both original stores and all manifests for audit.

An old Flask binary cannot read `candidate_readings` or represent a nullable forecast in its legacy `NOT NULL` table. Using that binary would require a separate schema/compatibility decision and tested conversion. It is not this candidate's rollback target by default.

### Firestore outage at rollback time

If no approved current mirror exists and Firestore cannot be read, a complete export cannot be obtained. Immediate zero-loss rollback is **not available**. Preserve the SQLite snapshot, all existing exports, request/queue evidence and Firestore data; restore cloud access or use a previously approved durable recovery mechanism. Do not declare SQLite complete and start allocating conflicting IDs based on an obsolete snapshot. Any intentional data-loss/reduced-availability choice requires an explicit owner decision.

No mirror, dual-write, automatic reverse export, or queue is authorized by this runbook. These are approval gates, not features claimed as implemented.

## 7. Stop/go checklist for the next stage

Local implementation/tests: complete. The next appropriate step is a separately approved **synthetic** emulator/staging rehearsal, covering real SDK transactions, contention/timeouts, actual query/index behavior, owned-probe cleanup, restart recovery, null-field clients, ingestion barriers, and reverse-path feasibility.

Production remains no-go until provenance, secure exported backups, device/queue behavior, model/runtime policy, IAM/indexes, final-delta reconciliation, canonical-compatible rollback tooling, operational monitoring, and explicit cutover authority are all resolved. This task does not execute any of those production steps.
