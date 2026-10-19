from __future__ import annotations

import argparse
from datetime import datetime,timezone

from scripts.common import add_destination_flags,destination,parse_row,source_arguments,verify_backup,write_new_json
from scripts.verify_migration import verify
from storage.base import ConflictError


def migrate(backup,manifest,lineage,report,*,apply=False,provider=None):
    if report.exists():raise FileExistsError("Migration reports are never overwritten; choose a new report for a resumed run.")
    try:
        evidence,rows=verify_backup(backup,manifest,lineage)
    except Exception as exc:
        write_new_json(report,{"mode":"apply" if apply else "dry_run","status":"source_verification_failed",
                               "destination_contacted":False,"reason":str(exc),"production_or_cutover_certified":False})
        raise
    result={"mode":"apply" if apply else "dry_run","source_lineage_id":lineage,"source_backup_sha256":evidence["backup_sha256"],
            "source_rows":len(rows),"high_water_mark":evidence["high_water_mark"],"validated":0,"created":0,"skipped":0,"failed":0,
            "destination_contacted":False,"records":[],"production_or_cutover_certified":False}
    imported_at=datetime.now(timezone.utc);parsed=[];seen=set()
    # Validate the whole snapshot before any destination connection/write.
    for raw in rows:
        try:
            reading=parse_row(raw,lineage,imported_at)
            if reading.source_record_id in seen:raise ValueError("Duplicate source identity.")
            seen.add(reading.source_record_id);parsed.append(reading);result["validated"]+=1
        except (ValueError,KeyError,TypeError) as exc:
            result["failed"]+=1;result["records"].append({"record_id":raw[0],"status":"validation_failed","reason":str(exc)})
    if apply and result["failed"]==0:
        if provider is None:raise ValueError("An explicitly authorized destination is required for apply.")
        for reading in parsed:
            result["destination_contacted"]=True
            try:
                outcome=provider.import_reading(reading)
                result[outcome]+=1
                result["records"].append({"record_id":reading.source_record_id,"status":outcome,"fingerprint":reading.fingerprint()})
            except ConflictError:
                result["failed"]+=1;result["records"].append({"record_id":reading.source_record_id,"status":"conflict","reason":"Destination content differs; no overwrite performed."})
            except Exception:
                result["failed"]+=1;result["records"].append({"record_id":reading.source_record_id,"status":"write_unacknowledged","reason":"Result may be uncertain. Resume idempotently after investigation."})
        result["verification"]=verify(rows,lineage,provider)
    else:
        result["records"] += [{"record_id":reading.source_record_id,"status":"validated_only","fingerprint":reading.fingerprint()} for reading in parsed]
    result["status"]="validation_failed" if result["failed"] else "dry_run_complete" if not apply else "complete" if result.get("verification",{}).get("verified") else "verification_failed"
    if result["failed"] and apply and result["destination_contacted"]:result["status"]="partial"
    write_new_json(report,result);return result


def main():
    parser=argparse.ArgumentParser(description="Dry-run by default; idempotent create/verify only, never source deletion or overwrite.")
    source_arguments(parser);add_destination_flags(parser)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    provider=destination(args,args.lineage,write=True) if args.apply else None
    result=migrate(args.backup,args.manifest,args.lineage,args.report,apply=args.apply,provider=provider)
    print(f"{result['status']}: validated={result['validated']}, created={result['created']}, skipped={result['skipped']}, failed={result['failed']}")
    if result["failed"] or result["status"]=="verification_failed":raise SystemExit(1)


if __name__=="__main__":main()
