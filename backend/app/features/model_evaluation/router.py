from fastapi import APIRouter

from .schemas import ClassifyRequest, ClassifyResponse, RunStatus
from .service import classify_message, get_run_status, start_run

router = APIRouter(prefix="/api/model-evaluation", tags=["model-evaluation"])


@router.post("/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    return classify_message(request.message)


@router.post("/run-tests", response_model=RunStatus)
def run_tests() -> RunStatus:
    return start_run()


@router.get("/run-status", response_model=RunStatus)
def run_status() -> RunStatus:
    return get_run_status()
