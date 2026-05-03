from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///./") or url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        if "./" in raw:
            raw = raw.split("./", 1)[-1]
        path = Path(raw)
        if path.parent.parts:
            path.parent.mkdir(parents=True, exist_ok=True)


def make_engine(database_url: str):
    _ensure_sqlite_dir(database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    eng = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine = None  # set by init_db
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)


def init_db(database_url: str):
    global engine
    engine = make_engine(database_url)
    SessionLocal.configure(bind=engine)
    from app import models  # noqa: F401 — register models

    Base.metadata.create_all(bind=engine)
    _ensure_bot_settings()


def _ensure_bot_settings():
    from app.models import BotSettings

    with SessionLocal() as db:
        row = db.query(BotSettings).filter(BotSettings.id == 1).one_or_none()
        if row is None:
            db.add(
                BotSettings(
                    id=1,
                    master_prompt="You are a friendly creator chatting with a subscriber.",
                    guidelines=(
                        "Be warm and concise. Occasionally offer exclusive PPV content when it fits the conversation. "
                        "If they haven't unlocked your last offer after many messages, politely excuse yourself."
                    ),
                    exit_message=(
                        "omg someone just tipped me — i gotta jump off for a sec, chat soon xoxo 💕"
                    ),
                    automation_paused_global=False,
                )
            )
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
