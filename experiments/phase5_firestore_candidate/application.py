from __future__ import annotations

from datetime import datetime,timezone
import hmac
import threading

from flask import Flask,jsonify,render_template,request
from werkzeug.exceptions import BadRequest,RequestEntityTooLarge

from inference import ForecastEngine
from storage.base import ConflictError,Reading,StorageUnavailable,finite_number
from storage.factory import Settings,make_storage

LABEL="Experimental IoT forecast — unvalidated"


def display_latest(reading):
    from legacy_logic import get_pagasa_advisory
    if reading is None:
        return {"timestamp":"--:--:--","temperature":"--","humidity":"--","current_hi":"--","forecast_hi":"--",
                "cur_category":"WAITING...","cur_action":"Awaiting sensor readings.","cur_color":"#64748b",
                "fore_category":"UNAVAILABLE","fore_action":"No validated forecast available.","fore_color":"#64748b",
                "status":"No persisted readings","measured_at_utc":None,"received_at_utc":None,
                "forecast_label":LABEL,"forecast_horizon_verified":False,"sensor_freshness":"unknown"}
    current=get_pagasa_advisory(reading.heat_index_c)
    forecast=get_pagasa_advisory(reading.experimental_forecast_c) if reading.experimental_forecast_c is not None else ("UNAVAILABLE","Forecast unavailable; current heat index is not substituted.","#64748b")
    return {"timestamp":reading.measured_at_utc.isoformat() if reading.measured_at_utc else reading.legacy_timestamp_raw,
            "temperature":f"{reading.temperature_c:.1f}","humidity":f"{reading.humidity_percent:.1f}",
            "current_hi":f"{reading.heat_index_c:.1f}","forecast_hi":f"{reading.experimental_forecast_c:.1f}" if reading.experimental_forecast_c is not None else None,
            "cur_category":current[0],"cur_action":current[1],"cur_color":current[2],
            "fore_category":forecast[0],"fore_action":forecast[1],"fore_color":forecast[2],
            "status":"Stored telemetry available; measurement freshness unverified",
            "measured_at_utc":reading.measured_at_utc.isoformat() if reading.measured_at_utc else None,
            "received_at_utc":reading.received_at_utc.isoformat() if reading.received_at_utc else None,
            "legacy_timestamp_raw":reading.legacy_timestamp_raw,"source_record_id":reading.source_record_id,
            "timestamp_quality":"offset_bearing_device_time" if reading.measured_at_utc else "timezone_unverified" if reading.legacy_timestamp_raw else "missing_measurement_time",
            "sensor_freshness":"unknown","forecast_label":LABEL,"forecast_horizon_verified":False,
            "advisory_status":"legacy classification; unvalidated boundary defects retained"}


def history_row(reading):
    return {"id":reading.source_record_id,"timestamp":reading.measured_at_utc.isoformat() if reading.measured_at_utc else reading.legacy_timestamp_raw,
            "temperature_c":reading.temperature_c,"humidity_pct":reading.humidity_percent,"heat_index_c":reading.heat_index_c,
            "forecast_3hr_c":reading.experimental_forecast_c,"pagasa_advisory":reading.advisory,
            "received_at_utc":reading.received_at_utc.isoformat() if reading.received_at_utc else None,
            "measured_at_utc":reading.measured_at_utc.isoformat() if reading.measured_at_utc else None,
            "forecast_label":LABEL,"forecast_horizon_verified":False}


def create_app(settings=None,*,provider=None,engine=None,clock=None):
    configuration=settings or Settings.from_env()
    if configuration.auth_mode not in {"off","optional","required"}:
        raise ValueError("DEVICE_AUTH_MODE must be off, optional, or required.")
    if configuration.auth_mode in {"optional","required"} and not configuration.device_token:
        raise ValueError("A server-side device token must be configured before enabling authentication.")
    app=Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"]=8192
    store=provider if provider is not None else make_storage(configuration)
    forecasting=engine if engine is not None else ForecastEngine(configuration.model_path)
    utc_now=clock or (lambda:datetime.now(timezone.utc))
    lock=threading.Lock()
    app.extensions["storage_provider"]=store
    app.extensions["forecast_engine"]=forecasting

    @app.errorhandler(StorageUnavailable)
    def storage_error(error):
        return jsonify(status="error",code="storage_unavailable",message=str(error),write_acknowledged=False),503

    @app.errorhandler(ConflictError)
    def conflict(error):
        return jsonify(status="error",code="storage_conflict",message=str(error)),409

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return jsonify(status="error",message="Telemetry body exceeds 8192 bytes."),413

    @app.post("/api/telemetry")
    def telemetry():
        if configuration.auth_mode!="off":
            supplied=request.headers.get("X-Device-Token","")
            if configuration.auth_mode=="required" or supplied:
                if len(supplied)>512 or not hmac.compare_digest(supplied.encode(),configuration.device_token.encode()):
                    return jsonify(status="error",message="Device authentication failed."),401
        try:
            payload=request.get_json(force=True)
            if not isinstance(payload,dict): raise ValueError("A JSON object is required.")
            temperature=finite_number(payload.get("temperature"),"temperature",-90,60)
            humidity=finite_number(payload.get("humidity"),"humidity",0,100)
        except (ValueError,BadRequest):
            return jsonify(status="error",message="Provide finite temperature (−90–60°C) and humidity (0–100%); booleans are invalid."),400
        with lock:
            current,prediction,sample=forecasting.preview(temperature,humidity)
            from legacy_logic import get_pagasa_advisory
            advisory=get_pagasa_advisory(prediction if prediction is not None else current)[0]
            reading=Reading(configuration.lineage,None,"legacy-esp32-unverified",temperature,humidity,current,prediction,
                            advisory,None,None,utc_now(),None,"esp32")
            saved=store.insert(reading)  # success is impossible before the selected backend acknowledges
            if saved.source_record_id is None:
                raise StorageUnavailable("Storage returned no acknowledged record identifier.")
            forecasting.commit(sample)
        return jsonify({"status":"success","db_logged":True}),200

    @app.get("/api/v1/latest")
    def latest():
        return jsonify(display_latest(store.latest()))

    @app.get("/api/v1/history")
    def history():
        try:
            limit=int(request.args.get("limit","20"))
            page=store.history(limit,request.args.get("cursor"))
        except ValueError:
            return jsonify(status="error",message="Invalid limit (1–200) or history cursor."),400
        return jsonify(count=len(page.readings),readings=[history_row(row) for row in page.readings],next_cursor=page.next_cursor)

    @app.get("/")
    def index(): return render_template("dashboard.html")

    @app.get("/logs")
    def logs():
        return render_template("logs.html",readings=[history_row(row) for row in store.history(100).readings])

    return app
