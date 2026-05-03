from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    master_prompt: Mapped[str] = mapped_column(Text, default="")
    guidelines: Mapped[str] = mapped_column(Text, default="")
    exit_message: Mapped[str] = mapped_column(Text, default="")
    automation_paused_global: Mapped[bool] = mapped_column(Boolean, default=False)


class Subscriber(Base):
    """Active subscriber profile. Entire row is hard-deleted on churn."""

    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fanvue_user_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Arbitrary JSON blob merged into LLM pack (preferences, summaries, tiers, etc.)
    llm_context: Mapped[dict] = mapped_column(SQLITE_JSON, nullable=False)

    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    messages_since_ppv_offer: Mapped[int] = mapped_column(Integer, default=0)
    pending_ppv_message_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    exit_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    facts: Mapped[list[SubscriberFact]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )


class SubscriberFact(Base):
    """Structured facts the LLM can read (key/value). Deleted with subscriber on churn."""

    __tablename__ = "subscriber_facts"
    __table_args__ = (UniqueConstraint("subscriber_id", "fact_key", name="uq_subscriber_fact_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"))
    fact_key: Mapped[str] = mapped_column(String(255))
    fact_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    subscriber: Mapped[Subscriber] = relationship(back_populates="facts")


class ChatMessage(Base):
    """Mirrored Fanvue messages we have processed."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"))
    fanvue_message_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    direction: Mapped[str] = mapped_column(String(16))  # inbound | outbound
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    had_pricing: Mapped[bool] = mapped_column(Boolean, default=False)
    purchased_at_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)

    sent_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    subscriber: Mapped[Subscriber] = relationship(back_populates="messages")
