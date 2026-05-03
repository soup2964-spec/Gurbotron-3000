"""Message ingest, PPV counters, reply dispatch."""

from __future__ import annotations

import random
import uuid
from datetime import datetime
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.fanvue import FanvueClient
from app.llm import ReplyContext, ReplyGenerator, default_generator
from app.models import BotSettings, ChatMessage, Subscriber


def facts_dict(db: Session, subscriber: Subscriber) -> dict[str, str]:
    return {f.fact_key: f.fact_value for f in subscriber.facts}


def recent_thread(db: Session, subscriber: Subscriber, limit: int = 40) -> list[tuple[str, str]]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.subscriber_id == subscriber.id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    out: list[tuple[str, str]] = []
    for m in rows:
        role = "fan" if m.direction == "inbound" else "creator"
        text = (m.body or "").strip()
        if text:
            out.append((role, text))
    return out


async def compose_and_maybe_send(
    db: Session,
    subscriber: Subscriber,
    fanvue: FanvueClient,
    generator: ReplyGenerator | None = None,
) -> None:
    gen = generator or default_generator
    bot = db.get(BotSettings, 1)
    if bot is None or bot.automation_paused_global or not subscriber.automation_enabled:
        return

    ctx = ReplyContext(
        master_prompt=bot.master_prompt,
        guidelines=bot.guidelines,
        subscriber_handle=subscriber.handle,
        subscriber_uuid=subscriber.fanvue_user_uuid,
        llm_context=subscriber.llm_context or {},
        facts=facts_dict(db, subscriber),
        recent_messages=recent_thread(db, subscriber),
    )

    text, ppv_price = await gen.generate(ctx)

    if subscriber.pending_ppv_message_uuid and subscriber.exit_threshold is None:
        subscriber.exit_threshold = random.randint(
            settings.exit_messages_min, settings.exit_messages_max
        )

    if (
        subscriber.pending_ppv_message_uuid
        and subscriber.exit_threshold is not None
        and subscriber.messages_since_ppv_offer >= subscriber.exit_threshold
    ):
        text = bot.exit_message
        ppv_price = None

    price_out = ppv_price or settings.default_ppv_price_cents
    price_out = price_out if price_out and price_out >= 300 else None

    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = await fanvue.send_chat_message(
            subscriber.fanvue_user_uuid,
            text=text,
            price_cents=price_out,
            client=client,
        )

    data = payload.get("data") if isinstance(payload, dict) else None
    fanvue_msg_uuid = None
    if isinstance(data, dict):
        fanvue_msg_uuid = data.get("uuid")

    local_id = fanvue_msg_uuid or str(uuid.uuid4())
    db.add(
        ChatMessage(
            fanvue_message_uuid=local_id,
            subscriber_id=subscriber.id,
            direction="outbound",
            body=text,
            had_pricing=bool(price_out),
        )
    )

    if price_out and fanvue_msg_uuid:
        subscriber.pending_ppv_message_uuid = fanvue_msg_uuid
        subscriber.messages_since_ppv_offer = 0
        subscriber.exit_threshold = None

    subscriber.updated_at = datetime.utcnow()
    db.commit()


async def send_ppv_offer(
    db: Session,
    subscriber: Subscriber,
    fanvue: FanvueClient,
    *,
    template_uuid: str | None = None,
    text: str | None = None,
    price_cents: int | None = None,
    media_uuids: list[str] | None = None,
) -> dict[str, object]:
    """Send a saved Fanvue chat template or a custom message with optional PPV (price >= 300 cents).

    Templates are managed in Fanvue (chat message templates); we resolve preview text/price via GET then POST templateUuid.
    """
    if template_uuid:
        if text or price_cents is not None or media_uuids:
            raise ValueError("Use either template_uuid or custom text/price/media — not both")

    preview_text = ""
    price_for_tracking: int | None = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        if template_uuid:
            detail = await fanvue.get_chat_template(template_uuid, client=client)
            data = detail.get("data") if isinstance(detail, dict) else None
            if isinstance(data, dict):
                preview_text = (data.get("text") or "").strip()
                p = data.get("price")
                if p is not None:
                    try:
                        pi = int(p)
                        if pi >= 300:
                            price_for_tracking = pi
                    except (TypeError, ValueError):
                        pass
            payload = await fanvue.send_chat_message(
                subscriber.fanvue_user_uuid,
                template_uuid=template_uuid,
                client=client,
            )
            stored_body = preview_text or None
        else:
            t = (text or "").strip()
            if not t:
                raise ValueError("Message text is required when not using a template")
            if price_cents is not None and price_cents < 300:
                raise ValueError("PPV price must be at least 300 cents ($3)")
            price_out = price_cents if price_cents is not None and price_cents >= 300 else None
            payload = await fanvue.send_chat_message(
                subscriber.fanvue_user_uuid,
                text=t,
                price_cents=price_out,
                media_uuids=media_uuids or None,
                client=client,
            )
            stored_body = t
            price_for_tracking = price_out

    resp_data = payload.get("data") if isinstance(payload, dict) else None
    fanvue_msg_uuid = resp_data.get("uuid") if isinstance(resp_data, dict) else None

    local_id = fanvue_msg_uuid or str(uuid.uuid4())
    db.add(
        ChatMessage(
            fanvue_message_uuid=local_id,
            subscriber_id=subscriber.id,
            direction="outbound",
            body=stored_body,
            had_pricing=bool(price_for_tracking),
        )
    )

    if price_for_tracking and fanvue_msg_uuid:
        subscriber.pending_ppv_message_uuid = fanvue_msg_uuid
        subscriber.messages_since_ppv_offer = 0
        subscriber.exit_threshold = None

    subscriber.updated_at = datetime.utcnow()
    db.commit()

    return {
        "fanvue_message_uuid": fanvue_msg_uuid or local_id,
        "had_pricing": bool(price_for_tracking),
        "template_uuid": template_uuid,
    }


def refresh_ppv_purchase_state(db: Session, subscriber: Subscriber, messages_payload: dict) -> None:
    pending = subscriber.pending_ppv_message_uuid
    if not pending:
        return
    for item in messages_payload.get("data") or []:
        if item.get("uuid") != pending:
            continue
        if item.get("purchasedAt"):
            subscriber.pending_ppv_message_uuid = None
            subscriber.messages_since_ppv_offer = 0
            subscriber.exit_threshold = None
            subscriber.updated_at = datetime.utcnow()
            db.commit()
        break


def ingest_message_row(
    db: Session,
    subscriber: Subscriber,
    *,
    fanvue_message_uuid: str,
    body: str | None,
    sender_uuid: str,
    creator_uuid: str,
    pricing: dict | None,
    purchased_at: str | None,
    sent_at: str | None,
) -> bool:
    """Persist message if new. Returns True if this row was inbound from fan."""
    exists = (
        db.query(ChatMessage).filter(ChatMessage.fanvue_message_uuid == fanvue_message_uuid).first()
    )
    if exists:
        return False

    direction = "inbound" if sender_uuid != creator_uuid else "outbound"
    had_pricing = bool(pricing)

    db.add(
        ChatMessage(
            fanvue_message_uuid=fanvue_message_uuid,
            subscriber_id=subscriber.id,
            direction=direction,
            body=body,
            had_pricing=had_pricing,
            purchased_at_raw=purchased_at,
            sent_at=sent_at,
        )
    )

    if direction == "inbound" and subscriber.pending_ppv_message_uuid:
        subscriber.messages_since_ppv_offer += 1

    subscriber.updated_at = datetime.utcnow()
    db.commit()
    return direction == "inbound"
