from __future__ import annotations

from typing import Literal

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import Response

from backend.services import datasets as ds

router = APIRouter(prefix="/api", tags=["Phase 2 dashboard"])


@router.get("/health")
def health():
    return {"status": "ok", "phase": 2}


@router.get("/himawari/summary")
def satellite_summary():
    return ds.summary(*ds.dataset("himawari"))


def history(kind, start, end, page, page_size, max_points, bands=None, statistic="mean"):
    frame, metadata = ds.dataset(kind)
    frame = ds.filtered(frame, start, end)
    if kind == "himawari":
        chosen = bands.split(",") if bands else list(ds.BANDS)
        if any(band not in ds.BANDS for band in chosen):
            ds.fail("band_invalid", "Supported bands are B08, B13, B14, and B15.")
        stats = ("mean", "min", "max") if statistic == "all" else (statistic,)
        columns = [f"{band}_{stat}_K" for band in dict.fromkeys(chosen) for stat in stats if f"{band}_{stat}_K" in frame]
        frame = frame[["timestamp", *columns]]
    points, aggregation = ds.chart_data(frame, max_points)
    total = len(frame)
    return {"metadata": metadata, "columns": list(frame.columns), "total": total, "page": page, "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "records": ds.json_records(frame.iloc[(page - 1)*page_size:page*page_size]),
            "chart": points, "chart_aggregation": aggregation}


@router.get("/himawari/history")
def satellite_history(start: str | None = Query(None, max_length=40), end: str | None = Query(None, max_length=40),
                      page: int = Query(1, ge=1, le=100000), page_size: int = Query(100, ge=1, le=1000),
                      max_points: int = Query(800, ge=50, le=2000), bands: str | None = Query(None, max_length=60),
                      statistic: Literal["mean", "min", "max", "all"] = "mean"):
    return history("himawari", start, end, page, page_size, max_points, bands, statistic)


@router.get("/weather/history")
def weather_history(start: str | None = Query(None, max_length=40), end: str | None = Query(None, max_length=40),
                    page: int = Query(1, ge=1, le=100000), page_size: int = Query(100, ge=1, le=1000), max_points: int = Query(800, ge=50, le=2000)):
    return history("weather", start, end, page, page_size, max_points)


@router.get("/heat-index/history")
def heat_index_history(start: str | None = Query(None, max_length=40), end: str | None = Query(None, max_length=40),
                       page: int = Query(1, ge=1, le=100000), page_size: int = Query(100, ge=1, le=1000), max_points: int = Query(800, ge=50, le=2000)):
    return history("heat-index", start, end, page, page_size, max_points)


@router.get("/himawari/quality")
def satellite_quality():
    frame, metadata = ds.dataset("himawari")
    periods = ds.missing_periods(frame)
    reports = []
    for name in ("daily_coverage.csv", "missing_hours.csv", "time_gaps.csv"):
        path = ds.data_root() / "data_coverage_results" / name
        if path.is_file():
            try:
                saved = ds.read_csv(path)
                reports.append({"name": name, "rows": len(saved), "status": "archived", "note": "Existing report from an earlier pipeline run; live quality metrics above are authoritative."})
            except Exception:
                reports.append({"name": name, "status": "unavailable"})
    daily = frame.assign(date=frame["timestamp"].dt.floor("D")).groupby("date")["timestamp"].nunique().reset_index(name="observed_hours")
    return {**ds.summary(frame, metadata), "missing_periods": periods[:500], "periods_truncated": len(periods) > 500,
            "daily_observations": ds.json_records(daily.tail(1000)), "existing_reports": reports}


def csv_response(frame: pd.DataFrame, filename: str):
    return Response(frame.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/himawari/export")
def satellite_export(start: str | None = Query(None, max_length=40), end: str | None = Query(None, max_length=40)):
    frame, _ = ds.dataset("himawari")
    frame = ds.filtered(frame, start, end)
    if len(frame) > 100000:
        ds.fail("export_too_large", "Narrow the date range to export at most 100,000 rows.")
    return csv_response(frame, "himawari_history.csv")


@router.get("/himawari/missing-hours.csv")
def missing_export():
    frame, _ = ds.dataset("himawari")
    periods = ds.missing_periods(frame)
    if sum(period["hours"] for period in periods) > 100000:
        ds.fail("export_too_large", "The missing-hour report exceeds 100,000 hours.")
    hours = [timestamp.isoformat() for period in periods for timestamp in pd.date_range(period["start"], period["end"], freq="h")]
    return csv_response(pd.DataFrame({"missing_timestamp_utc": hours}), "missing_hours_live.csv")


@router.get("/himawari/reports/{report}")
def coverage_report(report: Literal["daily_coverage.csv", "missing_hours.csv", "time_gaps.csv"]):
    frame = ds.read_csv(ds.data_root() / "data_coverage_results" / report)
    return csv_response(frame.head(100000), report)


