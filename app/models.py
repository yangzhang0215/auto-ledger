from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)

    direction: Mapped[str] = mapped_column(String(10), default="expense", index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    category: Mapped[str] = mapped_column(String(32), default="其他", index=True)
    note: Mapped[str] = mapped_column(String(255), default="")

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.now, index=True)

