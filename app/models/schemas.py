
from pydantic import BaseModel
from typing import Optional, Any

class QueryRequest(BaseModel):
    """What the API expects to receive"""
    question: str           # The user's natural language question
    show_query: bool = False  # Whether to include the generated MongoDB query in response

class QueryResponse(BaseModel):
    """What the API sends back"""
    question: str
    status: str             # "success" or "error"
    response: str           # The friendly English answer
    results_count: Optional[int] = None
    query_info: Optional[dict] = None  # MongoDB query details (if show_query=True)
    error: Optional[str] = None