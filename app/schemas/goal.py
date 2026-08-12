from pydantic import BaseModel


class GoalTaskOut(BaseModel):
    id: str
    node_id: str
    title: str
    description: str
    done: bool
    done_at: str | None
    due_at: str | None
    #: True when `due_at` is a plain day rather than a moment — the client
    #: renders "20 Aug" instead of "20 Aug 14:30". Same flag `TaskOut` carries.
    due_all_day: bool
    position: int


class GoalTaskCreate(BaseModel):
    title: str
    description: str = ""
    due_at: str | None = None


class GoalTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: str | None = None
    done: bool | None = None


class GoalNodeOut(BaseModel):
    id: str
    goal_id: str
    parent_id: str | None
    title: str
    description: str
    position: int
    tasks: list[GoalTaskOut]
    #: Filled in by the tree builder — a node's own children, already ordered.
    children: list["GoalNodeOut"] = []
    #: Counts for this node ALONE (not the subtree): what the box shows.
    done_count: int = 0
    task_count: int = 0


class GoalNodeCreate(BaseModel):
    title: str
    description: str = ""
    parent_id: str | None = None


class GoalNodeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    parent_id: str | None = None


class GoalOut(BaseModel):
    """A goal without its tree — what the index lists."""

    id: str
    title: str
    description: str
    archived: bool
    created_at: str
    updated_at: str
    done_count: int
    task_count: int
    #: The soonest unfinished deadline anywhere in the goal, or None.
    next_due_at: str | None


class GoalDetail(GoalOut):
    """One goal with its whole tree nested and ordered."""

    nodes: list[GoalNodeOut]


class GoalCreate(BaseModel):
    title: str
    description: str = ""


class GoalUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    archived: bool | None = None


class AiDraftRequest(BaseModel):
    """A sentence about what he wants to get good at."""

    goal: str


class AiDraftNode(BaseModel):
    title: str
    description: str = ""
    children: list["AiDraftNode"] = []


class AiDraftOut(BaseModel):
    """A proposal, not a saved thing — he confirms before it is written."""

    nodes: list[AiDraftNode]


class AiTaskSuggestion(BaseModel):
    title: str
    description: str = ""


class AiTasksOut(BaseModel):
    tasks: list[AiTaskSuggestion]
