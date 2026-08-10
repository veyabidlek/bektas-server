from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.services import assistant as svc

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

#: What the client shows when there is no model. Says which knob is missing —
#: an assistant that is merely *off* should never read like an outage.
UNAVAILABLE = (
    "The assistant is unavailable — DEEPSEEK_API_KEY is not configured, "
    "or the model did not answer."
)


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    #: The conversation so far; only the last few turns are actually sent.
    history: list[ChatTurn] | None = None


class ChatReply(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatReply)
def chat(
    data: ChatRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Ask about his own day. Admin-only — this reads his private everything."""
    message = data.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Ask a question")

    reply = svc.answer(db, message, [t.model_dump() for t in data.history or []])
    if reply is None:
        # 503, not 500: nothing is broken, there is simply no model to answer.
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return ChatReply(reply=reply)
