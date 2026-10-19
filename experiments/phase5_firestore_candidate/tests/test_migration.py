from dataclasses import replace
from datetime import datetime,timezone
import json
import sqlite3

import pytest

from scripts.backup_sqlite import backup
from scripts.common import read_rows,sha256,verify_backup
from scripts.migrate_sqlite_to_firestore import migrate
from scripts.verify_migration import verify
from storage.base import document_id
from storage.firestore_provider import FirestoreProvider
from storage.sqlite_provider import SQLiteProvider
from tests.fakes import MemoryGateway

LINEAGE="synthetic-test-v1"


def snapshot(legacy_db,tmp_path,suffix="first"):
    copied=tmp_path/f"synthetic-{suffix}.backup.sqlite";manifest=tmp_path/f"synthetic-{suffix}.manifest.json"
    result=backup(legacy_db,copied,LINEAGE,manifest)
    return copied,manifest,result


def test_native_backup_default_dry_run_and_source_unchanged(legacy_db,tmp_path):
    before=sha256(legacy_db)
    copied,manifest,evidence=snapshot(legacy_db,tmp_path)
    assert evidence["mechanism"]=="sqlite3.Connection.backup" and evidence["row_count"]==3
    assert before==sha256(legacy_db)
    class Forbidden:
        def import_reading(self,*args):raise AssertionError("Dry-run touched destination.")
    report=migrate(copied,manifest,LINEAGE,tmp_path/"dry-run.json",provider=Forbidden())
    assert report["status"]=="dry_run_complete" and report["validated"]==3
    assert not report["destination_contacted"] and report["created"]==0
    with pytest.raises(FileExistsError):backup(legacy_db,copied,LINEAGE,manifest)


def test_migration_is_idempotent_preserves_times_and_reports_conflicts(legacy_db,tmp_path):
    copied,manifest,_=snapshot(legacy_db,tmp_path)
    gateway=MemoryGateway();store=FirestoreProvider(LINEAGE,lambda:gateway,True)
    first=migrate(copied,manifest,LINEAGE,tmp_path/"first.json",apply=True,provider=store)
    assert first["created"]==3 and first["verification"]["verified"]
    saved=gateway.get(LINEAGE,1)
    assert saved.legacy_timestamp_raw=="2024-08-01 12:00:00"
    assert saved.measured_at_utc is saved.received_at_utc is None and saved.imported_at_utc.tzinfo is not None
    again=migrate(copied,manifest,LINEAGE,tmp_path/"resume.json",apply=True,provider=store)
    assert again["created"]==0 and again["skipped"]==3 and len(gateway.documents)==3
    assert gateway.get(LINEAGE,1).imported_at_utc==saved.imported_at_utc
    key=document_id(LINEAGE,2)
    gateway.documents[key]=replace(gateway.documents[key],temperature_c=29)
    conflict=migrate(copied,manifest,LINEAGE,tmp_path/"conflict.json",apply=True,provider=store)
    assert conflict["status"]=="partial" and conflict["failed"]==1
    assert 2 in conflict["verification"]["content_mismatch_ids"]
    assert gateway.get(LINEAGE,2).temperature_c==29


def test_interrupted_write_resumes_without_duplicate_documents(legacy_db,tmp_path):
    copied,manifest,_=snapshot(legacy_db,tmp_path)
    gateway=MemoryGateway();normal=gateway.create_or_verify;lost=[False]
    def commit_then_timeout(reading):
        result=normal(reading)
        if not lost[0]:lost[0]=True;raise TimeoutError("Simulated lost response")
        return result
    gateway.create_or_verify=commit_then_timeout
    store=FirestoreProvider(LINEAGE,lambda:gateway,True)
    partial=migrate(copied,manifest,LINEAGE,tmp_path/"partial.json",apply=True,provider=store)
    assert partial["failed"]==1 and len(gateway.documents)==3
    resumed=migrate(copied,manifest,LINEAGE,tmp_path/"resumed.json",apply=True,provider=store)
    assert resumed["skipped"]==3 and resumed["status"]=="complete"


