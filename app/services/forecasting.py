"""
Forecasting service — wraps Mohsen's Prophet model.
Trains one Prophet model per bin, stores predictions in the forecasts table.
Designed to be called nightly via APScheduler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, date, timedelta

import numpy as np
import pandas as pd
from prophet import Prophet
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.models import Bin, Telemetry, Forecast

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
TRAIN_DAYS       = 70
FORECAST_HORIZON = 10   # days ahead to predict
MAPE_THRESHOLD   = 15.0  # % — warn if exceeded


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    mask = actual != 0
    if mask.sum() == 0:
        return 0.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


async def run_forecasts_for_all_bins() -> dict:
    """
    Main entry point called by scheduler or API endpoint.
    Returns a summary dict with per-bin results.
    """
    async with AsyncSessionLocal() as db:
        bins = (await db.execute(select(Bin))).scalars().all()
        if not bins:
            return {"status": "no_bins", "results": []}

        results = []
        for b in bins:
            try:
                result = await _forecast_bin(db, b.id)
                results.append(result)
            except Exception as exc:
                logger.error("Forecast failed for bin %s: %s", b.id, exc)
                results.append({"bin_id": b.id, "status": "error", "error": str(exc)})

        passed = sum(1 for r in results if r.get("status") == "ok" and r.get("mape", 999) <= MAPE_THRESHOLD)
        return {
            "status": "completed",
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "total_bins": len(bins),
            "passed_mape": passed,
            "results": results,
        }


async def _forecast_bin(db: AsyncSession, bin_id: str) -> dict:
    """Train Prophet on one bin's telemetry and save forecasts to DB."""

    # ── 1. Pull telemetry ──────────────────────────────────────────────
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRAIN_DAYS)
    rows = (
        await db.execute(
            select(Telemetry)
            .where(Telemetry.bin_id == bin_id, Telemetry.ts >= cutoff)
            .order_by(Telemetry.ts)
        )
    ).scalars().all()

    if len(rows) < 10:
        return {"bin_id": bin_id, "status": "skipped", "reason": "insufficient_data", "rows": len(rows)}

    # ── 2. Aggregate to daily fill_pct ────────────────────────────────
    df = pd.DataFrame(
        [{"ds": r.ts.date(), "y": r.fill_pct} for r in rows]
    )
    df = df.groupby("ds", as_index=False)["y"].mean()
    df["ds"] = pd.to_datetime(df["ds"])
    df = df.sort_values("ds").reset_index(drop=True)

    if len(df) < 7:
        return {"bin_id": bin_id, "status": "skipped", "reason": "insufficient_daily_rows", "rows": len(df)}

    # ── 3. Train / validate ───────────────────────────────────────────
    split_idx = max(int(len(df) * 0.7), len(df) - 30)
    train_df  = df.iloc[:split_idx]
    val_df    = df.iloc[split_idx:]

    model = Prophet(
        weekly_seasonality=True,
        daily_seasonality=False,
        yearly_seasonality=False,
        seasonality_mode="multiplicative",
        interval_width=0.95,
    )
    model.fit(train_df)

    # MAPE on validation window
    mape_val = 0.0
    if len(val_df) > 0:
        val_future   = model.make_future_dataframe(periods=len(val_df))
        val_forecast = model.predict(val_future)
        val_preds    = np.clip(val_forecast.iloc[split_idx:]["yhat"].values, 1.0, None)
        actual_vals  = val_df["y"].values
        min_len      = min(len(actual_vals), len(val_preds))
        mape_val     = _mape(actual_vals[:min_len], val_preds[:min_len])

    # ── 4. Re-train on full data, predict horizon ─────────────────────
    model_full = Prophet(
        weekly_seasonality=True,
        daily_seasonality=False,
        yearly_seasonality=False,
        seasonality_mode="multiplicative",
        interval_width=0.95,
    )
    model_full.fit(df)

    future   = model_full.make_future_dataframe(periods=FORECAST_HORIZON)
    forecast = model_full.predict(future)

    horizon_rows = forecast.tail(FORECAST_HORIZON)

    # ── 5. Persist to DB (delete old, insert new) ─────────────────────
    await db.execute(delete(Forecast).where(Forecast.bin_id == bin_id))

    today = date.today()
    new_forecasts = []
    for _, row in horizon_rows.iterrows():
        fdate = row["ds"].date()
        if fdate <= today:
            continue
        predicted_fill = float(np.clip(row["yhat"], 0, 100))
        # Estimate weight from fill (rough linear mapping: 100% fill ≈ 50 kg)
        predicted_weight = predicted_fill * 0.5

        # Recommend pickup when predicted fill >= 80%
        recommended_pickup = fdate
        if predicted_fill < 80:
            # Find first future date ≥ 80% in the horizon
            future_high = horizon_rows[
                (horizon_rows["ds"].dt.date > fdate) &
                (horizon_rows["yhat"] >= 80)
            ]
            if not future_high.empty:
                recommended_pickup = future_high.iloc[0]["ds"].date()

        new_forecasts.append(
            Forecast(
                bin_id=bin_id,
                forecast_date=fdate,
                predicted_fill_pct=round(predicted_fill, 2),
                predicted_weight_kg=round(predicted_weight, 2),
                recommended_pickup_date=recommended_pickup,
                model_version=f"prophet-v1-mape{mape_val:.1f}",
            )
        )

    db.add_all(new_forecasts)
    await db.commit()

    logger.info(
        "Forecast done: bin=%s  mape=%.2f%%  horizon=%d rows",
        bin_id, mape_val, len(new_forecasts),
    )
    return {
        "bin_id":          bin_id,
        "status":          "ok",
        "mape":            round(mape_val, 2),
        "pass":            mape_val <= MAPE_THRESHOLD,
        "forecast_rows":   len(new_forecasts),
        "training_rows":   len(df),
    }