"""IoT tests are fully mocked; they never contact Render."""
from datetime import datetime, timedelta, timezone
import json
from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient
import pytest
import requests

from backend.main import app
from backend.services.iot import MAX_RESPONSE_BYTES, RenderSensorProvider, Settings, get_sensor_provider

NOW = datetime(2026,10,14,7,42,tzinfo=timezone.utc)
LATEST = {"temperature":"29.2", "humidity":"30.0", "current_hi":"28.0", "forecast_hi":"28.6",
          "timestamp":"07:41:30", "cur_category":"CAUTION", "cur_action":"Upstream test advisory", "status":"Telemetry"}
ROW = {"id":1,"timestamp":"2026-10-14 07:41:30","temperature_c":29.2,"humidity_pct":30,
       "heat_index_c":28.04,"forecast_3hr_c":28.55,"pagasa_advisory":"CAUTION"}


class FakeResponse:
    def __init__(self, payload=None, status=200, body=None):
        self.status_code = status
        self.body = body if body is not None else json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size):
        for position in range(0,len(self.body),chunk_size): yield self.body[position:position+chunk_size]


def provider_for(payload=None, *, error=None, status=200, body=None):
    calls=[]
    def get(url, **kwargs):
        calls.append((url,kwargs))
        if error: raise error
        return FakeResponse(payload,status,body)
    provider=RenderSensorProvider(Settings(),get=get,utc_now=lambda:NOW)
    return provider,calls


def test_latest_formatted_values_and_no_invented_measurement_date():
    provider,calls=provider_for({**LATEST,"temperature":"29.2 °C","humidity":"30.0 %"})
    result=provider.latest(); reading=result["measurement"]
    assert result["status"]=="available" and result["server_reachable"]
    assert (reading["temperature_c"],reading["humidity_percent"],reading["heat_index_c"])==(29.2,30,28)
    assert reading["timestamp_raw"]=="07:41:30" and reading["measurement_timestamp_utc"] is None
    assert reading["timestamp_quality"]=="time_only" and reading["freshness"]=="unknown"
    assert reading["age_seconds"] is None and not reading["forecast_horizon_verified"]
    assert reading["forecast_label"]=="Experimental IoT forecast — unvalidated"
    assert calls[0][1]["timeout"]==(3,8) and not calls[0][1]["allow_redirects"]


def test_history_preserves_naive_sqlite_timestamps_and_bounds():
    provider,calls=provider_for({"count":3,"readings":[ROW,{**ROW,"id":2},{**ROW,"id":3}]})
    result=provider.history(2)
    assert result["returned_count"]==2 and result["unverified_timestamps"]==2
    assert result["duplicate_timestamps"]==1 and not result["total_database_count_known"]
    assert result["records"][0]["timestamp_quality"]=="timezone_unverified"
    assert result["records"][0]["measurement_timestamp_utc"] is None
    assert calls[0][1]["params"]=={"limit":2}
    with pytest.raises(ValueError): provider.history(201)


@pytest.mark.parametrize("value", ["NaN","inf","--",101,-1])
def test_bad_humidity_never_becomes_a_valid_reading_or_heat_index(value):
    provider,_=provider_for({**LATEST,"humidity":value})
    result=provider.latest()
    assert result["status"]=="partial" and result["invalid_fields"]>=1
    assert result["measurement"]["humidity_percent"] is None
    assert result["measurement"]["heat_index_c"] is None


@pytest.mark.parametrize("value", [True, {}, []])
def test_numeric_schema_rejects_boolean_objects_and_arrays(value):
    provider,_=provider_for({**LATEST,"temperature":value})
    result=provider.latest()
    assert result["status"]=="unavailable" and result["error_code"]=="schema_invalid"
    assert result["server_reachable"] and result["measurement"] is None


@pytest.mark.parametrize("exception,code", [(requests.ConnectTimeout(),"upstream_timeout"),
                                           (requests.ReadTimeout(),"upstream_timeout"),
                                           (requests.ConnectionError(),"upstream_unavailable")])
def test_upstream_connection_and_timeout_states(exception,code):
    provider,_=provider_for(error=exception)
    result=provider.latest()
    assert result["error_code"]==code and not result["server_reachable"]
    assert result["measurement"] is None


