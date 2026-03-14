
from pydantic import BaseModel
from typing import Optional, Any

class QueryRequest(BaseModel):
    question: str
    show_query: bool = False

class QueryResponse(BaseModel):
    question: str
    status: str
    response: str
    results_count: Optional[int] = None
    query_info: Optional[dict] = None
    error: Optional[str] = None