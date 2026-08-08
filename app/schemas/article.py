from pydantic import BaseModel, ConfigDict


class CommentCreate(BaseModel):
    author: str = ""
    body: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author: str
    avatar: str
    date: str
    body: str


class ArticleImageOut(BaseModel):
    id: str
    article_slug: str
    # Ready to paste into the markdown body as ![](url).
    url: str
    width: int | None = None
    height: int | None = None
    created_at: str


class ArticleSummary(BaseModel):
    slug: str
    title: str
    description: str
    date: str
    read_time: str
    comment_count: int
    archived: bool = False
    visibility: str = "public"


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    description: str
    date: str
    read_time: str
    body: list[str]
    body_md: str = ""
    archived: bool
    visibility: str = "public"
    comments: list[CommentOut]


class ArticleCreate(BaseModel):
    slug: str
    title: str
    description: str
    date: str
    read_time: str
    body: list[str] = []
    body_md: str = ""
    visibility: str = "public"


class ArticleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    date: str | None = None
    read_time: str | None = None
    body: list[str] | None = None
    body_md: str | None = None
    visibility: str | None = None
