from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.task import (
    AiCaptureOut,
    AiCaptureRequest,
    BoardInsightsOut,
    TaskAnalysisOut,
    TaskArchiveUpdate,
    TaskCreate,
    TaskDoneUpdate,
    TaskOut,
    TaskPriorityUpdate,
    TaskStatusUpdate,
    TaskTodaySummary,
    TaskUpdate,
)
from app.schemas.task_tag import TaskTagCreate, TaskTagOut, TaskTagUpdate
from app.services import task_insights, task_rules, task_tags, tasks_ai
from app.services import tasks as svc

# Admin-only, like the calendar and the diary.
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _ai_unavailable() -> str:
    """Why capture could not answer, said out loud rather than as a 500.

    ⚠️ The two causes are told apart on purpose. "DEEPSEEK_API_KEY is not
    configured" sent someone hunting for a missing key on 2026-08-23 when the
    key was present and the account was simply out of credit — a message that
    names the wrong cause is worse than a vague one, because it is actionable
    in the wrong direction.
    """
    from app.services import llm

    if not llm.configured():
        return "Capture is unavailable — DEEPSEEK_API_KEY is not configured."
    return (
        "Capture is unavailable — the model did not answer. Check the DeepSeek "
        "account (an exhausted balance answers 402) and the server log."
    )


def _load(db: Session, task_id: str):
    task = svc.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/today", response_model=TaskTodaySummary)
def get_today(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Declared before /{task_id} routes so "today" is never read as an id."""
    return svc.today_summary(db)


@router.post("/ai/capture", response_model=AiCaptureOut)
def ai_capture(
    data: AiCaptureRequest,
    _: None = Depends(require_admin),
):
    """A note in his own words → proposed tasks.

    ⚠️ Declared before `/{task_id}` and it SAVES NOTHING. The response is a
    proposal; the only thing that creates a task is him pressing Add on one.
    """
    note = data.note.strip()
    if not note:
        raise HTTPException(status_code=422, detail="Say what needs doing")
    proposals = tasks_ai.capture(note, svc.today())
    if proposals is None:
        raise HTTPException(status_code=503, detail=_ai_unavailable())
    return AiCaptureOut(tasks=proposals)


@router.get("/ai/analysis", response_model=TaskAnalysisOut)
def ai_analysis(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """What the board says.

    ⚠️ Always 200. The counts are computed here and are the useful half; the
    paragraph is the optional one, and a missing DeepSeek key drops it to
    `null` rather than failing the request. Same bargain as the weekly digest.
    """
    active = svc.list_tasks(db, include_archived=False)
    insights = task_insights.summarize(active, svc.today())
    return TaskAnalysisOut(
        insights=BoardInsightsOut(**insights.__dict__),
        summary=tasks_ai.analyse(task_insights.as_context(insights)),
    )


# ---------------------------------------------------------------- the tags
#
# ⚠️ Declared BEFORE `/{task_id}`, or FastAPI matches "tags" as a task id and
# every one of these returns 404.


def _tag_or_404(db: Session, tag_id: str):
    tag = task_tags.get_tag(db, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.get("/tags", response_model=list[TaskTagOut])
def list_tags(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return [task_tags.out(t) for t in task_tags.list_tags(db)]


@router.post("/tags", response_model=TaskTagOut, status_code=201)
def create_tag(
    data: TaskTagCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        return task_tags.out(task_tags.create_tag(db, data))
    except task_tags.TagNameTaken as exc:
        raise HTTPException(status_code=409, detail=f"«{exc}» already exists") from exc


@router.patch("/tags/{tag_id}", response_model=TaskTagOut)
def update_tag(
    tag_id: str,
    data: TaskTagUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    tag = _tag_or_404(db, tag_id)
    try:
        return task_tags.out(task_tags.update_tag(db, tag, data))
    except task_tags.TagNameTaken as exc:
        raise HTTPException(status_code=409, detail=f"«{exc}» already exists") from exc


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Drop the tag. The tasks that wore it stay, wearing one fewer."""
    task_tags.delete_tag(db, _tag_or_404(db, tag_id))


@router.get("", response_model=list[TaskOut])
def list_tasks(
    include_done: bool = True,
    include_archived: bool = False,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.list_tasks(
        db,
        include_done=include_done,
        start=start,
        end=end,
        include_archived=include_archived,
    )


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="Title is required")
    try:
        task_rules.normalize_status(data.status)
        task = svc.create_task(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except task_tags.UnknownTag as exc:
        raise HTTPException(status_code=404, detail="Tag not found") from exc
    return svc.out(task, db)


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    sent = data.model_dump(exclude_unset=True)
    # Refused rather than resolved. Both fields decide the same thing, and a
    # caller that disagrees with itself (`status="todo", done=true`) has a bug
    # that a silent precedence rule would hide until it reached the board.
    if "status" in sent and "done" in sent:
        raise HTTPException(
            status_code=422,
            detail="Send status or done, not both — done is derived from status",
        )

    task = _load(db, task_id)
    try:
        task = svc.update_task(db, task, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except task_tags.UnknownTag as exc:
        raise HTTPException(status_code=404, detail="Tag not found") from exc
    return svc.out(task, db)


@router.patch("/{task_id}/status", response_model=TaskOut)
def set_status(
    task_id: str,
    data: TaskStatusUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """A drag between board columns. Moving into Done stamps the completion."""
    task = _load(db, task_id)
    try:
        return svc.out(db=db, task=svc.set_status(db, task, data.status))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{task_id}/done", response_model=TaskOut)
def set_done(
    task_id: str,
    data: TaskDoneUpdate | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Tick or untick. With no body it toggles — that is what the checkbox sends."""
    task = _load(db, task_id)
    return svc.out(db=db, task=svc.set_done(db, task, data.done if data else None))


@router.patch("/{task_id}/priority", response_model=TaskOut)
def set_priority(
    task_id: str,
    data: TaskPriorityUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Place the task in the Eisenhower matrix, or take it back out.

    Both axes are read from the body every time, including when they are
    absent — omitting one means "un-answer it", which returns the task to the
    unsorted tray. That is deliberate: the matrix is a 2-D position, and a
    partial update would leave a card in a quadrant nobody chose.
    """
    task = _load(db, task_id)
    return svc.out(db=db, task=svc.set_priority(db, task, data.urgent, data.important))


@router.patch("/{task_id}/archive", response_model=TaskOut)
def set_archived(
    task_id: str,
    data: TaskArchiveUpdate | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Archive or restore. With no body it toggles."""
    task = _load(db, task_id)
    return svc.out(db=db, task=svc.set_archived(db, task, data.archived if data else None))


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    task = _load(db, task_id)
    svc.delete_task(db, task)
