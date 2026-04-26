from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean, BigInteger, Date, Integer, Numeric,
    String, Text, TIMESTAMP, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class ClientAccount(Base):
    __tablename__ = "client_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class CampaignSnapshot(Base):
    __tablename__ = "campaign_snapshots"
    __table_args__ = (Index("ix_campaign_snapshots_customer_date", "customer_id", "snapshot_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(10), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(20), nullable=False)
    campaign_name: Mapped[str] = mapped_column(String(255))
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    cost_micros: Mapped[int | None] = mapped_column(BigInteger)
    conversions: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    cpa: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class ChangeLog(Base):
    __tablename__ = "change_log"
    __table_args__ = (Index("ix_change_log_customer_executed", "customer_id", "executed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(50))
    before_payload: Mapped[dict | None] = mapped_column(JSONB)
    after_payload: Mapped[dict | None] = mapped_column(JSONB)
    confirmed_by: Mapped[str | None] = mapped_column(String(100))
    executed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class GeneratedAdCopy(Base):
    __tablename__ = "generated_ad_copy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(10), nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(20))
    service: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(100))
    headlines: Mapped[list | None] = mapped_column(JSONB)
    descriptions: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
