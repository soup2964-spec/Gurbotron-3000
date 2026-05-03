"""LLM backend plug-in: swap StubReplyGenerator for your provider."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ReplyContext:
    master_prompt: str
    guidelines: str
    subscriber_handle: str | None
    subscriber_uuid: str
    llm_context: dict
    facts: dict[str, str]
    recent_messages: list[tuple[str, str]]  # (role, text) role in fan|creator


class ReplyGenerator(Protocol):
    async def generate(self, ctx: ReplyContext) -> tuple[str, int | None]:
        """Return (plain_text_reply, ppv_price_cents_or_none)."""


class StubReplyGenerator:
    """Placeholder until you wire a real model."""

    async def generate(self, ctx: ReplyContext) -> tuple[str, int | None]:
        facts_preview = ", ".join(f"{k}={v}" for k, v in list(ctx.facts.items())[:5])
        tail = ""
        if facts_preview:
            tail = f" (I remember: {facts_preview})"
        return (
            f"[auto/stub] hey love thanks for texting 💕 wire a real LLM in app/llm.py.{tail}",
            None,
        )


default_generator: ReplyGenerator = StubReplyGenerator()
