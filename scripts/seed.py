"""
Seed script — configurable via constants at the top.
Uses SYNC_DATABASE_URL (psycopg2) for simplicity.

⚠️  MOCK/PLACEHOLDER data for PPR purposes:
    - Telemetry values simulate realistic IoT sensor patterns
    - Forecasts are random (placeholder for the CS/ISE forecasting module)
    - Pickup routes are placeholder (placeholder for the scheduling module)
"""
import os, sys, random, math
from datetime import datetime, timedelta, timezone, date
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import settings
from app.models.models import Base, Bin, Telemetry, Pickup, Forecast, BinStatus, PickupPriority, PickupStatus

# ── Configuration ──────────────────────────────────────────────────────────
BIN_COUNT          = 20
DAYS               = 30
INTERVAL_MINUTES   = 120    # set to 5 for max density (~864K rows); 30 is ~144K
SKIP_PROB          = 0.03  # probability of a missing reading (simulates dropped packets)
FORECAST_HORIZON   = 10    # days ahead
ROUTES             = ["R-NORTH", "R-SOUTH", "R-EAST", "R-WEST", "R-CENTRAL"]
# ───────────────────────────────────────────────────────────────────────────

LOCATIONS = [
    ("Restaurant Row A",    24.6877, 46.7219),
    ("University Cafeteria",24.7136, 46.6753),
    ("Central Market",      24.6880, 46.7233),
    ("City Park North",     24.7251, 46.6901),
    ("Tech Hub Plaza",      24.7421, 46.6512),
    ("Hospital Complex",    24.6521, 46.7102),
    ("Sports Complex",      24.7601, 46.7341),
    ("Residential Block D", 24.6982, 46.7654),
    ("Shopping Mall West",  24.6741, 46.6988),
    ("Office District",     24.7312, 46.7023),
    ("Airport Terminal",    24.9578, 46.6988),
    ("Bus Station Central", 24.6805, 46.7315),
    ("School District 4",   24.7095, 46.7432),
    ("Mosque Compound",     24.6951, 46.6871),
    ("Residential Block K", 24.7189, 46.7189),
    ("Food Court East",     24.6631, 46.7451),
    ("Hotel Row",           24.7522, 46.7102),
    ("Industrial Zone C",   24.6401, 46.7681),
    ("Marina Walk",         24.7801, 46.6341),
    ("Suburb Connector",    24.6221, 46.7891),
]


def make_bins():
    bins = []
    for i in range(BIN_COUNT):
        loc = LOCATIONS[i % len(LOCATIONS)]
        bins.append(Bin(
            id=f"BN-{i+1:03d}",
            name=f"Smart Bin #{i+1:03d}",
            location_name=loc[0],
            lat=loc[1] + random.uniform(-0.002, 0.002),
            lng=loc[2] + random.uniform(-0.002, 0.002),
            installed_at=datetime.now(timezone.utc) - timedelta(days=random.randint(60, 365)),
            status=BinStatus.operational,
        ))
    return bins


def fill_pct_at(hour: int, day_offset: int, bin_idx: int) -> float:
    """
    Simulate realistic fill: rises during meal/business hours,
    resets after pickup (midnight), adds per-bin variability.
    """
    base_rate  = 0.8 + 0.4 * (bin_idx % 5)          # bins at busier spots fill faster
    hour_factor= 1.0 + 0.5 * math.sin(math.pi * hour / 12)  # peaks at noon
    fill = (hour / 24.0) * base_rate * hour_factor * 100
    fill += random.gauss(0, 3)                         # sensor noise
    return max(0.0, min(100.0, fill))


