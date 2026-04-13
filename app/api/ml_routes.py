"""
New API routes for:
  POST /api/v1/forecasts/run          — trigger Prophet forecasts (admin/regulator)
  GET  /api/v1/forecasts/{bin_id}     — get stored forecasts (already exists, kept)
  POST /api/v1/routes/optimize        — run route optimizer (collector/regulator)
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Bin, Telemetry, User
from app.core.deps import get_current_user, require_roles
from app.services.forecasting import run_forecasts_for_all_bins
from app.services.routing import optimize_route

router = APIRouter(tags=["ml"])


# ── Schemas ───────────────────────────────────────────────────────────────

class RouteOptimizeRequest(BaseModel):
    flagged_bin_ids: Optional[list[str]] = None   # if None → auto-flag bins ≥ 80% fill
    priority_map:    Optional[dict[str, int]] = None
    use_ortools:     bool = True
    solver_time_limit: int = 30                    # seconds


# ── Forecast endpoints ────────────────────────────────────────────────────

@router.post("/forecasts/run")
async def trigger_forecasts(
    current_user: User = Depends(require_roles("regulator")),
):
    """
    Manually trigger Prophet forecasting for all bins.
    Normally called by the nightly scheduler.
    Restricted to regulators.
    """
    result = await run_forecasts_for_all_bins()
    return result


# ── Route optimization endpoint ───────────────────────────────────────────

@router.post("/routes/optimize")
async def optimize_pickup_route(
    req: RouteOptimizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("collector", "regulator")),
):
    """
    Run Aseel's OR-Tools route optimizer on-demand.
    If flagged_bin_ids is not provided, auto-flags all bins with fill >= 80%.
    """
    # Load all bins with their latest telemetry
    bins_db = (await db.execute(select(Bin))).scalars().all()
    if not bins_db:
        raise HTTPException(404, detail="No bins found")

    # Build bin list for optimizer
    bins_for_optimizer = [
        {"id": b.id, "name": b.name, "lat": b.lat, "lng": b.lng}
        for b in bins_db
    ]

    # Auto-detect flagged bins if not provided
    flagged = req.flagged_bin_ids
    if flagged is None:
        # Flag bins where latest fill >= 80%
        from sqlalchemy import func, desc
        from app.models.models import Telemetry as Tel

        # Get latest fill per bin
        flagged = []
        for b in bins_db:
            latest = (
                await db.execute(
                    select(Tel)
                    .where(Tel.bin_id == b.id)
                    .order_by(desc(Tel.ts))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if latest and latest.fill_pct >= 80:
                flagged.append(b.id)

        if not flagged:
            # If nothing is ≥80%, flag top 60% by fill
            fill_data = []
            for b in bins_db:
                latest = (
                    await db.execute(
                        select(Tel)
                        .where(Tel.bin_id == b.id)
                        .order_by(desc(Tel.ts))
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest:
                    fill_data.append((b.id, latest.fill_pct))
            fill_data.sort(key=lambda x: x[1], reverse=True)
            top_n = max(1, int(len(fill_data) * 0.6))
            flagged = [bid for bid, _ in fill_data[:top_n]]

    if not flagged:
        raise HTTPException(400, detail="No bins to flag for pickup")

    # Build priority map from fill level if not provided
    priority_map = req.priority_map
    if priority_map is None:
        from sqlalchemy import desc as _desc
        from app.models.models import Telemetry as Tel2
        priority_map = {}
        for b in bins_db:
            if b.id in flagged:
                latest = (
                    await db.execute(
                        select(Tel2)
                        .where(Tel2.bin_id == b.id)
                        .order_by(_desc(Tel2.ts))
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest:
                    # Priority 3=high(≥90%), 2=medium(≥70%), 1=low
                    fill = latest.fill_pct
                    priority_map[b.id] = 3 if fill >= 90 else (2 if fill >= 70 else 1)

    result = optimize_route(
        bins=bins_for_optimizer,
        flagged_bin_ids=flagged,
        priority_map=priority_map,
        use_ortools=req.use_ortools,
        solver_time_limit=req.solver_time_limit,
    )

    if "error" in result:
        raise HTTPException(422, detail=result["error"])

    return result