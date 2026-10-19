from copy import deepcopy
from dataclasses import replace
import threading

from storage.base import ConflictError,document_id


class MemoryGateway:
    def __init__(self):
        self.documents={};self.counters={};self.lock=threading.Lock();self.fail=False;self.uncertain_once=False
    def allocate_and_create(self,reading):
        with self.lock:
            if self.fail:raise TimeoutError()
            identifier=self.counters.get(reading.source_lineage_id,0)+1
            saved=reading.with_id(identifier)
            self.create_or_verify(saved)
            if self.uncertain_once:
                self.uncertain_once=False;raise TimeoutError("committed but response lost")
            return saved
    def create_or_verify(self,reading):
        if self.fail:raise TimeoutError()
        key=document_id(reading.source_lineage_id,reading.source_record_id)
        if key in self.documents:
            if self.documents[key].fingerprint()!=reading.fingerprint():raise ConflictError("Different content.")
            result="skipped"
        else:self.documents[key]=deepcopy(reading);result="created"
        self.counters[reading.source_lineage_id]=max(self.counters.get(reading.source_lineage_id,0),reading.source_record_id)
        return result
    def get(self,lineage,identifier):return deepcopy(self.documents.get(document_id(lineage,identifier)))
    def history(self,lineage,limit,before):
        if self.fail:raise TimeoutError()
        rows=[deepcopy(row) for row in self.documents.values() if row.source_lineage_id==lineage and (before is None or row.source_record_id<before)]
        return sorted(rows,key=lambda row:row.source_record_id,reverse=True)[:limit]


class StubEngine:
    def __init__(self):self.committed=[];self.called=0
    def preview(self,temp,hum):
        self.called+=1
        return 35.25,36.75,[temp,hum,35.25]
    def commit(self,sample):self.committed.append(sample)
