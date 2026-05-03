"""FastAPI entry: dashboard + subscriber memory APIs + worker lifecycle."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.automation import facts_dict, recent_thread, send_ppv_offer
from app.churn import purge_subscriber_by_fanvue_uuid
from app.config import settings
from app.db import get_db, init_db
from app.fanvue import FanvueClient
from app.models import BotSettings, Subscriber, SubscriberFact
from app.worker import poll_once, shutdown_worker, start_background_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["tojsonpretty"] = lambda v: json.dumps(v or {}, indent=2, ensure_ascii=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings.database_url)
    start_background_worker()
    logger.info("Gurbotron worker started")
    yield
    await shutdown_worker()
    logger.info("Gurbotron worker stopped")


app = FastAPI(title="Gurbotron-3000", lifespan=lifespan)


class BotSettingsPatch(BaseModel):
    master_prompt: str | None = None
    guidelines: str | None = None
    exit_message: str | None = None
    automation_paused_global: bool | None = None


class LLMContextPatch(BaseModel):
    llm_context: dict = Field(default_factory=dict)


class FactBody(BaseModel):
    value: str


class SendPpvBody(BaseModel):
    """Either send a saved Fanvue chat template, or a custom message."""

    template_uuid: str | None = None
    text: str | None = None
    price_cents: int | None = None
    media_uuids: list[str] | None = None


async def _fetch_chat_templates() -> tuple[list[dict], str | None]:
    """Load creator chat templates from Fanvue for dashboard / API."""
    if not settings.fanvue_access_token:
        return [], None
    try:
        fv = FanvueClient()
        async with httpx.AsyncClient(timeout=45.0) as client:
            payload = await fv.list_chat_templates(page=1, size=50, client=client)
        rows = payload.get("data")
        if isinstance(rows, list):
            return rows, None
        return [], "Fanvue templates response missing data array"
    except httpx.HTTPError:
        logger.exception("Fanvue chat templates request failed")
        return [], "Could not load templates from Fanvue (check token and scopes)."
    except Exception:
        logger.exception("Unexpected error loading chat templates")
        return [], "Unexpected error loading templates."


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    subs = (
        db.query(Subscriber)
        .options(selectinload(Subscriber.facts))
        .order_by(Subscriber.updated_at.desc())
        .all()
    )
    bot = db.get(BotSettings, 1)
    ppv_templates, ppv_templates_error = await _fetch_chat_templates()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "subscribers": subs,
            "bot": bot,
            "fanvue_ok": bool(settings.fanvue_access_token and settings.fanvue_creator_uuid),
            "ppv_templates": ppv_templates,
            "ppv_templates_error": ppv_templates_error,
        },
    )


@app.get("/api/settings")
def api_get_settings(db: Session = Depends(get_db)):
    bot = db.get(BotSettings, 1)
    if not bot:
        raise HTTPException(500, "bot settings missing")
    return {
        "master_prompt": bot.master_prompt,
        "guidelines": bot.guidelines,
        "exit_message": bot.exit_message,
        "automation_paused_global": bot.automation_paused_global,
    }


@app.get("/api/fanvue/chat-templates")
async def api_fanvue_chat_templates(
    page: int = 1,
    size: int = 50,
    folder_name: str | None = None,
):
    if not settings.fanvue_access_token:
        raise HTTPException(503, "FANVUE_ACCESS_TOKEN not set")
    fv = FanvueClient()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = await fv.list_chat_templates(
                page=page, size=min(max(size, 1), 50), folder_name=folder_name, client=client
            )
        return payload
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text[:1200]) from e
    except httpx.HTTPError as e:
        detail = getattr(getattr(e, "response", None), "text", None) or str(e)
        raise HTTPException(502, detail[:1200]) from e


@app.post("/api/subscribers/{fanvue_uuid}/send-ppv")
async def api_send_ppv(fanvue_uuid: str, body: SendPpvBody, db: Session = Depends(get_db)):
    if not settings.fanvue_access_token:
        raise HTTPException(503, "FANVUE_ACCESS_TOKEN not set")
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if not sub:
        raise HTTPException(404, "subscriber not found")

    tpl = (body.template_uuid or "").strip() or None
    if tpl and (body.text or body.price_cents is not None or body.media_uuids):
        raise HTTPException(
            400,
            "Send either template_uuid OR custom fields (text / price_cents / media_uuids), not both.",
        )

    fv = FanvueClient()
    try:
        if tpl:
            result = await send_ppv_offer(db, sub, fv, template_uuid=tpl)
        else:
            result = await send_ppv_offer(
                db,
                sub,
                fv,
                text=body.text,
                price_cents=body.price_cents,
                media_uuids=body.media_uuids,
            )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text[:1200]) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, str(e)) from e

    return {"ok": True, **result}


@app.patch("/api/settings")
def api_patch_settings(body: BotSettingsPatch, db: Session = Depends(get_db)):
    bot = db.get(BotSettings, 1)
    if not bot:
        raise HTTPException(500, "bot settings missing")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(bot, k, v)
    db.commit()
    return {"ok": True}


@app.get("/api/subscribers")
def api_list_subscribers(db: Session = Depends(get_db)):
    rows = db.query(Subscriber).order_by(Subscriber.updated_at.desc()).all()
    return [
        {
            "fanvue_user_uuid": s.fanvue_user_uuid,
            "handle": s.handle,
            "display_name": s.display_name,
            "automation_enabled": s.automation_enabled,
            "messages_since_ppv_offer": s.messages_since_ppv_offer,
            "pending_ppv_message_uuid": s.pending_ppv_message_uuid,
            "fact_count": len(s.facts),
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in rows
    ]


@app.get("/api/subscribers/{fanvue_uuid}/llm-pack")
def api_llm_pack(fanvue_uuid: str, db: Session = Depends(get_db)):
    """Structured bundle any LLM adapter can consume for tailored replies."""
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if not sub:
        raise HTTPException(404, "subscriber not found")
    bot = db.get(BotSettings, 1)
    return {
        "subscriber": {
            "fanvue_user_uuid": sub.fanvue_user_uuid,
            "handle": sub.handle,
            "display_name": sub.display_name,
            "llm_context": sub.llm_context or {},
            "facts": facts_dict(db, sub),
            "automation_enabled": sub.automation_enabled,
            "messages_since_ppv_offer": sub.messages_since_ppv_offer,
            "pending_ppv_offer_message_uuid": sub.pending_ppv_message_uuid,
        },
        "bot": {
            "master_prompt": bot.master_prompt if bot else "",
            "guidelines": bot.guidelines if bot else "",
            "exit_message": bot.exit_message if bot else "",
        },
        "recent_messages": [{"role": r, "text": t} for r, t in recent_thread(db, sub)],
    }


@app.patch("/api/subscribers/{fanvue_uuid}/context")
def api_patch_context(fanvue_uuid: str, body: LLMContextPatch, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if not sub:
        raise HTTPException(404, "subscriber not found")
    sub.llm_context = body.llm_context
    db.commit()
    return {"ok": True}


@app.put("/api/subscribers/{fanvue_uuid}/facts/{fact_key}")
def api_put_fact(fanvue_uuid: str, fact_key: str, body: FactBody, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if not sub:
        raise HTTPException(404, "subscriber not found")
    existing = (
        db.query(SubscriberFact)
        .filter(SubscriberFact.subscriber_id == sub.id, SubscriberFact.fact_key == fact_key)
        .first()
    )
    if existing:
        existing.fact_value = body.value
    else:
        db.add(SubscriberFact(subscriber_id=sub.id, fact_key=fact_key, fact_value=body.value))
    db.commit()
    return {"ok": True}


@app.delete("/api/subscribers/{fanvue_uuid}/facts/{fact_key}")
def api_del_fact(fanvue_uuid: str, fact_key: str, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if not sub:
        raise HTTPException(404, "subscriber not found")
    db.query(SubscriberFact).filter(
        SubscriberFact.subscriber_id == sub.id, SubscriberFact.fact_key == fact_key
    ).delete()
    db.commit()
    return {"ok": True}


@app.post("/api/subscribers/{fanvue_uuid}/churn")
def api_churn(fanvue_uuid: str, db: Session = Depends(get_db)):
    """Hard-delete subscriber memory: facts, messages, profile."""
    if not purge_subscriber_by_fanvue_uuid(db, fanvue_uuid):
        raise HTTPException(404, "subscriber not found")
    return {"ok": True, "deleted": fanvue_uuid}


@app.post("/api/worker/run-once")
async def api_run_worker_once():
    await poll_once()
    return {"ok": True}


@app.post("/dashboard/subscribers/{fanvue_uuid}/send-ppv", response_class=RedirectResponse)
async def form_send_ppv(
    fanvue_uuid: str,
    template_uuid: str = Form(""),
    ppv_custom_text: str = Form(""),
    ppv_price_cents: str = Form(""),
    ppv_media_uuids: str = Form(""),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if sub and settings.fanvue_access_token:
        fv = FanvueClient()
        tpl = template_uuid.strip()
        media_parts = [x.strip() for x in ppv_media_uuids.replace(",", " ").split() if x.strip()]
        try:
            if tpl:
                await send_ppv_offer(db, sub, fv, template_uuid=tpl)
            else:
                price_val: int | None = None
                if ppv_price_cents.strip():
                    try:
                        price_val = int(ppv_price_cents.strip())
                    except ValueError:
                        logger.warning("invalid ppv_price_cents for %s", fanvue_uuid)
                        return RedirectResponse("/", status_code=303)
                await send_ppv_offer(
                    db,
                    sub,
                    fv,
                    text=ppv_custom_text,
                    price_cents=price_val,
                    media_uuids=media_parts or None,
                )
        except ValueError:
            logger.warning("Manual PPV validation failed for %s", fanvue_uuid)
        except httpx.HTTPError:
            logger.exception("Manual PPV send failed for %s", fanvue_uuid)
    return RedirectResponse("/", status_code=303)


@app.post("/dashboard/settings", response_class=RedirectResponse)
def form_post_settings(
    master_prompt: str = Form(""),
    guidelines: str = Form(""),
    exit_message: str = Form(""),
    automation_paused_global: str | None = Form(None),
    db: Session = Depends(get_db),
):
    bot = db.get(BotSettings, 1)
    if bot:
        bot.master_prompt = master_prompt
        bot.guidelines = guidelines
        bot.exit_message = exit_message
        bot.automation_paused_global = automation_paused_global == "on"
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/dashboard/subscribers/{fanvue_uuid}/toggle", response_class=RedirectResponse)
def form_toggle_auto(fanvue_uuid: str, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if sub:
        sub.automation_enabled = not sub.automation_enabled
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/dashboard/subscribers/{fanvue_uuid}/churn", response_class=RedirectResponse)
def form_churn(fanvue_uuid: str, db: Session = Depends(get_db)):
    purge_subscriber_by_fanvue_uuid(db, fanvue_uuid)
    return RedirectResponse("/", status_code=303)


@app.post("/dashboard/subscribers/{fanvue_uuid}/context", response_class=RedirectResponse)
def form_context(
    fanvue_uuid: str,
    llm_context_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    import json

    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if sub:
        try:
            sub.llm_context = json.loads(llm_context_json or "{}")
        except json.JSONDecodeError:
            pass
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/dashboard/subscribers/{fanvue_uuid}/facts", response_class=RedirectResponse)
def form_add_fact(
    fanvue_uuid: str,
    fact_key: str = Form(""),
    fact_value: str = Form(""),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_uuid).first()
    if sub and fact_key.strip():
        existing = (
            db.query(SubscriberFact)
            .filter(SubscriberFact.subscriber_id == sub.id, SubscriberFact.fact_key == fact_key.strip())
            .first()
        )
        if existing:
            existing.fact_value = fact_value
        else:
            db.add(
                SubscriberFact(
                    subscriber_id=sub.id,
                    fact_key=fact_key.strip(),
                    fact_value=fact_value,
                )
            )
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
