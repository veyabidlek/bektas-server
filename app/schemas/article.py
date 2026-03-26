from pydantic import BaseModel, ConfigDict


class CommentCreate(BaseModel):
    author: str
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


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    description: str
    date: str
    read_time: str
    body: list[str]
    comments: list[CommentOut]
