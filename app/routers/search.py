from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.dependencies import require_admin
from app.schemas.search import SearchResults
from app.services import search as svc
from app.services.search_index import rebuild_search_index

# Admin-only, all of it. Search reaches across the diary and the inbox, so even
# a public writing surfaces here through the private view — there is no version
# of this endpoint that is safe to leave open.
router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResults)
def search(
    q: str = "",
    limit: int = 6,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """One box, everything he owns. A too-short or meaningless query returns
    empty groups rather than an error — the panel asks on every keystroke."""
    return svc.search(db, q, limit=min(max(limit, 1), 25))


@router.post("/reindex")
def reindex(_: None = Depends(require_admin)):
    """Rebuild the index from the source tables.

    Only needed after a write that bypassed the triggers — a restored backup,
    say. Normal use never touches this.
    """
    return {"indexed": rebuild_search_index(engine)}
