import time
from datetime import date, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.schemas import DailyReportRow, ReportResponse

REPORT_SQL_ALL = text("""
    SELECT
        DATE(ts AT TIME ZONE 'UTC') AS day,
        AVG(fill_pct)::numeric(6,2) AS avg_fill_pct,
        MAX(fill_pct)::numeric(6,2) AS max_fill_pct,
        AVG(temp_c)::numeric(6,2)   AS avg_temp_c,
        SUM(weight_kg)::numeric(10,3) AS total_weight_kg,
        COUNT(*) AS reading_count
    FROM telemetry
    WHERE ts >= :start_ts AND ts < :end_ts
    GROUP BY DATE(ts AT TIME ZONE 'UTC')
    ORDER BY day
""")

REPORT_SQL_BIN = text("""
    SELECT
        DATE(ts AT TIME ZONE 'UTC') AS day,
        AVG(fill_pct)::numeric(6,2) AS avg_fill_pct,
        MAX(fill_pct)::numeric(6,2) AS max_fill_pct,
        AVG(temp_c)::numeric(6,2)   AS avg_temp_c,
        SUM(weight_kg)::numeric(10,3) AS total_weight_kg,
        COUNT(*) AS reading_count
    FROM telemetry
    WHERE ts >= :start_ts AND ts < :end_ts AND bin_id = :bin_id
    GROUP BY DATE(ts AT TIME ZONE 'UTC')
    ORDER BY day
""")

PICKUP_SQL_ALL = text("""
    SELECT COUNT(*) AS cnt FROM pickups
    WHERE scheduled_at >= :start_ts AND scheduled_at < :end_ts
""")

PICKUP_SQL_BIN = text("""
    SELECT COUNT(*) AS cnt FROM pickups
    WHERE scheduled_at >= :start_ts AND scheduled_at < :end_ts AND bin_id = :bin_id
""")


async def get_30day_report(db: AsyncSession, bin_id: str | None, days: int = 30):
    end_date   = date.today()
    start_date = end_date - timedelta(days=days)
    params = {"start_ts": start_date, "end_ts": end_date + timedelta(days=1)}

    if bin_id:
        params["bin_id"] = bin_id
        result        = await db.execute(REPORT_SQL_BIN,   params)
        pickup_result = await db.execute(PICKUP_SQL_BIN,   params)
    else:
        result        = await db.execute(REPORT_SQL_ALL,   params)
        pickup_result = await db.execute(PICKUP_SQL_ALL,   params)

    rows = [
        DailyReportRow(
            day             = r.day,
            avg_fill_pct    = float(r.avg_fill_pct    or 0),
            max_fill_pct    = float(r.max_fill_pct    or 0),
            avg_temp_c      = float(r.avg_temp_c      or 0),
            total_weight_kg = float(r.total_weight_kg or 0),
            reading_count   = int(r.reading_count),
        )
        for r in result.fetchall()
    ]

    pickup_count = pickup_result.scalar() or 0
    return rows, pickup_count