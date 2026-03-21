from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import settings
from .database import Base, SessionLocal, engine
from .parser import parse_text_to_transaction
from .services import create_transaction, parse_result_to_create
from .telegram_commands import build_command_reply

LOGGER = logging.getLogger(__name__)
POLL_TIMEOUT_SECONDS = 50
RETRY_DELAY_INITIAL = 3
RETRY_DELAY_MAX = 60


def _allowed_chat_ids() -> set[int]:
    raw = settings.telegram_allowed_chat_ids.strip()
    if not raw:
        return set()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                LOGGER.warning("Invalid chat_id in TELEGRAM_ALLOWED_CHAT_IDS: %s", part)
    return ids


def _extract_message(update: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    for key in ("message", "edited_message", "channel_post"):
        msg = update.get(key)
        if isinstance(msg, dict):
            text = msg.get("text")
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            return text, chat_id, msg.get("message_id")
    return None, None, None


async def _reply_telegram(client: httpx.AsyncClient, api_base: str, chat_id: int | None, text: str) -> None:
    if chat_id is None:
        return
    try:
        await client.post(
            f"{api_base}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    except Exception:
        LOGGER.exception("Failed to send Telegram reply")


async def _process_update(client: httpx.AsyncClient, api_base: str, update: dict[str, Any]) -> None:
    text, chat_id, message_id = _extract_message(update)
    if not text:
        return

    # Chat ID whitelist check
    allowed = _allowed_chat_ids()
    if allowed and chat_id not in allowed:
        LOGGER.info("Ignored message from unauthorized chat_id=%s", chat_id)
        return

    try:
        with SessionLocal() as db:
            command_reply = build_command_reply(text, db)
    except Exception:
        LOGGER.exception("Failed to process command for update_id=%s", update.get("update_id"))
        await _reply_telegram(client, api_base, chat_id, "命令处理失败，请稍后重试。")
        return

    if command_reply is not None:
        await _reply_telegram(client, api_base, chat_id, command_reply)
        return

    update_id = update.get("update_id")
    external_id = f"tg:{update_id or message_id}" if (update_id or message_id) else None

    try:
        parsed = parse_text_to_transaction(text, tz_name=settings.tz)
    except ValueError as exc:
        await _reply_telegram(client, api_base, chat_id, f"解析失败: {exc}")
        return

    try:
        with SessionLocal() as db:
            tx_payload = parse_result_to_create(parsed, source="telegram", external_id=external_id)
            tx = create_transaction(db, tx_payload)
    except Exception:
        LOGGER.exception("Failed to save transaction for update_id=%s", update_id)
        await _reply_telegram(client, api_base, chat_id, "记录失败，请重试。")
        return

    direction_text = "收入" if tx.direction == "income" else "支出"
    await _reply_telegram(
        client,
        api_base,
        chat_id,
        f"已记账: {direction_text} {tx.amount:.2f} 元 ({tx.category})",
    )


async def run_poller() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty. Set it in .env before starting the poller.")

    Base.metadata.create_all(bind=engine)
    api_base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    offset: int | None = None
    retry_delay = RETRY_DELAY_INITIAL
    async with httpx.AsyncClient(timeout=POLL_TIMEOUT_SECONDS + 10) as client:
        # Polling and webhook cannot work at the same time for the same bot.
        try:
            await client.post(f"{api_base}/deleteWebhook", json={"drop_pending_updates": False})
        except Exception:
            LOGGER.exception("Failed to disable Telegram webhook before polling")

        while True:
            payload: dict[str, Any] = {"timeout": POLL_TIMEOUT_SECONDS, "allowed_updates": ["message", "edited_message", "channel_post"]}
            if offset is not None:
                payload["offset"] = offset

            try:
                resp = await client.post(f"{api_base}/getUpdates", json=payload)
                resp.raise_for_status()
                body = resp.json()
            except Exception:
                LOGGER.exception("getUpdates request failed, retrying in %ss", retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, RETRY_DELAY_MAX)
                continue

            if not body.get("ok"):
                LOGGER.warning("getUpdates returned non-ok body: %s", body)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, RETRY_DELAY_MAX)
                continue

            # Reset backoff on success
            retry_delay = RETRY_DELAY_INITIAL

            for update in body.get("result", []):
                await _process_update(client, api_base, update)
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_poller())


if __name__ == "__main__":
    main()
