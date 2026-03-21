from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..parser import parse_text_to_transaction
from ..services import create_transaction, parse_result_to_create

router = APIRouter(prefix="/webhook/wechat", tags=["wechat"])


def _valid_signature(signature: str, timestamp: str, nonce: str) -> bool:
    token = settings.wechat_token
    if not token:
        return False
    parts = sorted([token, timestamp, nonce])
    digest = hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()
    return digest == signature


def _xml_text(xml_root: ET.Element, tag: str) -> str:
    node = xml_root.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _reply_xml(to_user: str, from_user: str, content: str) -> str:
    now = int(time.time())
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{now}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        "</xml>"
    )


@router.get("")
def wechat_verify(
    signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
):
    if not _valid_signature(signature, timestamp, nonce):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    return Response(content=echostr, media_type="text/plain")


@router.post("")
async def wechat_webhook(
    request: Request,
    db: Session = Depends(get_db),
    signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
):
    if not _valid_signature(signature, timestamp, nonce):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    payload = await request.body()
    root = ET.fromstring(payload.decode("utf-8"))

    msg_type = _xml_text(root, "MsgType")
    from_user = _xml_text(root, "FromUserName")
    to_user = _xml_text(root, "ToUserName")

    if msg_type != "text":
        return Response(content="success", media_type="text/plain")

    text = _xml_text(root, "Content")
    msg_id = _xml_text(root, "MsgId")
    external_id = f"wechat:{msg_id}" if msg_id else None

    try:
        parsed = parse_text_to_transaction(text, tz_name=settings.tz)
        tx_payload = parse_result_to_create(parsed, source="wechat", external_id=external_id)
        tx = create_transaction(db, tx_payload)
        content = f"已记账: {'收入' if tx.direction == 'income' else '支出'} {tx.amount:.2f} 元 ({tx.category})"
    except ValueError as exc:
        content = f"解析失败: {exc}"

    return Response(content=_reply_xml(from_user, to_user, content), media_type="application/xml")

