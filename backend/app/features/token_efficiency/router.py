from fastapi import APIRouter

from .schemas import CatalogCategory, CompareRequest, CompareResponse, SampleQuery
from .service import compare, get_catalog, list_sample_queries

router = APIRouter(prefix="/api/token-efficiency", tags=["token-efficiency"])


@router.get("/sample-queries", response_model=list[SampleQuery])
def sample_queries() -> list[SampleQuery]:
    return list_sample_queries()


@router.get("/catalog", response_model=list[CatalogCategory])
def catalog() -> list[CatalogCategory]:
    return get_catalog()


@router.post("/compare", response_model=CompareResponse)
def run_compare(request: CompareRequest) -> CompareResponse:
    return compare(request.query)
