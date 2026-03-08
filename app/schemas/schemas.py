from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel

# ── Bin ───────────────────────────────────────────────────────────────────

class TelemetrySummary(BaseModel):
    ts         : Optional[datetime]
    fill_pct   : Optional[float]
    weight_kg  : Optional[float]
    temp_c     : Optional[float]
    battery_v  : Optional[float]

class BinListItem(BaseModel):
    id            : str
    name          : str
    location_name : str
    lat           : float
    lng           : float
    status        : str
    latest_telemetry: Optional[TelemetrySummary] = None

    model_config = {"from_attributes": True}

class BinDetail(BinListItem):
    installed_at: datetime

    model_config = {"from_attributes": True}

# ── Telemetry ─────────────────────────────────────────────────────────────

class TelemetryRow(BaseModel):
    id          : int
    bin_id      : str
    ts          : datetime
    fill_pct    : float
    weight_kg   : float
    temp_c      : float
    battery_v   : float
    signal_rssi : Optional[float] = None

    model_config = {"from_attributes": True}

# ── Pickup ────────────────────────────────────────────────────────────────

class PickupRow(BaseModel):
    id           : int
    bin_id       : str
    scheduled_at : datetime
    window_start : datetime
    window_end   : datetime
    route_id     : str
    priority     : str
    status       : str

    model_config = {"from_attributes": True}

# ── Forecast ──────────────────────────────────────────────────────────────

class ForecastRow(BaseModel):
    id                     : int
    bin_id                 : str
    forecast_date          : date
    predicted_fill_pct     : float
    predicted_weight_kg    : float
    recommended_pickup_date: date
    model_version          : str

    model_config = {"from_attributes": True}

# ── Report ────────────────────────────────────────────────────────────────

class DailyReportRow(BaseModel):
    day             : date
    avg_fill_pct    : float
    max_fill_pct    : float
    avg_temp_c      : float
    total_weight_kg : float
    reading_count   : int

class ReportResponse(BaseModel):
    bin_id           : Optional[str]
    period_start     : date
    period_end       : date
    pickup_count     : int
    daily_rows       : list[DailyReportRow]
    server_elapsed_ms: float   # PPR evidence — query instrumentation

# ── Generic ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status : str
    version: str