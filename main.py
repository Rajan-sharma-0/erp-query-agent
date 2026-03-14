
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.query import router

app = FastAPI(
    title="ERP Query Agent",
    description="Natural language to MongoDB query agent for school ERP systems",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to ERP Query Agent!",
        "docs": "Visit /docs for interactive API documentation",
        "health": "/api/health",
        "query": "POST /api/query"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)