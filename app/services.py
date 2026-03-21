from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Transaction
from .schemas import ParseResult, TransactionCreate


def create_transaction(db: Session, payload: TransactionCreate) -> Transaction:
    if payload.external_id:
        stmt = select(Transaction).where(Transaction.external_id == payload.external_id)
        existing = db.scalar(stmt)
        if existing:
            return existing

    tx = Transaction(
        source=payload.source,
        external_id=payload.external_id,
        direction=payload.direction,
        amount=payload.amount,
        currency=payload.currency,
        category=payload.category,
        note=payload.note,
        occurred_at=payload.occurred_at,
        raw_text=payload.raw_text,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def parse_result_to_create(
    parsed: ParseResult,
    source: str,
    external_id: str | None,
) -> TransactionCreate:
    return TransactionCreate(
        source=source,
        external_id=external_id,
        direction=parsed.direction,
        amount=parsed.amount,
        category=parsed.category,
        note=parsed.note,
        occurred_at=parsed.occurred_at,
        raw_text=parsed.raw_text,
    )

