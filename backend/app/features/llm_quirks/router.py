from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.rate_limiter import reserve

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
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    # All variants run for one click - reserve the whole known count upfront
    # so a run either fully succeeds or fails cleanly.
    reserve(len(case.variants))
    return run_case(case_id)


@router.post("/cases/{case_id}/run-stream")
def run_stream(case_id: str) -> StreamingResponse:
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case '{case_id}'")
    # Must reserve *before* constructing StreamingResponse: once streaming
    # starts, the HTTP status is already sent, so a check inside the
    # generator could no longer turn into a 429.
    reserve(len(case.variants))
    return StreamingResponse(
        run_case_stream(case_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
