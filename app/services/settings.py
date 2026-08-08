from sqlalchemy.orm import Session

from app.models.setting import Setting


def get_setting(db: Session, key: str) -> str | None:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row and row.value else None


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def delete_setting(db: Session, key: str) -> None:
    db.query(Setting).filter(Setting.key == key).delete()
    db.commit()
