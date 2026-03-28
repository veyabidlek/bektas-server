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


class ArticleSummary(BaseModel):
    slug: str
    title: str
    description: str
    date: str
    read_time: str
    comment_count: int
    archived: bool = False


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    description: str
    date: str
    read_time: str
    body: list[str]
    archived: bool
    comments: list[CommentOut]


class ArticleCreate(BaseModel):
    slug: str
    title: str
    description: str
    date: str
    read_time: str
    body: list[str]


class ArticleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    date: str | None = None
    read_time: str | None = None
    body: list[str] | None = None
