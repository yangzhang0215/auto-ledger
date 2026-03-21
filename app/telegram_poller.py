from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import settings
from .database import Base, SessionLocal, engine
from .parser import parse_text_to_transaction
from .services import create_transaction, parse_result_to_create

LOGGER = logging.getLogger(__name__)
POLL_TIMEOUT_SECONDS = 50
RETRY_DELAY_SECONDS = 3


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

    update_id = update.get("update_id")
    external_id = f"tg:{update_id or message_id}" if (update_id or message_id) else None

    try:
        parsed = parse_text_to_transaction(text, tz_name=settings.tz)
    except ValueError as exc:
        await _reply_telegram(client, api_base, chat_id, f"Parse failed: {exc}")
        return

    try:
        with SessionLocal() as db:
            tx_payload = parse_result_to_create(parsed, source="telegram", external_id=external_id)
            tx = create_transaction(db, tx_payload)
    except Exception:
        LOGGER.exception("Failed to save transaction for update_id=%s", update_id)
        await _reply_telegram(client, api_base, chat_id, "Record failed. Please retry.")
        return

    direction_text = "income" if tx.direction == "income" else "expense"
    await _reply_telegram(
        client,
        api_base,
        chat_id,
        f"Recorded: {direction_text} {tx.amount:.2f} ({tx.category})",
    )


async def run_poller() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty. Set it in .env before starting the poller.")

    Base.metadata.create_all(bind=engine)
    api_base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    offset: int | None = None
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
                LOGGER.exception("getUpdates request failed, retrying in %ss", RETRY_DELAY_SECONDS)
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue

            if not body.get("ok"):
                LOGGER.warning("getUpdates returned non-ok body: %s", body)
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue

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
