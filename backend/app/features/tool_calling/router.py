from fastapi import APIRouter

from .schemas import ToolCallingRequest, ToolCallingResponse
from .service import run_tool_calling

router = APIRouter(prefix="/api/tool-calling", tags=["tool-calling"])


@router.post("/run", response_model=ToolCallingResponse)
def run(request: ToolCallingRequest) -> ToolCallingResponse:
    return run_tool_calling(request.query, request.functions)
