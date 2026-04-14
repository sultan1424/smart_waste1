"""
Seed script — configurable via constants at the top.
Uses SYNC_DATABASE_URL (psycopg2) for simplicity.

⚠️  MOCK/PLACEHOLDER data for PPR purposes:
    - Telemetry values simulate realistic IoT sensor patterns
    - Forecasts are random (placeholder for the CS/ISE forecasting module)
    - Pickup routes are placeholder (placeholder for the scheduling module)
    - Coordinates match Aseel's routing model (Dammam, Saudi Arabia)
"""
import os, sys, random, math, hashlib
from datetime import datetime, timedelta, timezone, date
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import settings
from app.core.security import encrypt_value
from app.models.models import Base, Bin, Telemetry, Pickup, Forecast, BinStatus, PickupPriority, PickupStatus

# ── Configuration ──────────────────────────────────────────────────────────
BIN_COUNT          = 20
DAYS               = 30
INTERVAL_MINUTES   = 120
SKIP_PROB          = 0.03
FORECAST_HORIZON   = 10
ROUTES             = ["R-NORTH", "R-SOUTH", "R-EAST", "R-WEST", "R-CENTRAL"]
# ───────────────────────────────────────────────────────────────────────────

# Dammam locations — first 20 match Aseel's routing model node positions
LOCATIONS = [
    ("Al Corniche",        26.4447, 50.1120),
    ("Al Faisaliyah",      26.4390, 50.0950),
    ("Al Hamra",           26.4310, 50.1070),
    ("Al Murjan",          26.4500, 50.1060),
    ("Al Rakah",           26.4260, 50.1150),
    ("Al Nakheel",         26.4560, 50.0980),
    ("Al Dana",            26.4480, 50.1200),
    ("Al Aqrabiyah",       26.4330, 50.0900),
    ("Al Badiyah",         26.4200, 50.1000),
    ("Al Taawun",          26.4620, 50.1040),
    ("Al Mazruiyah",       26.4150, 50.1100),
    ("Al Anud",            26.4280, 50.0870),
    ("Dhahran Hills",      26.4700, 50.1090),
    ("Al Safa",            26.4380, 50.1190),
    ("Uhud District",      26.4090, 50.1040),
    ("Al Khalidiyah",      26.4440, 50.0840),
    ("Al Jawharah",        26.4600, 50.1160),
    ("Al Qusur",           26.4170, 50.0950),
    ("Al Firdaws",         26.4530, 50.0900),
    ("Al Rawdah",          26.4350, 50.1260),
]


def make_bins():
    bins = []
    for i in range(BIN_COUNT):
        loc = LOCATIONS[i % len(LOCATIONS)]
        location_name = loc[0]
        bins.append(Bin(
            id=f"BN-{i+1:03d}",
            name=f"Smart Bin #{i+1:03d}",
            location_name_encrypted=encrypt_value(location_name),
            location_name_hash=hashlib.sha256(location_name.lower().encode()).hexdigest(),
            lat=loc[1] + random.uniform(-0.001, 0.001),
            lng=loc[2] + random.uniform(-0.001, 0.001),
            installed_at=datetime.now(timezone.utc) - timedelta(days=random.randint(60, 365)),
            status=BinStatus.operational,
        ))
    return bins


def fill_pct_at(hour: int, day_offset: int, bin_idx: int) -> float:
    base_rate  = 0.8 + 0.4 * (bin_idx % 5)
    hour_factor= 1.0 + 0.5 * math.sin(math.pi * hour / 12)
    fill = (hour / 24.0) * base_rate * hour_factor * 100
    fill += random.gauss(0, 3)
    return max(0.0, min(100.0, fill))


def make_telemetry(bins):
    rows = []
    now  = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start= now - timedelta(days=DAYS)

    for b_idx, b in enumerate(bins):
        ts = start
        while ts < now:
            if random.random() > SKIP_PROB:
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
            if random.random() < 0.35:
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
                model_version          = "mock-v0.1",
            ))
    return rows


def seed():
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        print("🗑  Clearing existing data...")
        session.query(Forecast).delete()
        session.query(Pickup).delete()
        session.query(Telemetry).delete()
        session.query(Bin).delete()
        session.commit()

        print(f"🏗  Creating {BIN_COUNT} bins in Dammam...")
        bins = make_bins()
        session.add_all(bins)
        session.commit()

        print(f"📡  Generating telemetry ({DAYS} days × {BIN_COUNT} bins @ {INTERVAL_MINUTES}min intervals)...")
        tel = make_telemetry(bins)
        print(f"    → {len(tel):,} telemetry rows")
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

    print("\n✅  Seed complete! All bins now in Dammam — consistent with Aseel's routing model.")


if __name__ == "__main__":
    seed()