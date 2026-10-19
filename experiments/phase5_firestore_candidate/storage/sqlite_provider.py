from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3

from storage.base import ConflictError, Page, Reading, StorageUnavailable, check_limit, cursor_decode, cursor_encode, legacy_reading, validate_lineage

LEGACY_SELECT="id,timestamp,temperature,humidity,heat_index,forecast_3hr_hi,pagasa_advisory"


def table_exists(connection,name):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


class SQLiteProvider:
    """Legacy table is read through, not rebuilt. New nullable records use a v2 table.

    Only candidate writers may share this file: old Flask binaries cannot allocate
    IDs safely alongside v2 writes. No real database is bundled with this candidate.
    """
    def __init__(self,path: Path,lineage: str):
        self.path=Path(path)
        self.lineage=validate_lineage(lineage)

    def _connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(self.path,timeout=5)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS candidate_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO candidate_metadata VALUES ('source_lineage_id',?)",(self.lineage,))
            stored=connection.execute("SELECT value FROM candidate_metadata WHERE key='source_lineage_id'").fetchone()[0]
            if stored!=self.lineage:
                raise ConflictError("SQLite source lineage does not match its recorded identity.")
            connection.execute("CREATE TABLE IF NOT EXISTS candidate_readings (id INTEGER PRIMARY KEY,payload TEXT NOT NULL)")
            connection.commit()
            return connection
        except Exception:
            connection.close()
            raise

    def insert(self,reading: Reading):
        if reading.source_lineage_id!=self.lineage or reading.source_record_id is not None:
            raise ValueError("Live SQLite inserts require this lineage and an unallocated ID.")
        try:
            with closing(self._connect()) as db:
                db.execute("BEGIN IMMEDIATE")
                maximum=db.execute("SELECT COALESCE(MAX(id),0) FROM candidate_readings").fetchone()[0]
                if table_exists(db,"sensor_readings"):
                    maximum=max(maximum,db.execute("SELECT COALESCE(MAX(id),0) FROM sensor_readings").fetchone()[0])
                saved=reading.with_id(maximum+1)
                db.execute("INSERT INTO candidate_readings VALUES (?,?)",(saved.source_record_id,json.dumps(saved.document(json_safe=True),allow_nan=False)))
                db.commit()
                return saved
        except sqlite3.Error as exc:
            raise StorageUnavailable("SQLite did not acknowledge the write.") from exc

    def history(self,limit=20,cursor=None):
        check_limit(limit); before=cursor_decode(cursor,self.lineage)
        try:
            with closing(self._connect()) as db:
                clause=" WHERE id < ?" if before else ""
                params=(before,limit+1) if before else (limit+1,)
                new=[Reading.from_document(json.loads(row[0])) for row in db.execute("SELECT payload FROM candidate_readings"+clause+" ORDER BY id DESC LIMIT ?",params)]
                old=[legacy_reading(row,self.lineage) for row in db.execute("SELECT "+LEGACY_SELECT+" FROM sensor_readings"+clause+" ORDER BY id DESC LIMIT ?",params)] if table_exists(db,"sensor_readings") else []
                combined=sorted(new+old,key=lambda row:row.source_record_id,reverse=True)
                if len({row.source_record_id for row in combined})!=len(combined):
                    raise ConflictError("Legacy/v2 IDs overlap. Stop mixed-version writers and reconcile explicitly.")
                selected=combined[:limit]
                return Page(selected,cursor_encode(selected[-1]) if len(combined)>limit else None)
        except (sqlite3.Error,ValueError,KeyError) as exc:
            if isinstance(exc,ConflictError): raise
            raise StorageUnavailable("SQLite history is unavailable or contains invalid records.") from exc

    def latest(self):
        page=self.history(1)
        return page.readings[0] if page.readings else None
