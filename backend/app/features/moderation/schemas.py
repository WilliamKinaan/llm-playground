from pydantic import BaseModel, Field


class ModerationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class CategoryResult(BaseModel):
    name: str
    flagged: bool
    score: float


class ModerationResponse(BaseModel):
    flagged: bool
    categories: list[CategoryResult]
