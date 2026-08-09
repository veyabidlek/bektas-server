from pydantic import BaseModel


class SearchHit(BaseModel):
    """One thing found.

    `kind` + `ref` is the deep link: the client owns the routing table, so a URL
    change never means a backend deploy. `date` is what the thing is *about* —
    the diary day, the event start, the writing's publish date — because that is
    what tells two similar-looking hits apart.
    """

    kind: str
    ref: str
    title: str
    snippet: str
    date: str


class SearchResults(BaseModel):
    """Grouped by kind, ranked within each group.

    Groups stay in the response when empty so the client renders from a fixed
    shape rather than guessing which keys arrived.
    """

    query: str
    total: int
    articles: list[SearchHit] = []
    diary: list[SearchHit] = []
    tasks: list[SearchHit] = []
    events: list[SearchHit] = []
    inbox: list[SearchHit] = []
