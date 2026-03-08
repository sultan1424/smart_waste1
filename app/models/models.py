import enum
from datetime import datetime, date
from sqlalchemy import (
    String, Float, DateTime, Date, Integer, ForeignKey,
    Enum as SAEnum, Index, JSON, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class UserRole(str, enum.Enum):
    restaurant = "restaurant"
    collector  = "collector"
    regulator  = "regulator"

class Base(DeclarativeBase):
    pass

# ── Enums ──────────────────────────────────────────────────────────────────

class BinStatus(str, enum.Enum):
    operational = "operational"
    near_full   = "near_full"
    full        = "full"
    maintenance = "maintenance"

class PickupPriority(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"

class PickupStatus(str, enum.Enum):
    planned   = "planned"
    completed = "completed"
    missed    = "missed"

# ── Models ─────────────────────────────────────────────────────────────────

class Bin(Base):
    __tablename__ = "bins"

    id           : Mapped[str]      = mapped_column(String(20), primary_key=True)
    name         : Mapped[str]      = mapped_column(String(100))
    location_name: Mapped[str]      = mapped_column(String(200))
    lat          : Mapped[float]    = mapped_column(Float)
    lng          : Mapped[float]    = mapped_column(Float)
    installed_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    status       : Mapped[BinStatus]= mapped_column(SAEnum(BinStatus), default=BinStatus.operational)

    telemetry: Mapped[list["Telemetry"]] = relationship(back_populates="bin", lazy="noload")
    pickups  : Mapped[list["Pickup"]]    = relationship(back_populates="bin", lazy="noload")
    forecasts: Mapped[list["Forecast"]]  = relationship(back_populates="bin", lazy="noload")


class Telemetry(Base):
    __tablename__ = "telemetry"

    id          : Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    bin_id      : Mapped[str]   = mapped_column(String(20), ForeignKey("bins.id", ondelete="CASCADE"))
    ts          : Mapped[datetime]= mapped_column(DateTime(timezone=True), nullable=False)
    fill_pct    : Mapped[float] = mapped_column(Float)
    weight_kg   : Mapped[float] = mapped_column(Float)
    temp_c      : Mapped[float] = mapped_column(Float)
    battery_v   : Mapped[float] = mapped_column(Float)
    signal_rssi : Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at  : Mapped[datetime]= mapped_column(DateTime(timezone=True), default=func.now())

    bin: Mapped["Bin"] = relationship(back_populates="telemetry")

    __table_args__ = (
        # Critical composite index for time-range queries by bin
        Index("ix_telemetry_bin_ts", "bin_id", "ts"),
        # Also support pure time-range scans across all bins
        Index("ix_telemetry_ts",    "ts"),
    )


class Pickup(Base):
    __tablename__ = "pickups"

    id          : Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    bin_id      : Mapped[str]           = mapped_column(String(20), ForeignKey("bins.id", ondelete="CASCADE"))
    scheduled_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True))
    window_start: Mapped[datetime]      = mapped_column(DateTime(timezone=True))
    window_end  : Mapped[datetime]      = mapped_column(DateTime(timezone=True))
    route_id    : Mapped[str]           = mapped_column(String(50))
    priority    : Mapped[PickupPriority]= mapped_column(SAEnum(PickupPriority), default=PickupPriority.medium)
    status      : Mapped[PickupStatus]  = mapped_column(SAEnum(PickupStatus),   default=PickupStatus.planned)
    created_at  : Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=func.now())

    bin: Mapped["Bin"] = relationship(back_populates="pickups")

    __table_args__ = (
        Index("ix_pickups_scheduled_at", "scheduled_at"),
        Index("ix_pickups_bin_id",       "bin_id"),
    )


class Forecast(Base):
    __tablename__ = "forecasts"

    id                    : Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    bin_id                : Mapped[str]   = mapped_column(String(20), ForeignKey("bins.id", ondelete="CASCADE"))
    forecast_date         : Mapped[date]  = mapped_column(Date)
    predicted_fill_pct    : Mapped[float] = mapped_column(Float)
    predicted_weight_kg   : Mapped[float] = mapped_column(Float)
    recommended_pickup_date: Mapped[date] = mapped_column(Date)
    model_version         : Mapped[str]   = mapped_column(String(50), default="mock-v0.1")
    created_at            : Mapped[datetime]= mapped_column(DateTime(timezone=True), default=func.now())

    bin: Mapped["Bin"] = relationship(back_populates="forecasts")

    __table_args__ = (
        Index("ix_forecasts_bin_date", "bin_id", "forecast_date"),
    )


class ReportCache(Base):
    __tablename__ = "reports_cache"

    id           : Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    bin_id       : Mapped[str | None]= mapped_column(String(20), nullable=True)
    period_start : Mapped[date]     = mapped_column(Date)
    period_end   : Mapped[date]     = mapped_column(Date)
    generated_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    payload_json : Mapped[dict]     = mapped_column(JSON)

    __table_args__ = (
        Index("ix_reports_cache_bin_period", "bin_id", "period_start", "period_end"),
    )
    
class User(Base):
    __tablename__ = "users"

    id            : Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_encrypted: Mapped[str]     = mapped_column(String(500), unique=True)  # AES-256-GCM encrypted
    email_hash    : Mapped[str]      = mapped_column(String(200), unique=True)  # SHA-256 for lookup
    password_hash : Mapped[str]      = mapped_column(String(200))
    role          : Mapped[UserRole] = mapped_column(SAEnum(UserRole))
    restaurant_id : Mapped[str|None] = mapped_column(String(20), nullable=True)  # e.g. "BN-001..BN-005"
    created_at    : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())