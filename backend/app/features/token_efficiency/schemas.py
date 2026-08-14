from pydantic import BaseModel


class SampleQuery(BaseModel):
    label: str
    query: str


class Product(BaseModel):
    name: str
    category: str
    brand: str
    price: float
    description: str


class CatalogCategory(BaseModel):
    name: str
    products: list[Product]


class StepUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChainedResult(BaseModel):
    classification: str  # raw JSON text the classifier returned
    classification_usage: StepUsage
    answer: str
    answer_usage: StepUsage
    total_tokens: int


class SingleShotResult(BaseModel):
    answer: str
    usage: StepUsage


class CompareRequest(BaseModel):
    query: str


class CompareResponse(BaseModel):
    chained: ChainedResult
    single_shot: SingleShotResult
    tokens_saved: int
    tokens_saved_pct: float