def test_http_error_malformed_json_empty_and_missing_sensor_data():
    provider,_=provider_for(status=503)
    assert provider.latest()["server_reachable"] and provider.latest()["error_code"]=="upstream_http_error"
    provider,_=provider_for(body=b"not JSON")
    assert provider.latest()["error_code"]=="invalid_json"
    provider,_=provider_for({})
    assert provider.latest()["status"]=="no_data" and provider.latest()["measurement"] is None
    provider,_=provider_for({"count":0,"readings":[]})
    assert provider.history()["status"]=="no_data" and provider.history()["returned_count"]==0
    provider,_=provider_for({"readings":"invalid"})
    assert provider.history()["error_code"]=="schema_invalid"
    provider,_=provider_for(body=b"x"*(MAX_RESPONSE_BYTES+1))
    assert provider.latest()["error_code"]=="response_too_large"


@pytest.mark.parametrize("age,expected", [(30,"fresh"),(121,"stale"),(-60,"future")])
def test_only_explicit_offsets_establish_age(age,expected):
    value=(NOW-timedelta(seconds=age)).astimezone(timezone(timedelta(hours=8))).isoformat()
    provider,_=provider_for({**LATEST,"timestamp":value})
    reading=provider.latest()["measurement"]
    assert reading["timestamp_quality"]=="offset_verified" and reading["freshness"]==expected
    assert reading["age_seconds"]==age


def test_history_invalid_rows_and_missing_fields_are_counted():
    provider,_=provider_for({"readings":[ROW,{**ROW,"humidity_pct":"bad"},{**ROW,"id":"invalid"}]})
    result=provider.history()
    assert result["status"]=="partial" and result["invalid_readings"]==2
    assert result["records"][1]["humidity_percent"] is None


@pytest.mark.parametrize("value", ["99:99:99", "bad", "2026-10-14", "0001-01-01T00:00:00+23:00"])
def test_invalid_timestamps_do_not_establish_freshness_or_crash(value):
    provider,_=provider_for({**LATEST,"timestamp":value})
    reading=provider.latest()["measurement"]
    assert reading["timestamp_quality"]=="invalid" and reading["freshness"]=="unknown"
    assert reading["measurement_timestamp_utc"] is None


def test_cache_single_flight_expiry_and_no_stale_fallback():
    calls=[]; clock=[0.0]
    def get(*args, **kwargs):
        calls.append(1);time.sleep(.02)
        if len(calls)>1: raise requests.ConnectionError()
        return FakeResponse(LATEST)
    provider=RenderSensorProvider(Settings(),get=get,utc_now=lambda:NOW,monotonic=lambda:clock[0])
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda _:provider.latest(),range(4)))
    assert len(calls)==1 and all(result["status"]=="available" for result in results)
    results[0]["measurement"]["temperature_c"]=0
    assert provider.latest()["measurement"]["temperature_c"]==29.2
    clock[0]=6
    assert provider.latest()["status"]=="unavailable" and provider.latest()["measurement"] is None


def test_configuration_rejects_embedded_credentials_without_network_calls():
    calls=[]
    provider=RenderSensorProvider(Settings(base_url="https://user:secret@example.com"),get=lambda *a,**kw:calls.append(1))
    assert provider.latest()["error_code"]=="configuration_invalid" and not calls


def test_all_api_routes_use_normalized_provider_and_validate_limits():
    class StubProvider:
        def latest(self): return provider_for(LATEST)[0].latest()
        def history(self,limit): return provider_for({"count":1,"readings":[ROW]})[0].history(limit)
    app.dependency_overrides[get_sensor_provider]=lambda:StubProvider()
    try:
        client=TestClient(app)
        assert client.get("/api/iot/latest").json()["measurement"]["temperature_c"]==29.2
        assert client.get("/api/iot/history?limit=1").json()["returned_count"]==1
        assert client.get("/api/iot/status").json()["sensor_freshness"]=="unknown"
        for limit in [0,201,-1,"bad"]:
            assert client.get(f"/api/iot/history?limit={limit}").status_code==422
    finally:
        app.dependency_overrides.pop(get_sensor_provider,None)
