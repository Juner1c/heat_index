"""Creates clearly marked synthetic local artifacts; never opens a real source DB."""
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
import uuid

from scripts.backup_sqlite import backup
from scripts.migrate_sqlite_to_firestore import migrate
from scripts.common import write_new_json


def main():
    output=Path(__file__).resolve().parents[1]/"artifacts"/("synthetic_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    source=output/"synthetic_source.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sensor_readings(id INTEGER PRIMARY KEY,timestamp TEXT NOT NULL,temperature REAL NOT NULL,humidity REAL NOT NULL,heat_index REAL NOT NULL,forecast_3hr_hi REAL NOT NULL,pagasa_advisory TEXT NOT NULL)")
        db.executemany("INSERT INTO sensor_readings VALUES(?,?,?,?,?,?,?)",
                       [(i,f"2024-01-01 00:00:{i*10:02d}",30+i*.1,70,35,36,"SYNTHETIC TEST ONLY") for i in range(1,6)])
    lineage="synthetic-smoke-v1"
    copied=output/"synthetic_backup.sqlite";manifest=output/"backup_manifest.json"
    backup_result=backup(source,copied,lineage,manifest)
    result=migrate(copied,manifest,lineage,output/"migration_dry_run.json")
    write_new_json(output/"summary.json",{"synthetic_only":True,"production_contacted":False,"backup_rows":backup_result["row_count"],
                                         "dry_run_status":result["status"],"validated":result["validated"],"failed":result["failed"]})
    print(f"Synthetic-only backup and migration dry-run: {result['validated']} validated, {result['failed']} failed; no Firebase connection.")
    print(output)


if __name__=="__main__":main()
