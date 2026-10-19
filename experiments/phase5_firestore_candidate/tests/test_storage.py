from dataclasses import replace
from datetime import datetime,timezone
import importlib
import json
from pathlib import Path
import sqlite3

import pytest

from storage.base import ConflictError,StorageUnavailable,cursor_encode
from storage.factory import Settings,initialize_client,make_storage
from storage.firestore_provider import FirestoreProvider
from storage.sqlite_provider import SQLiteProvider
from tests.fakes import MemoryGateway


def test_sqlite_legacy_readthrough_nullable_new_forecast_and_restart(legacy_db,reading):
    store=SQLiteProvider(legacy_db,reading.source_lineage_id)
    initial=store.latest()
    assert initial.source_record_id==3 and initial.legacy_timestamp_raw=="2024-08-01 12:00:32"
    assert initial.received_at_utc is None and initial.measured_at_utc is None
    saved=store.insert(replace(reading,experimental_forecast_c=None))
    assert saved.source_record_id==4 and saved.experimental_forecast_c is None
    restarted=SQLiteProvider(legacy_db,reading.source_lineage_id)
    assert restarted.latest()==saved
    page=restarted.history(2);second=restarted.history(2,page.next_cursor)
    assert [row.source_record_id for row in page.readings+second.readings]==[4,3,2,1]
    with sqlite3.connect(legacy_db) as db:
        assert db.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]==3
        assert db.execute("PRAGMA table_info(sensor_readings)").fetchall()[5][3]==1
    with pytest.raises(ConflictError):SQLiteProvider(legacy_db,"different-lineage").latest()


def test_firestore_acknowledgements_ordering_pagination_and_restart(reading):
    gateway=MemoryGateway();store=FirestoreProvider(reading.source_lineage_id,lambda:gateway,True)
    assert store.latest() is None
    for _ in range(5):store.insert(reading)
    first=store.history(2);second=store.history(2,first.next_cursor);third=store.history(2,second.next_cursor)
    assert [row.source_record_id for row in first.readings+second.readings+third.readings]==[5,4,3,2,1]
    assert third.next_cursor is None
    assert FirestoreProvider(reading.source_lineage_id,lambda:gateway).latest().source_record_id==5
    with pytest.raises(ValueError):store.history(201)
    with pytest.raises(ValueError):store.history(2,cursor_encode(replace(reading,source_lineage_id="other",source_record_id=1)))


def test_firestore_failure_uncertain_commit_never_falls_back(reading,tmp_path):
    gateway=MemoryGateway();gateway.uncertain_once=True
    store=FirestoreProvider(reading.source_lineage_id,lambda:gateway,True)
    with pytest.raises(StorageUnavailable,match="uncertain"):store.insert(reading)
    assert len(gateway.documents)==1
    assert not list(tmp_path.iterdir())
    gateway.fail=True
    with pytest.raises(StorageUnavailable):store.latest()
    with pytest.raises(StorageUnavailable,match="disabled"):
        FirestoreProvider(reading.source_lineage_id,lambda:gateway).insert(reading)


def test_lazy_import_and_creation_do_not_initialize_sdk_or_databases(tmp_path,monkeypatch):
    import storage.factory as factory
    from application import create_app
    calls=[]
    monkeypatch.setattr(factory,"initialize_client",lambda _:calls.append(1))
    config=Settings(backend="firestore",project="uncontacted-project",lineage="test-lazy",sqlite_path=tmp_path/"never-created.sqlite")
    app=create_app(config)
    assert not calls and not list(tmp_path.iterdir())
    assert app.extensions["storage_provider"]._client is None
    importlib.import_module("app")
    assert not calls


def test_remote_access_off_by_default_and_invalid_credentials_are_safe(monkeypatch,reading):
    with pytest.raises(ValueError,match="disabled"):
        initialize_client(Settings(backend="firestore",project="uncontacted",lineage="test-lazy"))
    import firebase_admin
    from firebase_admin import credentials
    monkeypatch.setattr(firebase_admin,"get_app",lambda _:(_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(credentials,"ApplicationDefault",lambda:(_ for _ in ()).throw(ValueError("private diagnostic must not leak")))
    store=make_storage(Settings(backend="firestore",project="uncontacted",lineage="test-lazy",allow_remote=True))
    with pytest.raises(StorageUnavailable) as caught:store.latest()
    assert "private diagnostic" not in str(caught.value)


def test_sdk_query_builds_offline_with_bounded_deterministic_order():
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    client=firestore.Client(project="demo-offline",credentials=AnonymousCredentials())
    query=client.collection("sensor_readings").where(filter=FieldFilter("source_lineage_id","==","synthetic-test-v1"))
    query=query.order_by("source_record_id",direction="DESCENDING").order_by("__name__",direction="DESCENDING").limit(201)
    wire=query._to_protobuf()
    assert wire.limit==201 and [value.field.field_path for value in wire.order_by]==["source_record_id","__name__"]


def test_legacy_import_receipt_and_measurement_times_cannot_be_invented(reading):
    with pytest.raises(ValueError,match="invent"):
        replace(reading,source="sqlite_legacy",source_record_id=1)
    with pytest.raises(ValueError,match="offset"):
        replace(reading,received_at_utc=datetime(2026,10,14))
