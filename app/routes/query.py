from fastapi import APIRouter, HTTPException
from app.models.schemas import QueryRequest, QueryResponse
from app.services.query_agent import run_query

router = APIRouter(prefix="/api", tags=["Query Agent"])

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    if not request.question or len(request.question.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question too short")
    
    result = run_query(request.question.strip())
    
    return QueryResponse(
        question=result["question"],
        status=result["status"],
        response=result.get("response", "No response generated"),
        results_count=result.get("results_count"),
        query_info=result.get("query_generated") if request.show_query else None,
        error=result.get("error")
    )

@router.get("/health")
async def health_check():
    return {"status": "healthy", "message": "ERP Query Agent is running!"}

@router.get("/examples")
async def get_examples():
    return {
        "examples": [
            "List all students in Class 6",
            "Show attendance of students for today",
            "List all teachers in the system",
            "Show all assignments created today",
            "Show students who were absent yesterday",
            "List assignments due this week",
            "Show students belonging to section A of class 6",
            "Show all exams scheduled this month",
            "Count how many students were absent today",
            "Show the number of assignments submitted per class",
            "Find the class with highest number of absent students today",
            "Show students who have not submitted an assignment",
            "List teachers and the classes they teach",
            "Show attendance percentage of each student",
            "Show top 5 students with highest attendance percentage"
        ]
    }