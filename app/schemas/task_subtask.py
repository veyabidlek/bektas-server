from pydantic import BaseModel, field_validator


class TaskSubtaskOut(BaseModel):
    id: str
    title: str
    done: bool = False
    position: int = 0


class TaskSubtaskCreate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # A blank line in a checklist is a tick nobody can interpret.
        text = value.strip()
        if not text:
            raise ValueError("a subtask needs a title")
        return text


class TaskSubtaskUpdate(BaseModel):
    #: Omitted means "leave it" — the same `exclude_unset` convention the task
    #: schemas use, so ticking a line cannot blank its title.
    title: str | None = None
    done: bool | None = None
    position: int | None = None

    @field_validator("title")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("a subtask needs a title")
        return text
