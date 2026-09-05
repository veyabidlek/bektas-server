from pydantic import BaseModel, field_validator


class TaskTagOut(BaseModel):
    id: str
    name: str
    #: A palette key, not a hex string — see `models.task_tag.TaskTag.color`.
    color: str = "slate"
    position: int = 0


class TaskTagCreate(BaseModel):
    name: str
    color: str = "slate"

    @field_validator("name")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        # A blank tag is a chip with nothing on it and a filter nobody can
        # name. Refused at the edge so the service never has to wonder.
        text = value.strip()
        if not text:
            raise ValueError("a tag needs a name")
        return text


class TaskTagUpdate(BaseModel):
    #: Omitted means "leave it" — the same `exclude_unset` convention the task
    #: schemas use, so a recolour cannot blank the name.
    name: str | None = None
    color: str | None = None
    position: int | None = None

    @field_validator("name")
    @classmethod
    def _name_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("a tag needs a name")
        return text
