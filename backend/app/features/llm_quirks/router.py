from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .schemas import CaseDetail, CaseSummary, RunResponse
from .service import get_case, list_cases, run_case, run_case_stream

router = APIRouter(prefix="/api/llm-quirks", tags=["llm-quirks"])


@router.get("/cases", response_model=list[CaseSummary])
def cases() -> list[CaseSummary]:
    return list_cases()


@router.get("/cases/{case_id}", response_model=CaseDetail)
def case_detail(case_id: str) -> CaseDetail:
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    return case


@router.post("/cases/{case_id}/run", response_model=RunResponse)
def run(case_id: str) -> RunResponse:
    result = run_case(case_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    return result


@router.post("/cases/{case_id}/run-stream")
def run_stream(case_id: str) -> StreamingResponse:
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    return StreamingResponse(
        run_case_stream(case_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
