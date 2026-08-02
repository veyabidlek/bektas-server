from pydantic import BaseModel


class FriendOut(BaseModel):
    id: str
    name: str
    code: str
    created_at: str
    last_seen_at: str | None = None
    revoked: bool = False

    model_config = {"from_attributes": True}
