from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..parser import parse_text_to_transaction
from ..services import create_transaction, parse_result_to_create

router = APIRouter(prefix="/webhook/telegram", tags=["telegram"])


def _extract_message(update: dict) -> tuple[str | None, int | None, int | None]:
    for key in ("message", "edited_message", "channel_post"):
        msg = update.get(key)
        if isinstance(msg, dict):
            text = msg.get("text")
            if not text:
                return None, None, msg.get("message_id")
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            return text, chat_id, msg.get("message_id")
    return None, None, None


async def _reply_telegram(chat_id: int | None, text: str) -> None:
    if not chat_id or not settings.telegram_bot_token:
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception:
        # Webhook should still return 200 even if reply fails.
        return


@router.post("/{path_secret}")
async def telegram_webhook(path_secret: str, request: Request, db: Session = Depends(get_db)):
    if settings.telegram_webhook_secret and path_secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    update = await request.json()
    text, chat_id, message_id = _extract_message(update)
    if not text:
        return {"ok": True, "ignored": True}

    update_id = update.get("update_id")
    external_id = f"tg:{update_id or message_id}" if (update_id or message_id) else None

    try:
        parsed = parse_text_to_transaction(text, tz_name=settings.tz)
    except ValueError as exc:
        await _reply_telegram(chat_id, f"解析失败: {exc}")
        return {"ok": False, "error": str(exc)}

    tx_payload = parse_result_to_create(parsed, source="telegram", external_id=external_id)
    tx = create_transaction(db, tx_payload)
    direction_text = "收入" if tx.direction == "income" else "支出"
    await _reply_telegram(chat_id, f"已记账: {direction_text} {tx.amount:.2f} 元 ({tx.category})")

    return {
        "ok": True,
        "id": tx.id,
        "chat_id": chat_id,
        "direction": tx.direction,
        "amount": tx.amount,
        "category": tx.category,
    }
