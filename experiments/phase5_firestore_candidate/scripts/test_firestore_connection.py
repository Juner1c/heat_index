"""Explicit opt-in probe. Never touches sensor_readings or bulk-deletes data."""
import argparse
from datetime import datetime,timezone
import uuid

from scripts.common import add_destination_flags,destination

TEST_COLLECTION="thermocast_connectivity_tests"


def probe(client):
    identifier="probe_"+uuid.uuid4().hex
    reference=client.collection(TEST_COLLECTION).document(identifier)
    value={"probe_id":identifier,"purpose":"isolated_phase5_connectivity","created_at_utc":datetime.now(timezone.utc)}
    result={"probe_id":identifier,"collection":TEST_COLLECTION,"verified":False,"cleanup_confirmed":False}
    attempted=False
    try:
        attempted=True
        reference.create(value,retry=None,timeout=5)
        stored=reference.get(retry=None,timeout=5)
        result["verified"]=stored.exists and stored.to_dict()==value
    except Exception:
        result["error"]="Probe write/read was not acknowledged; inspect cleanup result."
    finally:
        if attempted:
            # A timed-out create may have committed. Only this unpredictable owned ID is inspected/deleted.
            try:
                stored=reference.get(retry=None,timeout=5)
                if stored.exists:
                    if stored.to_dict()!=value:raise RuntimeError("Ownership changed; no deletion.")
                    reference.delete(option=client.write_option(last_update_time=stored.update_time),retry=None,timeout=5)
                result["cleanup_confirmed"]=not reference.get(retry=None,timeout=5).exists
            except Exception:
                result["cleanup_error"]="Cleanup unconfirmed; review only this probe ID."
    return result


def main():
    parser=argparse.ArgumentParser(description="No connection by default. Probe writes only its own unique temporary document.")
    add_destination_flags(parser);parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.execute:
        print("Not executed. Explicit --execute and target confirmation are required; no Firebase connection made.");return
    provider=destination(args,"connectivity-probe",write=True)
    try:
        result=probe(provider.gateway().client)
        print(result)
        if not result["verified"] or not result["cleanup_confirmed"]:raise SystemExit(1)
    except Exception:
        print("Connectivity/cleanup failed. Inspect only this probe's test collection; credentials are never printed.")
        raise SystemExit(1) from None


if __name__=="__main__":main()
