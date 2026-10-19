from __future__ import annotations

import hashlib
import threading

from storage.base import ConflictError, Page, Reading, StorageUnavailable, check_limit, cursor_decode, cursor_encode, document_id, validate_lineage


class FirestoreProvider:
    def __init__(self,lineage,gateway_factory,allow_writes=False):
        self.lineage=validate_lineage(lineage)
        self.gateway_factory=gateway_factory
        self.allow_writes=allow_writes
        self._client=None
        self._lock=threading.Lock()

    def gateway(self):
        with self._lock:
            if self._client is None:
                try: self._client=self.gateway_factory()
                except Exception as exc: raise StorageUnavailable("Firestore initialization failed; credentials/project/access must be verified.") from exc
            return self._client

    def insert(self,reading):
        if not self.allow_writes:
            raise StorageUnavailable("Firestore writes are disabled; explicit approval/configuration is required.")
        if reading.source_lineage_id!=self.lineage or reading.source_record_id is not None:
            raise ValueError("Live Firestore inserts require this lineage and an unallocated ID.")
        try:
            return self.gateway().allocate_and_create(reading)
        except ConflictError: raise
        except Exception as exc:
            raise StorageUnavailable("Firestore write was not acknowledged; its result may be uncertain. No SQLite fallback was attempted.") from exc

    def import_reading(self,reading):
        if not self.allow_writes:
            raise StorageUnavailable("Firestore migration writes are disabled.")
        if reading.source_lineage_id!=self.lineage or reading.source_record_id is None:
            raise ValueError("Imported readings require stable source lineage and record IDs.")
        try: return self.gateway().create_or_verify(reading)
        except ConflictError: raise
        except Exception as exc: raise StorageUnavailable("Firestore migration write was not acknowledged; rerun idempotently after investigation.") from exc

    def history(self,limit=20,cursor=None):
        check_limit(limit); before=cursor_decode(cursor,self.lineage)
        try:
            records=self.gateway().history(self.lineage,limit+1,before)
            selected=records[:limit]
            return Page(selected,cursor_encode(selected[-1]) if len(records)>limit else None)
        except (ConflictError,ValueError): raise
        except Exception as exc: raise StorageUnavailable("Firestore history is unavailable. No silent SQLite fallback was used.") from exc

    def latest(self):
        page=self.history(1)
        return page.readings[0] if page.readings else None

    def get_import(self,identifier):
        return self.gateway().get(self.lineage,identifier)


class GoogleFirestoreGateway:
    """SDK operations are lazy. Only reading documents/counters in this lineage.

    Imported and live IDs share a transactionally maintained per-lineage counter.
    No measurement document is overwritten; only the counter is updated.
    """
    def __init__(self,client,timeout=5):
        self.client,self.timeout=client,timeout

    def _reference(self,lineage,identifier):
        return self.client.collection("sensor_readings").document(document_id(lineage,identifier))

    def get(self,lineage,identifier):
        snapshot=self._reference(lineage,identifier).get(retry=None,timeout=self.timeout)
        return Reading.from_document(snapshot.to_dict()) if snapshot.exists else None

    def _transaction(self,reading,allocate):
        from google.cloud.firestore_v1 import transactional
        counter=self.client.collection("sensor_reading_counters").document(hashlib.sha256(reading.source_lineage_id.encode()).hexdigest())
        @transactional
        def operation(transaction):
            counter_snapshot=counter.get(transaction=transaction,retry=None,timeout=self.timeout)
            maximum=counter_snapshot.to_dict().get("maximum_id",0) if counter_snapshot.exists else 0
            saved=reading.with_id(maximum+1) if allocate else reading
            reference=self._reference(saved.source_lineage_id,saved.source_record_id)
            existing=reference.get(transaction=transaction,retry=None,timeout=self.timeout)
            if existing.exists:
                previous=Reading.from_document(existing.to_dict())
                if previous.fingerprint()!=saved.fingerprint():
                    raise ConflictError("An existing Firestore document has different source content; it was not overwritten.")
                outcome="skipped"
            else:
                transaction.create(reference,saved.document())
                outcome="created"
            transaction.set(counter,{"maximum_id":max(maximum,saved.source_record_id),"source_lineage_id":saved.source_lineage_id})
            return saved,outcome
        return operation(self.client.transaction(max_attempts=3))

    def allocate_and_create(self,reading):
        return self._transaction(reading,True)[0]

    def create_or_verify(self,reading):
        return self._transaction(reading,False)[1]

    def history(self,lineage,limit,before):
        from google.cloud.firestore_v1.base_query import FieldFilter
        query=self.client.collection("sensor_readings").where(filter=FieldFilter("source_lineage_id","==",lineage))
        query=query.order_by("source_record_id",direction="DESCENDING").order_by("__name__",direction="DESCENDING")
        if before is not None:
            anchor=self._reference(lineage,before).get(retry=None,timeout=self.timeout)
            if not anchor.exists: raise ValueError("History cursor no longer exists.")
            query=query.start_after(anchor)
        return [Reading.from_document(snapshot.to_dict()) for snapshot in query.limit(limit).stream(retry=None,timeout=self.timeout)]
