import time
import hashlib
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Bin, Telemetry, Pickup, Forecast, User
from app.schemas.schemas import (
    HealthResponse, BinListItem, BinDetail, TelemetryRow,
    PickupRow, ForecastRow, ReportResponse, TelemetrySummary
)
from app.services.report_service import get_30day_report
from app.core.deps import get_current_user, require_roles
from app.core.security import encrypt_value, decrypt_value

router = APIRouter()

# ── Helpers ───────────────────────────────────────────────────────────────

def _hash(value: str) -> str:
    """SHA-256 hash for fast indexed lookup."""
    return hashlib.sha256(value.lower().encode()).hexdigest()

def _decrypt_bin(b: Bin) -> dict:
    """Decrypt sensitive Bin fields before returning to client."""
    # Handle both old (location_name) and new (location_name_encrypted) schema
    if hasattr(b, 'location_name_encrypted') and b.location_name_encrypted:
        location = decrypt_value(b.location_name_encrypted)
    elif hasattr(b, 'location_name') and b.location_name:
        location = b.location_name
    else:
        location = "Unknown"
    return {
        "id": b.id,
        "name": b.name,
        "location_name": location,
        "lat": b.lat,
        "lng": b.lng,
        "status": b.status.value,
        "installed_at": b.installed_at,
    }

def _get_restaurant_id(user: User) -> str | None:
    return user.restaurant_id or None

# ── Health (public) ───────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="0.1.0-ppr")

# ── Bins ──────────────────────────────────────────────────────────────────

@router.get("/bins", response_model=list[BinListItem])
async def list_bins(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bins_q = select(Bin).order_by(Bin.id)

    # RBAC: restaurant sees only its own bins
    if current_user.role.value == "restaurant":
        restaurant_id = _get_restaurant_id(current_user)
        if restaurant_id:
            owned = restaurant_id.split(",")
            bins_q = bins_q.where(Bin.id.in_(owned))

    bins = (await db.execute(bins_q)).scalars().all()
    result = []
    for b in bins:
        latest = (await db.execute(
            select(Telemetry).where(Telemetry.bin_id == b.id)
            .order_by(desc(Telemetry.ts)).limit(1)
        )).scalar_one_or_none()

        summary = TelemetrySummary(
            ts=latest.ts if latest else None,
            fill_pct=latest.fill_pct if latest else None,
            weight_kg=latest.weight_kg if latest else None,
            temp_c=latest.temp_c if latest else None,
            battery_v=latest.battery_v if latest else None,
        ) if latest else None

        bin_data = _decrypt_bin(b)
        result.append(BinListItem(
            id=bin_data["id"],
            name=bin_data["name"],
            location_name=bin_data["location_name"],  # decrypted
            lat=bin_data["lat"],
            lng=bin_data["lng"],
            status=bin_data["status"],
            latest_telemetry=summary,
        ))
    return result


@router.get("/bins/{bin_id}", response_model=BinDetail)
async def get_bin(
    bin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # RBAC check for restaurant role
    if current_user.role.value == "restaurant":
        restaurant_id = _get_restaurant_id(current_user)
        owned = (restaurant_id or "").split(",")
        if bin_id not in owned:
            raise HTTPException(403, detail="Access denied to this bin")

    b = await db.get(Bin, bin_id)
    if not b:
        raise HTTPException(404, detail=f"Bin {bin_id} not found")

    latest = (await db.execute(
        select(Telemetry).where(Telemetry.bin_id == bin_id)
        .order_by(desc(Telemetry.ts)).limit(1)
    )).scalar_one_or_none()

    summary = TelemetrySummary(
        ts=latest.ts if latest else None,
        fill_pct=latest.fill_pct if latest else None,
        weight_kg=latest.weight_kg if latest else None,
        temp_c=latest.temp_c if latest else None,
        battery_v=latest.battery_v if latest else None,
    ) if latest else None

    bin_data = _decrypt_bin(b)
    return BinDetail(
        id=bin_data["id"],
        name=bin_data["name"],
        location_name=bin_data["location_name"],  # decrypted
        lat=bin_data["lat"],
        lng=bin_data["lng"],
        status=bin_data["status"],
        installed_at=bin_data["installed_at"],
        latest_telemetry=summary,
    )


@router.get("/bins/{bin_id}/telemetry", response_model=list[TelemetryRow])
async def get_telemetry(
    bin_id: str,
    from_: Optional[datetime] = Query(None, alias="from"),
    to:    Optional[datetime] = Query(None),
    limit: int = Query(500, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value == "restaurant":
        restaurant_id = _get_restaurant_id(current_user)
        owned = (restaurant_id or "").split(",")
        if bin_id not in owned:
            raise HTTPException(403, detail="Access denied to this bin")

    b = await db.get(Bin, bin_id)
    if not b:
        raise HTTPException(404, detail=f"Bin {bin_id} not found")

    filters = [Telemetry.bin_id == bin_id]
    if from_: filters.append(Telemetry.ts >= from_)
    if to:    filters.append(Telemetry.ts <= to)

    rows = (await db.execute(
        select(Telemetry).where(and_(*filters))
        .order_by(Telemetry.ts).limit(limit)
    )).scalars().all()
    return rows


@router.get("/pickups/today", response_model=list[PickupRow])
async def pickups_today(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("collector", "regulator", "restaurant")),
):
    today     = date.today()
    day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    day_end   = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)

    q = select(Pickup).where(Pickup.scheduled_at.between(day_start, day_end))

    # Restaurant only sees pickups for its bins
    if current_user.role.value == "restaurant":
        restaurant_id = _get_restaurant_id(current_user)
        owned = (restaurant_id or "").split(",")
        q = q.where(Pickup.bin_id.in_(owned))

    rows = (await db.execute(q.order_by(Pickup.scheduled_at))).scalars().all()
    return rows


@router.get("/forecasts/{bin_id}", response_model=list[ForecastRow])
async def get_forecasts(
    bin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value == "restaurant":
        restaurant_id = _get_restaurant_id(current_user)
        owned = (restaurant_id or "").split(",")
        if bin_id not in owned:
            raise HTTPException(403, detail="Access denied to this bin")

    b = await db.get(Bin, bin_id)
    if not b:
        raise HTTPException(404, detail=f"Bin {bin_id} not found")

    rows = (await db.execute(
        select(Forecast).where(Forecast.bin_id == bin_id)
        .order_by(desc(Forecast.created_at), Forecast.forecast_date).limit(10)
    )).scalars().all()
    return rows


@router.get("/reports/30days", response_model=ReportResponse)
async def report_30days(
    bin_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("restaurant", "regulator", "collector")),
):
    # Restaurant can only report on its own bins
    if current_user.role.value == "restaurant":
        restaurant_id = _get_restaurant_id(current_user)
        owned = (restaurant_id or "").split(",")
        if bin_id and bin_id not in owned:
            raise HTTPException(403, detail="Access denied to this bin's report")
        if not bin_id and owned:
            bin_id = owned[0]

    t0 = time.perf_counter()
    daily_rows, pickup_count = await get_30day_report(db, bin_id)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    today      = date.today()
    start_date = today - __import__("datetime").timedelta(days=30)

    return ReportResponse(
        bin_id=bin_id,
        period_start=start_date,
        period_end=today,
        pickup_count=pickup_count,
        daily_rows=daily_rows,
        server_elapsed_ms=elapsed_ms,
    )