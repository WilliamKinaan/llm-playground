from fastapi import APIRouter

from .schemas import ClassifyRequest, ClassifyResponse, DepartmentInfo, ExampleMessage, RunStatus
from .service import (
    classify_message,
    get_run_status,
    list_departments,
    list_example_messages,
    start_run,
)

router = APIRouter(prefix="/api/model-evaluation", tags=["model-evaluation"])


@router.get("/departments", response_model=list[DepartmentInfo])
def departments() -> list[DepartmentInfo]:
    return list_departments()


@router.get("/examples", response_model=list[ExampleMessage])
def examples() -> list[ExampleMessage]:
    return list_example_messages()


@router.post("/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    return classify_message(request.message)


@router.post("/run-tests", response_model=RunStatus)
def run_tests() -> RunStatus:
    return start_run()


@router.get("/run-status", response_model=RunStatus)
def run_status() -> RunStatus:
    return get_run_status()
