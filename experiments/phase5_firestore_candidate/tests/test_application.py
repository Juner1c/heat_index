import ast
from dataclasses import replace
import json
from pathlib import Path

import pytest
import torch

from application import create_app
from inference import ForecastEngine
from storage.factory import Settings
from storage.firestore_provider import FirestoreProvider
from tests.fakes import MemoryGateway,StubEngine


def test_api_contract_homepage_logs_and_latest_restart(tmp_path):
    configuration=Settings(sqlite_path=tmp_path/"synthetic.sqlite",lineage="api-synthetic")
    engine=StubEngine();app=create_app(configuration,engine=engine)
    client=app.test_client()
    assert client.get("/api/v1/latest").json["temperature"]=="--"
    response=client.post("/api/telemetry",json={"temperature":30,"humidity":70})
    assert response.status_code==200 and response.json=={"status":"success","db_logged":True}
    latest=client.get("/api/v1/latest").json
    assert {"temperature","humidity","current_hi","forecast_hi","timestamp","cur_category","cur_action","status"}.issubset(latest)
    assert latest["temperature"]=="30.0" and latest["forecast_hi"]=="36.8"
    assert latest["timestamp"] is None and latest["measured_at_utc"] is None and latest["received_at_utc"].endswith("+00:00")
    assert latest["sensor_freshness"]=="unknown" and not latest["forecast_horizon_verified"]
    history=client.get("/api/v1/history?limit=100").json
    assert history["count"]==1 and {"id","timestamp","temperature_c","humidity_pct","heat_index_c","forecast_3hr_c","pagasa_advisory"}.issubset(history["readings"][0])
    restored=create_app(configuration,engine=StubEngine()).test_client().get("/api/v1/latest").json
    assert restored==latest
    assert client.get("/").status_code==client.get("/logs").status_code==200
    assert "Experimental IoT forecast" in client.get("/").text
    assert "Received:" in client.get("/logs").text


@pytest.mark.parametrize("payload",[{"temperature":True,"humidity":70},{"temperature":"NaN","humidity":70},
                                   {"temperature":float("inf"),"humidity":70},{"temperature":61,"humidity":70},
                                   {"temperature":30,"humidity":101},{"temperature":30,"humidity":-1},[],{},
                                   {"temperature":None,"humidity":70}])
def test_invalid_telemetry_never_reaches_inference_or_storage(tmp_path,payload):
    engine=StubEngine();client=create_app(Settings(sqlite_path=tmp_path/"unused.sqlite"),engine=engine).test_client()
    assert client.post("/api/telemetry",json=payload).status_code==400
    assert not engine.called and not list(tmp_path.iterdir())


def test_missing_or_incompatible_weights_never_activate_random_model(tmp_path):
    engine=ForecastEngine(tmp_path/"absent.pth")
    current,prediction,sample=engine.preview(30,70)
    assert engine.model is None and prediction is None
    bad=ForecastEngine(tmp_path/"bad.pth",loader=lambda _:{"incorrect":torch.zeros(1)})
    assert bad.preview(30,70)[1] is None and bad.model is None
    configuration=Settings(sqlite_path=tmp_path/"sensor.sqlite",model_path=tmp_path/"absent.pth")
    client=create_app(configuration).test_client()
    assert client.post("/api/telemetry",json={"temperature":30,"humidity":70}).status_code==200
    latest=client.get("/api/v1/latest").json
    assert latest["forecast_hi"] is None and latest["fore_category"]=="UNAVAILABLE"
    assert client.get("/api/v1/history").json["readings"][0]["forecast_3hr_c"] is None
    assert "(data.forecast_hi ?? '--')" in client.get("/").text