def make_telemetry(bins):
    rows = []
    now  = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start= now - timedelta(days=DAYS)

    for b_idx, b in enumerate(bins):
        ts = start
        while ts < now:
            if random.random() > SKIP_PROB:  # simulate occasional missing readings
                fill = fill_pct_at(ts.hour, (ts - start).days, b_idx)
                rows.append(Telemetry(
                    bin_id     = b.id,
                    ts         = ts,
                    fill_pct   = round(fill, 2),
                    weight_kg  = round(fill * 0.045 + random.gauss(0, 0.2), 3),
                    temp_c     = round(22 + 8 * math.sin(math.pi * ts.hour / 12) + random.gauss(0, 1), 2),
                    battery_v  = round(random.uniform(3.4, 4.2), 2),
                    signal_rssi= round(random.uniform(-90, -50), 1) if random.random() > 0.1 else None,
                ))
            ts += timedelta(minutes=INTERVAL_MINUTES)
    return rows


def make_pickups(bins):
    rows  = []
    today = date.today()
    for day_offset in range(-DAYS, FORECAST_HORIZON + 1):
        d      = today + timedelta(days=day_offset)
        dt_base= datetime(d.year, d.month, d.day, 6, 0, tzinfo=timezone.utc)
        route  = ROUTES[day_offset % len(ROUTES)]
        for b in bins:
            if random.random() < 0.35:   # ~35% of bins get a pickup on any given day
                hour_offset = random.randint(0, 8)
                sched       = dt_base + timedelta(hours=hour_offset)
                past        = day_offset < 0
                rows.append(Pickup(
                    bin_id      = b.id,
                    scheduled_at= sched,
                    window_start= sched - timedelta(minutes=30),
                    window_end  = sched + timedelta(minutes=30),
                    route_id    = route,
                    priority    = random.choice(list(PickupPriority)),
                    status      = (
                        PickupStatus.completed if past and random.random() > 0.1
                        else PickupStatus.missed if past
                        else PickupStatus.planned
                    ),
                ))
    return rows


def make_forecasts(bins):
    rows  = []
    today = date.today()
    for b in bins:
        for i in range(FORECAST_HORIZON):
            fd = today + timedelta(days=i + 1)
            predicted_fill = min(100, 30 + i * 8 + random.gauss(0, 5))
            rows.append(Forecast(
                bin_id                 = b.id,
                forecast_date          = fd,
                predicted_fill_pct     = round(predicted_fill, 2),
                predicted_weight_kg    = round(predicted_fill * 0.045, 3),
                recommended_pickup_date= fd if predicted_fill > 70 else fd + timedelta(days=1),
                model_version          = "mock-v0.1",  # ← PLACEHOLDER for CS/ISE module
            ))
    return rows


def seed():
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)   # safety net if migrations weren't run

    with Session(engine) as session:
        # Idempotent: clear existing seed data
        print("🗑  Clearing existing data...")
        session.query(Forecast).delete()
        session.query(Pickup).delete()
        session.query(Telemetry).delete()
        session.query(Bin).delete()
        session.commit()

        print(f"🏗  Creating {BIN_COUNT} bins...")
        bins = make_bins()
        session.add_all(bins)
        session.commit()

        print(f"📡  Generating telemetry ({DAYS} days × {BIN_COUNT} bins @ {INTERVAL_MINUTES}min intervals)...")
        tel = make_telemetry(bins)
        print(f"    → {len(tel):,} telemetry rows")
        # Bulk insert in batches for speed
        BATCH = 5000
        for i in range(0, len(tel), BATCH):
            session.bulk_save_objects(tel[i:i+BATCH])
            session.commit()
            print(f"    → committed {min(i+BATCH, len(tel)):,}/{len(tel):,}", end="\r")
        print()

        print("🚛  Generating pickup schedules...")
        pickups = make_pickups(bins)
        session.add_all(pickups)
        session.commit()
        print(f"    → {len(pickups)} pickup records")

        print("🔮  Generating forecasts (MOCK/PLACEHOLDER)...")
        forecasts = make_forecasts(bins)
        session.add_all(forecasts)
        session.commit()
        print(f"    → {len(forecasts)} forecast records")

    print("\n✅  Seed complete!")


if __name__ == "__main__":
    seed()