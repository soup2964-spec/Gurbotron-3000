"""Poll Fanvue chats + ingest + automated replies."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.orm import Session, selectinload

from app.automation import compose_and_maybe_send, ingest_message_row, refresh_ppv_purchase_state
from app.config import settings
from app.db import SessionLocal
from app.fanvue import FanvueClient
from app.models import Subscriber

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def upsert_subscriber(db: Session, user: dict) -> Subscriber:
    uid = user["uuid"]
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == uid).first()
    if sub:
        sub.handle = user.get("handle")
        sub.display_name = user.get("displayName")
        db.commit()
        return sub
    sub = Subscriber(
        fanvue_user_uuid=uid,
        handle=user.get("handle"),
        display_name=user.get("displayName"),
        llm_context={},
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


async def poll_once() -> None:
    if not settings.fanvue_access_token or not settings.fanvue_creator_uuid:
        logger.warning("FANVUE_ACCESS_TOKEN or FANVUE_CREATOR_UUID missing — skipping poll")
        return

    fanvue = FanvueClient()
    creator = settings.fanvue_creator_uuid

    async with httpx.AsyncClient(timeout=60.0) as client:
        chats_payload = await fanvue.list_chats(page=1, size=30, filters=["subscribers"], client=client)

    chats = chats_payload.get("data") or []
    db = SessionLocal()
    try:
        for chat in chats:
            user = chat.get("user") or {}
            uid = user.get("uuid")
            if not uid:
                continue
            subscriber = upsert_subscriber(db, user)

            async with httpx.AsyncClient(timeout=60.0) as http:
                msg_payload = await fanvue.list_messages(
                    uid, page=1, size=50, mark_as_read=False, client=http
                )

            refresh_ppv_purchase_state(db, subscriber, msg_payload)
            db.refresh(subscriber)

            rows = msg_payload.get("data") or []

            def sort_key(m):
                return m.get("sentAt") or ""

            rows_sorted = sorted(rows, key=sort_key)

            had_new_inbound = False
            for m in rows_sorted:
                mid = m.get("uuid")
                sender = m.get("sender") or {}
                sid = sender.get("uuid")
                if not mid or not sid:
                    continue
                if ingest_message_row(
                    db,
                    subscriber,
                    fanvue_message_uuid=mid,
                    body=m.get("text"),
                    sender_uuid=sid,
                    creator_uuid=creator,
                    pricing=m.get("pricing"),
                    purchased_at=m.get("purchasedAt"),
                    sent_at=m.get("sentAt"),
                ):
                    had_new_inbound = True

            if had_new_inbound:
                sub_for_llm = (
                    db.query(Subscriber)
                    .options(selectinload(Subscriber.facts))
                    .filter(Subscriber.id == subscriber.id)
                    .first()
                )
                if sub_for_llm:
                    await compose_and_maybe_send(db, sub_for_llm, fanvue)
    except Exception:
        logger.exception("poll_once failed")
    finally:
        db.close()


_loop_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


async def worker_loop(stop: asyncio.Event):
    while not stop.is_set():
        await poll_once()
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)
        except asyncio.TimeoutError:
            pass


async def shutdown_worker():
    global _loop_task
    if _stop_event:
        _stop_event.set()
    if _loop_task:
        try:
            await _loop_task
        finally:
            _loop_task = None


def start_background_worker() -> asyncio.Event:
    global _loop_task, _stop_event
    _stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    _loop_task = loop.create_task(worker_loop(_stop_event))
    return _stop_event