def test_firestore_failed_or_uncertain_write_never_returns_success(tmp_path):
    gateway=MemoryGateway();gateway.uncertain_once=True
    provider=FirestoreProvider("failure-test",lambda:gateway,True)
    engine=StubEngine();client=create_app(Settings(backend="firestore",lineage="failure-test",sqlite_path=tmp_path/"forbidden.sqlite"),provider=provider,engine=engine).test_client()
    response=client.post("/api/telemetry",json={"temperature":30,"humidity":70})
    assert response.status_code==503 and not response.json["write_acknowledged"]
    assert not engine.committed and len(gateway.documents)==1 and not list(tmp_path.iterdir())
    gateway.fail=True
    assert client.get("/api/v1/latest").status_code==503


def test_synthetic_finite_weights_load_but_nonfinite_weights_do_not_activate(tmp_path):
    from legacy_logic import HeatIndexLNN
    # Synthetic in-memory state only: never reads, copies, or writes a checkpoint.
    weights={name:torch.zeros_like(value) for name,value in HeatIndexLNN(3,32).state_dict().items()}
    finite=ForecastEngine(tmp_path/"not-a-real-checkpoint",loader=lambda _:weights)
    finite.load()
    assert finite.model is not None and not finite.model.training
    invalid={name:value.clone() for name,value in weights.items()}
    invalid["fc.weight"][0,0]=float("nan")
    rejected=ForecastEngine(tmp_path/"also-not-a-checkpoint",loader=lambda _:invalid)
    assert rejected.preview(30,70)[1] is None and rejected.model is None


def test_auth_rollout_defaults_off_then_optional_then_required(tmp_path):
    base=Settings(sqlite_path=tmp_path/"auth.sqlite",lineage="auth-test")
    optional=create_app(replace(base,auth_mode="optional",device_token="synthetic-secret"),engine=StubEngine()).test_client()
    assert optional.post("/api/telemetry",json={"temperature":30,"humidity":70}).status_code==200
    required=create_app(replace(base,auth_mode="required",device_token="synthetic-secret"),engine=StubEngine()).test_client()
    assert required.post("/api/telemetry",json={"temperature":30,"humidity":70}).status_code==401
    assert required.post("/api/telemetry",json={"temperature":30,"humidity":70},headers={"X-Device-Token":"synthetic-secret"}).status_code==200


def test_original_scientific_functions_and_input_padding_are_preserved(tmp_path):
    import legacy_logic
    source=Path("provenance/original_app.py.txt").read_text(encoding="utf-8")
    namespace={"nn":torch.nn,"CfC":__import__("ncps.torch",fromlist=["CfC"]).CfC}
    nodes=[node for node in ast.parse(source).body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in {"calculate_heat_index","get_pagasa_advisory","HeatIndexLNN"}]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"legacy_reference","exec"),namespace)
    for t,h in [(25,40),(30,70),(35,90)]:assert legacy_logic.calculate_heat_index(t,h)==namespace["calculate_heat_index"](t,h)
    for value in [26,27,32.5,41.5,51.5]:assert legacy_logic.get_pagasa_advisory(value)==namespace["get_pagasa_advisory"](value)
    captured=[]
    class Capture:
        def __call__(self,values):captured.append(values.clone());return torch.tensor([[2.0]])
    engine=ForecastEngine(tmp_path/"unused");engine.attempted=True;engine.model=Capture()
    current,prediction,sample=engine.preview(30,70)
    assert prediction==current+.4
    torch.testing.assert_close(captured[0],torch.tensor([[sample]*24],dtype=torch.float32))
    engine.commit(sample);engine.preview(31,71)
    assert captured[-1].shape==(1,24,3) and captured[-1][0,-2].tolist()==pytest.approx(sample)


def test_history_bounds_malformed_payload_and_body_limit(tmp_path):
    client=create_app(Settings(sqlite_path=tmp_path/"test.sqlite"),engine=StubEngine()).test_client()
    for value in [0,201,"bad"]:assert client.get(f"/api/v1/history?limit={value}").status_code==400
    assert client.post("/api/telemetry",data="not json").status_code==400
    assert client.post("/api/telemetry",data="x"*8193).status_code==413