def test_new_upload_after_backup_is_reconciled_by_same_lineage_delta(legacy_db,tmp_path,reading):
    copied,manifest,_=snapshot(legacy_db,tmp_path)
    store=SQLiteProvider(legacy_db,LINEAGE)
    fourth=store.insert(reading)
    assert fourth.source_record_id==4
    gateway=MemoryGateway();cloud=FirestoreProvider(LINEAGE,lambda:gateway,True)
    first=migrate(copied,manifest,LINEAGE,tmp_path/"old-tip.json",apply=True,provider=cloud)
    assert first["created"]==3 and not first["production_or_cutover_certified"]
    assert store.latest().source_record_id==4 and cloud.latest().source_record_id==3
    final_backup,final_manifest,_=snapshot(legacy_db,tmp_path,"final")
    delta=migrate(final_backup,final_manifest,LINEAGE,tmp_path/"delta.json",apply=True,provider=cloud)
    assert delta["created"]==1 and delta["skipped"]==3 and delta["verification"]["verified"]
    assert cloud.insert(reading).source_record_id==5
    # With no dual-write, a mode switch alone would lose visibility of this Cloud-only accepted row.
    assert store.latest().source_record_id==4
    verified=verify(read_rows(final_backup,LINEAGE),LINEAGE,cloud)
    assert not verified["verified"] and verified["extra_ids"]==[5]


def test_invalid_rows_abort_entire_snapshot_before_any_cloud_writes(legacy_db,tmp_path):
    with sqlite3.connect(legacy_db) as db:db.execute("UPDATE sensor_readings SET humidity=101 WHERE id=2")
    copied,manifest,_=snapshot(legacy_db,tmp_path)
    gateway=MemoryGateway();store=FirestoreProvider(LINEAGE,lambda:gateway,True)
    result=migrate(copied,manifest,LINEAGE,tmp_path/"invalid.json",apply=True,provider=store)
    assert result["status"]=="validation_failed" and result["failed"]==1 and not gateway.documents
    assert result["records"][0]["record_id"]==2


def test_tampered_backup_and_wrong_lineage_are_rejected(legacy_db,tmp_path):
    copied,manifest,_=snapshot(legacy_db,tmp_path)
    with pytest.raises(ValueError):verify_backup(copied,manifest,"different-lineage")
    with sqlite3.connect(copied) as db:db.execute("UPDATE sensor_readings SET temperature=29 WHERE id=1")
    with pytest.raises(ValueError,match="SHA-256"):verify_backup(copied,manifest,LINEAGE)
    report=tmp_path/"tampered-report.json"
    with pytest.raises(ValueError,match="SHA-256"):
        migrate(copied,manifest,LINEAGE,report)
    failure=json.loads(report.read_text())
    assert failure["status"]=="source_verification_failed" and not failure["destination_contacted"]


def test_explicit_remote_gates_and_no_op_connectivity_cli(monkeypatch,tmp_path,capsys):
    import sys
    from scripts import test_firestore_connection
    from scripts.common import destination
    from argparse import Namespace
    args=Namespace(project="uncontacted",confirm_project="uncontacted",database="(default)",emulator_host="",allow_remote=False)
    with pytest.raises(ValueError,match="disabled"):destination(args,LINEAGE,True)
    args.confirm_project="different"
    with pytest.raises(ValueError,match="identical"):destination(args,LINEAGE,True)
    monkeypatch.setattr(sys,"argv",["probe"])
    test_firestore_connection.main()
    assert "no Firebase connection" in capsys.readouterr().out


def test_upload_committed_at_backup_completion_requires_later_reconciliation(legacy_db,tmp_path):
    added=[False]
    def writer(status,remaining,total):
        if remaining==0 and not added[0]:
            added[0]=True
            with sqlite3.connect(legacy_db) as db:
                db.execute("INSERT INTO sensor_readings(timestamp,temperature,humidity,heat_index,forecast_3hr_hi,pagasa_advisory) VALUES(?,?,?,?,?,?)",
                           ("2024-08-01 12:00:48",33,73,38,39,"SYNTHETIC CONCURRENT UPLOAD"))
    copied=tmp_path/"concurrent.backup.sqlite";manifest=tmp_path/"concurrent.manifest.json"
    result=backup(legacy_db,copied,LINEAGE,manifest,progress_hook=writer)
    assert result["row_count"]==3 and added[0]
    with sqlite3.connect(legacy_db) as db:assert db.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]==4
    assert verify_backup(copied,manifest,LINEAGE)[0]["high_water_mark"]==3
