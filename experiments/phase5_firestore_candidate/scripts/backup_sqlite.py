from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
import time

from scripts.common import read_rows,sha256,write_new_json


def backup(source,output,lineage,report,*,progress_hook=None):
    source,output,report=Path(source).resolve(),Path(output).resolve(),Path(report).resolve()
    if not source.is_file() or output==source or report in {source,output}:
        raise ValueError("Use an existing source and distinct new backup/report paths.")
    if output.exists() or report.exists():raise FileExistsError("Backups and reports are never overwritten.")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.open("xb").close()  # exclusive reservation, never truncates an existing file
    started=time.monotonic()
    try:
        with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=5)) as src,closing(sqlite3.connect(output)) as dst:
            src.execute("PRAGMA query_only=ON")
            def progress(status,remaining,total):
                if time.monotonic()-started>60:raise TimeoutError("Backup timed out; partial output is retained, not certified.")
                if progress_hook:progress_hook(status,remaining,total)
            src.backup(dst,pages=128,progress=progress,sleep=.01)
            if dst.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("Backup integrity failed.")
        rows=read_rows(output,lineage)
        result={"status":"complete","source_lineage_id":lineage,"source_path":str(source),"backup_path":str(output),
                "backup_sha256":sha256(output),"row_count":len(rows),"high_water_mark":max((row[0] for row in rows),default=0),
                "created_at_utc":datetime.now(timezone.utc).isoformat(),"mechanism":"sqlite3.Connection.backup",
                "production_provenance_verified":False,"note":"A completed local backup does not certify production provenance or freeze future uploads."}
        write_new_json(report,result);return result
    except Exception:
        if not report.exists():write_new_json(report,{"status":"failed","partial_backup_retained":str(output)})
        raise


def main():
    parser=argparse.ArgumentParser(description="SQLite native online backup; never overwrites/removes the source.")
    parser.add_argument("--source",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--lineage",required=True);parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    result=backup(args.source,args.output,args.lineage,args.report)
    print(f"Backup complete: {result['row_count']} rows, high-water mark {result['high_water_mark']}. Verify and export off-host before redeployment.")


if __name__=="__main__":main()
