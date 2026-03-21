from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Transaction

LOGGER = logging.getLogger(__name__)


def _now() -> datetime:
    """Return current time in the configured timezone (naive datetime)."""
    try:
        tz = ZoneInfo(settings.tz)
        return datetime.now(tz=tz).replace(tzinfo=None)
    except Exception:
        return datetime.now()

DEFAULT_LIST_LIMIT = 10
MAX_LIST_LIMIT = 50
DEFAULT_SUMMARY_DAYS = 30
MAX_SUMMARY_DAYS = 3650


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_command(token: str) -> str:
    # Telegram group messages may contain: /list@bot_name
    if "@" in token:
        token = token.split("@", 1)[0]
    return token.lower()


def _help_text() -> str:
    return (
        "可用命令:\n"
        "/help - 查看帮助\n"
        "/list [N] - 最近 N 条账单（默认10，最大50）\n"
        "/summary [days] - 最近 days 天汇总（默认30）\n"
        "/month - 本月汇总\n"
        "/category [income|expense] [days] - 分类统计（默认本月支出）\n"
        "/delete <id> - 删除指定账单（id 来自 /list）\n"
        "\n"
        "你也可以直接发记账语句，例如：午饭 23"
    )


def _format_record_line(index: int, tx: Transaction) -> str:
    direction = "收入" if tx.direction == "income" else "支出"
    sign = "+" if tx.direction == "income" else "-"
    ts = tx.occurred_at.strftime("%m-%d %H:%M")
    note = tx.note.strip() if tx.note else ""
    note_text = f" {note}" if note else ""
    return f"{index}. [#{tx.id}] {ts} {direction} {sign}{tx.amount:.2f} {tx.currency} [{tx.category}]{note_text}"


def _handle_list(db: Session, arg: str | None) -> str:
    limit = _safe_int(arg) if arg else DEFAULT_LIST_LIMIT
    if limit is None or limit <= 0:
        return "参数错误：/list [N] 中 N 必须是正整数。"
    limit = min(limit, MAX_LIST_LIMIT)

    stmt = select(Transaction).order_by(Transaction.occurred_at.desc()).limit(limit)
    rows = list(db.scalars(stmt))
    if not rows:
        return "暂无账单记录。"

    header = f"最近 {len(rows)} 条账单："
    body = "\n".join(_format_record_line(i + 1, tx) for i, tx in enumerate(rows))
    return f"{header}\n{body}"


def _handle_summary(db: Session, arg: str | None) -> str:
    days = _safe_int(arg) if arg else DEFAULT_SUMMARY_DAYS
    if days is None or days <= 0:
        return "参数错误：/summary [days] 中 days 必须是正整数。"
    days = min(days, MAX_SUMMARY_DAYS)

    start = _now() - timedelta(days=days)
    income_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "income",
        Transaction.occurred_at >= start,
    )
    expense_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "expense",
        Transaction.occurred_at >= start,
    )
    income_total = float(db.scalar(income_stmt) or 0)
    expense_total = float(db.scalar(expense_stmt) or 0)
    balance = income_total - expense_total

    return (
        f"最近 {days} 天汇总：\n"
        f"收入：{income_total:.2f} CNY\n"
        f"支出：{expense_total:.2f} CNY\n"
        f"结余：{balance:.2f} CNY"
    )


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _build_range_summary(db: Session, start: datetime, end: datetime, title: str) -> str:
    income_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "income",
        Transaction.occurred_at >= start,
        Transaction.occurred_at <= end,
    )
    expense_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "expense",
        Transaction.occurred_at >= start,
        Transaction.occurred_at <= end,
    )
    count_stmt = select(func.count(Transaction.id)).where(
        Transaction.occurred_at >= start,
        Transaction.occurred_at <= end,
    )

    income_total = float(db.scalar(income_stmt) or 0)
    expense_total = float(db.scalar(expense_stmt) or 0)
    balance = income_total - expense_total
    count = int(db.scalar(count_stmt) or 0)

    return (
        f"{title}：\n"
        f"收入：{income_total:.2f} CNY\n"
        f"支出：{expense_total:.2f} CNY\n"
        f"结余：{balance:.2f} CNY\n"
        f"笔数：{count}"
    )


def _handle_month(db: Session) -> str:
    now = _now()
    start = _month_start(now)
    title = f"{now.year}-{now.month:02d} 本月汇总"
    return _build_range_summary(db, start=start, end=now, title=title)


def _parse_category_args(arg: str | None) -> tuple[str, int | None] | str:
    if not arg:
        return "expense", None

    direction = "expense"
    days: int | None = None
    parts = arg.split()
    for token in parts:
        lowered = token.lower()
        if lowered in {"income", "in"} or token == "收入":
            direction = "income"
            continue
        if lowered in {"expense", "out"} or token == "支出":
            direction = "expense"
            continue
        value = _safe_int(token)
        if value is not None:
            if value <= 0:
                return "参数错误：/category [income|expense] [days] 中 days 必须是正整数。"
            days = min(value, MAX_SUMMARY_DAYS)
            continue
        return "参数错误：/category 仅支持 income/expense 和 days 参数。"

    return direction, days


def _handle_category(db: Session, arg: str | None) -> str:
    parsed = _parse_category_args(arg)
    if isinstance(parsed, str):
        return parsed
    direction, days = parsed

    now = _now()
    if days is None:
        start = _month_start(now)
        period_text = f"{now.year}-{now.month:02d} 本月"
    else:
        start = now - timedelta(days=days)
        period_text = f"最近 {days} 天"

    stmt = (
        select(
            Transaction.category,
            func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .where(
            Transaction.direction == direction,
            Transaction.occurred_at >= start,
            Transaction.occurred_at <= now,
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(20)
    )
    rows = db.execute(stmt).all()
    if not rows:
        kind = "收入" if direction == "income" else "支出"
        return f"{period_text}暂无{kind}记录。"

    total_amount = sum(float(row.total or 0) for row in rows)
    kind = "收入" if direction == "income" else "支出"
    lines = [f"{period_text}{kind}分类统计："]
    for index, row in enumerate(rows, start=1):
        amount = float(row.total or 0)
        count = int(row.count or 0)
        ratio = (amount / total_amount * 100) if total_amount > 0 else 0
        lines.append(f"{index}. {row.category}: {amount:.2f} CNY ({ratio:.1f}%) {count}笔")

    lines.append(f"合计：{total_amount:.2f} CNY")
    return "\n".join(lines)


def _handle_delete(db: Session, arg: str | None) -> str:
    record_id = _safe_int(arg) if arg else None
    if record_id is None or record_id <= 0:
        return "参数错误：/delete <id>，id 为账单编号（可通过 /list 查看）。"

    tx = db.get(Transaction, record_id)
    if not tx:
        return f"未找到编号为 {record_id} 的账单。"

    direction = "收入" if tx.direction == "income" else "支出"
    info = f"{direction} {tx.amount:.2f} {tx.currency} [{tx.category}]"
    db.delete(tx)
    db.commit()
    return f"已删除账单 #{record_id}：{info}"


def build_command_reply(text: str, db: Session) -> str | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split(maxsplit=1)
    command = _normalize_command(parts[0])
    arg = parts[1].strip() if len(parts) > 1 else None

    if command in {"/help", "/start"}:
        return _help_text()
    if command == "/list":
        return _handle_list(db, arg)
    if command == "/summary":
        return _handle_summary(db, arg)
    if command == "/month":
        return _handle_month(db)
    if command == "/category":
        return _handle_category(db, arg)
    if command == "/delete":
        return _handle_delete(db, arg)

    return "未知命令，发送 /help 查看可用命令。"
