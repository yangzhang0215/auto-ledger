from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Transaction
from ..parser import parse_text_to_transaction
from ..schemas import ParseRequest, SummaryRead, TransactionCreate, TransactionRead
from ..services import create_transaction, parse_result_to_create

router = APIRouter(prefix="/api", tags=["records"])


@router.post(
    "/parse",
    response_model=TransactionRead,
)
def parse_and_create(payload: ParseRequest, db: Session = Depends(get_db)):
    try:
        parsed = parse_text_to_transaction(payload.text, tz_name=settings.tz)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    tx_payload = parse_result_to_create(parsed, source=payload.source, external_id=payload.external_id)
    tx = create_transaction(db, tx_payload)
    return tx


@router.post(
    "/records",
    response_model=TransactionRead,
)
def create_record(payload: TransactionCreate, db: Session = Depends(get_db)):
    tx = create_transaction(db, payload)
    return tx


@router.get(
    "/records",
    response_model=list[TransactionRead],
)
def list_records(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
):
    stmt = select(Transaction).order_by(Transaction.occurred_at.desc()).limit(limit).offset(offset)
    if start is not None:
        stmt = stmt.where(Transaction.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(Transaction.occurred_at <= end)
    return list(db.scalars(stmt))


@router.get(
    "/summary",
    response_model=SummaryRead,
)
def summary(
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=3650),
):
    start = datetime.now() - timedelta(days=days)
    income_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "income", Transaction.occurred_at >= start
    )
    expense_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "expense", Transaction.occurred_at >= start
    )
    income_total = float(db.scalar(income_stmt) or 0)
    expense_total = float(db.scalar(expense_stmt) or 0)
    return SummaryRead(
        days=days,
        income_total=income_total,
        expense_total=expense_total,
        balance=income_total - expense_total,
    )


@router.delete(
    "/records/{record_id}",
)
def delete_record(record_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, record_id)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    db.delete(tx)
    db.commit()
    return {"ok": True, "deleted_id": record_id}
