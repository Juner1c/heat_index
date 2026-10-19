"""Exercise the real gateway logic against a transaction-aware fake SDK client."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone

import pytest

from scripts.test_firestore_connection import TEST_COLLECTION,probe
from storage.base import ConflictError,legacy_reading
from storage.firestore_provider import GoogleFirestoreGateway


class Snapshot:
    def __init__(self,reference,value,version):self.reference=reference;self.value=deepcopy(value);self.exists=value is not None;self.update_time=version
    def to_dict(self):return deepcopy(self.value)


class Reference:
    def __init__(self,client,path):self.client=client;self.path=path
    def get(self,**kwargs):return Snapshot(self,self.client.values.get(self.path),self.client.versions.get(self.path,0))
    def create(self,value,**kwargs):
        if self.path in self.client.values:raise ConflictError("Already exists.")
        self.client.values[self.path]=deepcopy(value);self.client.versions[self.path]=1
        if self.client.uncertain:
            self.client.uncertain=False;raise TimeoutError("Response lost after commit.")
    def delete(self,option=None,**kwargs):
        if option!=self.client.versions[self.path]:raise ConflictError("Changed after ownership check.")
        self.client.deleted.append(self.path);self.client.values.pop(self.path,None)


class Collection:
    def __init__(self,client,path):self.client=client;self.path=path
    def document(self,identifier):return Reference(self.client,self.path+"/"+identifier)


class Transaction:
    def __init__(self,client):self.client=client;self.pending=[]
    def create(self,reference,value):self.pending.append(("create",reference,value))
    def set(self,reference,value):self.pending.append(("set",reference,value))
    def run(self,function):
        result=function(self)
        for kind,reference,value in self.pending:
            if kind=="create":reference.create(value)
            else:self.client.values[reference.path]=deepcopy(value)
        return result


class Client:
    def __init__(self):self.values={};self.versions={};self.deleted=[];self.uncertain=False
    def collection(self,path):return Collection(self,path)
    def transaction(self,**kwargs):return Transaction(self)
    def write_option(self,**kwargs):return kwargs["last_update_time"]


def test_real_gateway_transaction_code_create_resume_and_counter(monkeypatch,reading):
    import google.cloud.firestore_v1 as sdk
    monkeypatch.setattr(sdk,"transactional",lambda function:lambda transaction:transaction.run(function))
    client=Client();gateway=GoogleFirestoreGateway(client)
    imported=legacy_reading((42,"2024-08-01 00:00:00",30,70,35,36,"TEST"),reading.source_lineage_id,datetime.now(timezone.utc))
    assert gateway.create_or_verify(imported)=="created"
    assert gateway.create_or_verify(imported)=="skipped"
    assert gateway.allocate_and_create(reading).source_record_id==43
    assert gateway.get(reading.source_lineage_id,42).received_at_utc is None
    with pytest.raises(ConflictError):gateway.create_or_verify(replace(imported,temperature_c=29))


@pytest.mark.parametrize("uncertain",[False,True])
def test_connectivity_probe_only_cleans_its_owned_test_document(uncertain):
    client=Client();client.values["sensor_readings/keep"]={"unrelated":True};client.uncertain=uncertain
    result=probe(client)
    assert result["cleanup_confirmed"] and result["verified"] is (not uncertain)
    assert client.values=={"sensor_readings/keep":{"unrelated":True}}
    assert len(client.deleted)==1 and client.deleted[0].startswith(TEST_COLLECTION+"/probe_")


def test_connectivity_probe_refuses_cleanup_when_owned_document_changed():
    class ChangedClient(Client):
        def write_option(self,**kwargs):
            for path in self.values:
                if path.startswith(TEST_COLLECTION+"/"):
                    self.versions[path]+=1
            return super().write_option(**kwargs)
    client=ChangedClient()
    result=probe(client)
    assert result["verified"] and not result["cleanup_confirmed"]
    assert "cleanup_error" in result and not client.deleted
