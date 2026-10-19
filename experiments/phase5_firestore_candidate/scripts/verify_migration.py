from __future__ import annotations

import argparse
from datetime import datetime,timezone

from scripts.common import add_destination_flags,destination,parse_row,source_arguments,verify_backup,write_new_json


def verify(rows,lineage,provider):
    expected={};failures=[];now=datetime.now(timezone.utc)
    for raw in rows:
        try:
            reading=parse_row(raw,lineage,now)
            if reading.source_record_id in expected:raise ValueError("Duplicate source identity.")
            expected[reading.source_record_id]=reading
        except (ValueError,KeyError,TypeError) as exc:failures.append({"record_id":raw[0],"reason":str(exc)})
    actual={};cursor=None
    try:
        while True:
            page=provider.history(200,cursor)
            for reading in page.readings:
                if reading.source_record_id in actual:raise ValueError("Duplicate destination identity or unstable pagination.")
                actual[reading.source_record_id]=reading
            if page.next_cursor is None:break
            if page.next_cursor==cursor:raise ValueError("Destination cursor did not advance.")
            cursor=page.next_cursor
    except Exception:
        return {"verified":False,"source_rows":len(rows),"error":"Destination could not be fully read; verification is incomplete.","failures":failures}
    missing=sorted(set(expected)-set(actual));extra=sorted(set(actual)-set(expected))
    mismatches=[identifier for identifier in set(expected)&set(actual) if expected[identifier].fingerprint()!=actual[identifier].fingerprint()]
    return {"verified":not(failures or missing or mismatches or extra),"source_rows":len(rows),"valid_source_rows":len(expected),
            "destination_rows_in_lineage":len(actual),"missing_ids":missing,"extra_ids":extra,"content_mismatch_ids":sorted(mismatches),
            "failures":failures,"scope":"This immutable backup/lineage only; not proof that live uploads have stopped or been reconciled."}


def main():
    parser=argparse.ArgumentParser(description="Local verification by default; destination reads require explicit opt-in.")
    source_arguments(parser);add_destination_flags(parser);parser.add_argument("--read-destination",action="store_true")
    args=parser.parse_args()
    manifest,rows=verify_backup(args.backup,args.manifest,args.lineage)
    if args.read_destination:
        result=verify(rows,args.lineage,destination(args,args.lineage))
    else:
        result={"status":"local_backup_verified","destination_contacted":False,"manifest":manifest,
                "note":"Use --read-destination plus explicit target confirmation only after approval."}
    write_new_json(args.report,result)
    print(result["status"] if "status" in result else "Destination verification passed" if result["verified"] else "Destination verification failed")
    if result.get("verified") is False:raise SystemExit(1)


if __name__=="__main__":main()
