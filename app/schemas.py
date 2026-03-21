from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["expense", "income"]


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    source: str = Field(default="manual", max_length=20)
    external_id: str | None = Field(default=None, max_length=128)


class ParseResult(BaseModel):
    direction: Direction
    amount: float
    category: str
    note: str
    occurred_at: datetime
    raw_text: str


class TransactionCreate(BaseModel):
    source: str = Field(default="manual", max_length=20)
    external_id: str | None = Field(default=None, max_length=128)
    direction: Direction
    amount: float = Field(gt=0)
    currency: str = Field(default="CNY", max_length=10)
    category: str = Field(default="其他", max_length=32)
    note: str = Field(default="", max_length=255)
    occurred_at: datetime = Field(default_factory=datetime.now)
    raw_text: str = Field(default="", max_length=1000)


class TransactionRead(BaseModel):
    id: int
    source: str
    external_id: str | None
    direction: Direction
    amount: float
    currency: str
    category: str
    note: str
    occurred_at: datetime
    raw_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SummaryRead(BaseModel):
    days: int
    income_total: float
    expense_total: float
    balance: float

