from fastapi import APIRouter

from .schemas import ModerationRequest, ModerationResponse
from .service import check_moderation

router = APIRouter(prefix="/api/moderation", tags=["moderation"])


@router.post("/check", response_model=ModerationResponse)
def check(request: ModerationRequest) -> ModerationResponse:
    return check_moderation(request.text)
