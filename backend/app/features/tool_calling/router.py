from fastapi import APIRouter

from .schemas import FunctionTemplateOut, ToolCallingRequest, ToolCallingResponse
from .service import list_function_templates, run_tool_calling

router = APIRouter(prefix="/api/tool-calling", tags=["tool-calling"])


@router.get("/templates", response_model=list[FunctionTemplateOut])
def templates() -> list[FunctionTemplateOut]:
    return list_function_templates()


@router.post("/run", response_model=ToolCallingResponse)
def run(request: ToolCallingRequest) -> ToolCallingResponse:
    return run_tool_calling(request.query, request.functions)
