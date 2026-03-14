"""
main.py
-------
This is the entry point of our entire application.
Running this file starts the web server.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.query import router

# Create the FastAPI application
app = FastAPI(
    title="ERP Query Agent",
    description="Natural language to MongoDB query agent for school ERP systems",
    version="1.0.0"
)


# CORS Middleware: Allows web browsers to call our API
# WHY? By default browsers block cross-origin requests for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for development)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register our routes
app.include_router(router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to ERP Query Agent!",
        "docs": "Visit /docs for interactive API documentation",
        "health": "/api/health",
        "query": "POST /api/query"
    }

# This runs when you execute: python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)