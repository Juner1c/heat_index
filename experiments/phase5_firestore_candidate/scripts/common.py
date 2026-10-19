from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from storage.base import Reading,legacy_reading,validate_lineage
from storage.factory import Settings,make_storage
from storage.sqlite_provider import LEGACY_SELECT,table_exists


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1048576),b""):digest.update(block)
    return digest.hexdigest()


def write_new_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write("\n")


def read_rows(path,lineage,imported_at=None):
    """No CREATE statements or schema changes; only explicitly supplied snapshots."""
    validate_lineage(lineage)
    if not Path(path).is_file():raise ValueError("SQLite snapshot is missing.")
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows=[]
        if table_exists(db,"candidate_metadata"):
            stored=db.execute("SELECT value FROM candidate_metadata WHERE key='source_lineage_id'").fetchone()
            if stored and stored[0]!=lineage:raise ValueError("Snapshot lineage does not match the configured source.")
        if table_exists(db,"sensor_readings"):
            rows.extend((row[0],"legacy",row) for row in db.execute("SELECT "+LEGACY_SELECT+" FROM sensor_readings ORDER BY id"))
        if table_exists(db,"candidate_readings"):
            rows.extend((row[0],"canonical",row[1]) for row in db.execute("SELECT id,payload FROM candidate_readings ORDER BY id"))
        if not table_exists(db,"sensor_readings") and not table_exists(db,"candidate_readings"):
            raise ValueError("No supported readings table exists.")
        return sorted(rows,key=lambda row:row[0])


def parse_row(raw,lineage,imported_at):
    identifier,kind,payload=raw
    if kind=="legacy":return legacy_reading(payload,lineage,imported_at)
    result=Reading.from_document(json.loads(payload))
    if result.source_lineage_id!=lineage or result.source_record_id!=identifier:
        raise ValueError("Canonical SQLite row has inconsistent identity.")
    return replace(result,imported_at_utc=imported_at)


def verify_backup(path,manifest_path,lineage):
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("status")!="complete" or manifest.get("source_lineage_id")!=lineage:
        raise ValueError("A completed backup manifest with matching stable lineage is required.")
    if sha256(path)!=manifest["backup_sha256"]:raise ValueError("Backup SHA-256 does not match its manifest.")
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("Backup integrity check failed.")
    rows=read_rows(path,lineage)
    if len(rows)!=manifest["row_count"] or max((row[0] for row in rows),default=0)!=manifest["high_water_mark"]:
        raise ValueError("Snapshot count/high-water mark changed or do not match the manifest.")
    return manifest,rows


def add_destination_flags(parser):
    parser.add_argument("--project",default="")
    parser.add_argument("--database",default="(default)")
    parser.add_argument("--emulator-host",default="")
    parser.add_argument("--allow-remote",action="store_true")
    parser.add_argument("--confirm-project",default="")


def destination(args,lineage,write=False):
    # Explicit allow flags, not inherited production environment flags, authorize CLI operations.
    if not args.project or args.confirm_project!=args.project:
        raise ValueError("Set --project and an identical --confirm-project before any destination access.")
    settings=Settings(backend="firestore",lineage=lineage,project=args.project,database=args.database,
                      emulator_host=args.emulator_host,allow_remote=args.allow_remote,allow_writes=write)
    if not settings.emulator_host and not settings.allow_remote:
        raise ValueError("Remote access is disabled; use an explicit loopback emulator or separately approved --allow-remote.")
    return make_storage(settings)


def source_arguments(parser):
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--lineage",required=True)
    parser.add_argument("--report",type=Path,required=True)
