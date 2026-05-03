"""Hard-delete subscriber row + cascaded facts/messages."""

from sqlalchemy.orm import Session

from app.models import Subscriber


def purge_subscriber_by_fanvue_uuid(db: Session, fanvue_user_uuid: str) -> bool:
    sub = db.query(Subscriber).filter(Subscriber.fanvue_user_uuid == fanvue_user_uuid).first()
    if sub is None:
        return False
    db.delete(sub)
    db.commit()
    return True
