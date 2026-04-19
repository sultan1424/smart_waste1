"""
Fixed routing endpoint — handles BN-001 style bin IDs from DB.
The 422 was caused by bins having no telemetry data, so flagged list was empty.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import Bin, Telemetry, User
from app.core.deps import get_current_user, require_roles
from app.services.forecasting import run_forecasts_for_all_bins
from app.services.routing import optimize_route

router = APIRouter(tags=["ml"])


class RouteOptimizeRequest(BaseModel):
    flagged_bin_ids: Optional[list[str]] = None
    priority_map:    Optional[dict[str, int]] = None
    use_ortools:     bool = True
    solver_time_limit: int = 30
    fill_threshold:  float = 80.0   # flag bins >= this fill %


@router.post("/forecasts/run")
async def trigger_forecasts(
    current_user: User = Depends(require_roles("regulator")),
):
    result = await run_forecasts_for_all_bins()
    return result


@router.post("/routes/optimize")
async def optimize_pickup_route(
    req: RouteOptimizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("collector", "regulator")),
):
    # Load all bins
    bins_db = (await db.execute(select(Bin))).scalars().all()
    if not bins_db:
        raise HTTPException(404, detail="No bins found in database")

    bins_for_optimizer = [
        {"id": b.id, "name": b.name, "lat": b.lat, "lng": b.lng}
        for b in bins_db
    ]

    # Get latest telemetry per bin
    fill_map: dict[str, float] = {}
    for b in bins_db:
        latest = (
            await db.execute(
                select(Telemetry)
                .where(Telemetry.bin_id == b.id)
                .order_by(desc(Telemetry.ts))
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest:
            fill_map[b.id] = latest.fill_pct

    # Determine flagged bins
    flagged = req.flagged_bin_ids
    if flagged is None:
        # Auto-flag by fill threshold
        flagged = [bid for bid, fill in fill_map.items() if fill >= req.fill_threshold]

        if not flagged:
            # Nothing above threshold — flag top 60% by fill level
            sorted_bins = sorted(fill_map.items(), key=lambda x: x[1], reverse=True)
            top_n = max(1, int(len(sorted_bins) * 0.6))
            flagged = [bid for bid, _ in sorted_bins[:top_n]]

        if not flagged:
            # No telemetry at all — flag all bins
            flagged = [b.id for b in bins_db]

    # Validate flagged IDs exist
    valid_ids = {b.id for b in bins_db}
    flagged = [f for f in flagged if f in valid_ids]

    if not flagged:
        raise HTTPException(
            400,
            detail=f"No valid bins to flag. Available bin IDs: {list(valid_ids)[:5]}..."
        )

    # Build priority map from fill levels
    priority_map = req.priority_map
    if priority_map is None:
        priority_map = {}
        for bid in flagged:
            fill = fill_map.get(bid, 50.0)
            priority_map[bid] = 3 if fill >= 90 else (2 if fill >= 70 else 1)

    result = optimize_route(
        bins=bins_for_optimizer,
        flagged_bin_ids=flagged,
        priority_map=priority_map,
        use_ortools=req.use_ortools,
        solver_time_limit=req.solver_time_limit,
    )

    if "error" in result:
        raise HTTPException(422, detail=f"Optimizer failed: {result['error']}")

    # Send route 