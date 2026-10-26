"""
Endpoints:
  GET /              API information
  GET /health        Check if the API is running
  GET /meta          Available filter values
  GET /severity      Crashes by severity
  GET /factors/top   Most common contributing factors
  GET /trends        Crash trends over time
  GET /crashes       Crash records for maps

Run: py -m uvicorn api:app --reload
http://127.0.0.1:8000/docs
"""

from typing import Literal, Optional
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from processing import (
    SEVERITY_LABELS,
    SEVERITY_ORDER,
    apply_filters,
    get_data,
    severity_counts,
    temporal_patterns,
    top_factors,
)

app = FastAPI(
    title="TxDOT Crash Analytics API",
    description="Crash data for the Lubbock district, 2020-2026.",
    version="1.0.0",
)

# Load the data when the app starts
DATA: pd.DataFrame = get_data()
VALID_COUNTIES = sorted(DATA["county"].dropna().unique())
VALID_ROAD_CLASSES = sorted(DATA["road_class"].dropna().unique())


class Filters:
    # Common filters used by the endpoints

    def __init__(
        self,
        county: Optional[str] = Query(
            None,
            description="County name, e.g. LUBBOCK",
        ),
        year: Optional[int] = Query(
            None,
            ge=2000,
            le=2100,
            description="Crash year, e.g. 2023",
        ),
        severity: Optional[str] = Query(
            None,
            description="K, A, B, or C",
        ),
        road_class: Optional[str] = Query(
            None,
            description="Road class, e.g. CITY STREET",
        ),
    ):
        self.county = county
        self.year = year
        self.severity = severity
        self.road_class = road_class

    def as_dict(self) -> dict:
        # Return only the filters that were provided
        return {k: v for k, v in vars(self).items() if v is not None}


def filtered_data(f: Filters = Depends()) -> pd.DataFrame:
    # Check the filters and return the matching crashes
    if f.severity and f.severity.strip().upper() not in SEVERITY_ORDER:
        raise HTTPException(422, f"severity debe ser uno de {SEVERITY_ORDER}")
    if f.county and f.county.strip().upper() not in VALID_COUNTIES:
        raise HTTPException(422, f"county desconocido. Opciones: {VALID_COUNTIES}")
    if f.road_class and f.road_class.strip().upper() not in VALID_ROAD_CLASSES:
        raise HTTPException(422, f"road_class desconocido. Opciones: {VALID_ROAD_CLASSES}")

    return apply_filters(DATA, f.county, f.year, f.severity, f.road_class)


@app.get("/", tags=["info"])
def index():
    # Return the available endpoints
    return {
        "service": "TxDOT Crash Analytics API",
        "docs": "/docs",
        "endpoints": ["/health", "/meta", "/severity", "/factors/top", "/trends", "/crashes"],
    }


@app.get("/health", tags=["info"])
def health():
    # Check that the API is running
    return {"status": "ok", "crashes_loaded": len(DATA)}


@app.get("/meta", tags=["info"])
def meta():
    # Return the available filters and date range
    return {
        "total_crashes": len(DATA),
        "date_range": {
            "start": DATA["date"].min().strftime("%Y-%m-%d"),
            "end": DATA["date"].max().strftime("%Y-%m-%d"),
        },
        "years": sorted(int(y) for y in DATA["year"].unique()),
        "counties": VALID_COUNTIES,
        "road_classes": VALID_ROAD_CLASSES,
        "severities": [
            {"code": s, "label": SEVERITY_LABELS[s]}
            for s in SEVERITY_ORDER
        ],
    }


@app.get("/severity", tags=["metrics"])
def severity(df: pd.DataFrame = Depends(filtered_data), f: Filters = Depends()):
    # Count crashes for each severity level
    counts = severity_counts(df)
    total = sum(counts.values())

    return {
        "filters": f.as_dict(),
        "total": total,
        "data": [
            {
                "severity": s,
                "label": SEVERITY_LABELS[s],
                "crashes": counts[s],
                "pct": round(100 * counts[s] / total, 1) if total else 0.0,
            }
            for s in SEVERITY_ORDER
        ],
    }


@app.get("/factors/top", tags=["metrics"])
def factors_top(
    n: int = Query(
        5,
        ge=1,
        le=25,
        description="Number of factors to return",
    ),
    df: pd.DataFrame = Depends(filtered_data),
    f: Filters = Depends(),
):
    # Return the most common contributing factors
    return {
        "filters": f.as_dict(),
        "total_crashes": len(df),
        "data": top_factors(df, n),
    }


@app.get("/trends", tags=["metrics"])
def trends(
    group_by: Literal["year", "month", "weekday", "hour"] = Query(
        "year",
        description="Time period to group by",
    ),
    df: pd.DataFrame = Depends(filtered_data),
    f: Filters = Depends(),
):
    # Group crashes by year, month, weekday, or hour
    series = temporal_patterns(df)[f"by_{group_by}"]

    return {
        "filters": f.as_dict(),
        "group_by": group_by,
        "data": [
            {"period": k, "crashes": v}
            for k, v in series.items()
        ],
    }


@app.get("/crashes", tags=["records"])
def crashes(
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Number of records per page",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of records to skip",
    ),
    with_coords_only: bool = Query(
        False,
        description="Return only crashes with valid coordinates",
    ),
    df: pd.DataFrame = Depends(filtered_data),
    f: Filters = Depends(),
):
    # Return a page of crash records
    if with_coords_only:
        df = df.dropna(subset=["lat", "lon"])

    page = df.sort_values(["date", "crash_id"]).iloc[offset:offset + limit]

    records = [
        {
            "crash_id": row.crash_id,
            "date": row.date.strftime("%Y-%m-%d"),
            "hour": None if pd.isna(row.hour) else int(row.hour),
            "severity": row.severity,
            "county": row.county,
            "road_class": None if pd.isna(row.road_class) else row.road_class,
            "lat": None if pd.isna(row.lat) else float(row.lat),
            "lon": None if pd.isna(row.lon) else float(row.lon),
            "factors": (
                []
                if pd.isna(row.factors_raw)
                else [x.strip() for x in row.factors_raw.split(";")]
            ),
        }
        for row in page.itertuples()
    ]

    return {
        "filters": f.as_dict(),
        "total": len(df),
        "limit": limit,
        "offset": offset,
        "data": records,
    }


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    # Return the dashboard page
    return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
