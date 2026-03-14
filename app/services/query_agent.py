"""
query_agent.py
--------------
Orchestrates the full query pipeline.

STRATEGY (most reliable → least reliable):
  1. Intent Detector  → handles all 15 assignment queries, 100% reliable
  2. Ollama AI        → fallback for unrecognized/custom queries
  3. Manual Fallback  → if Ollama fails entirely

WHY this order?
  gemma3:1b is a 1B parameter model — great for speed on CPU,
  but too small to reliably generate complex MongoDB JSON.
  Intent detector bypasses AI for all known query patterns.
"""

from app.services.intent_detector import detect_intent
from app.services.mongo_service import execute_query, get_schema_info
from app.services.llm_service import generate_mongo_query, format_response
import json
from datetime import datetime


def process_pipeline(pipeline: list) -> list:
    """
    Converts {"$date": "ISO_STRING"} → Python datetime objects.
    Only needed for AI-generated pipelines (intent detector uses
    real datetime objects directly, so no conversion needed).
    """
    def convert(obj):
        if isinstance(obj, dict):
            if "$date" in obj and len(obj) == 1:
                date_str = obj["$date"].replace("Z", "").replace(".000", "")
                try:
                    return datetime.fromisoformat(date_str)
                except Exception:
                    return datetime.now().replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(item) for item in obj]
        return obj

    return convert(pipeline)


def run_query(user_question: str) -> dict:
    """
    Main entry point called by the API route.

    Returns a dict with:
      - question      : original question
      - status        : "success" | "error"
      - response      : friendly English answer
      - results_count : number of DB records returned
      - query_generated: pipeline info (for /api/query with show_query=true)
      - raw_results   : first 10 raw records (for debugging)
      - error         : error message if status == "error"
    """

    intent = detect_intent(user_question)

    if intent:
        collection  = intent["collection"]
        pipeline    = intent["pipeline"]
        explanation = intent["explanation"]
        source      = "intent_detector"

    else:
        schema     = get_schema_info()
        llm_result = generate_mongo_query(user_question, schema)

        if not llm_result["success"]:
            return {
                "question": user_question,
                "status":   "error",
                "error":    llm_result["error"],
                "response": (
                    "Sorry, I couldn't process that question. "
                    "Try rephrasing it, e.g. 'list all students' or "
                    "'show absent students today'."
                )
            }

        query_data  = llm_result["data"]
        collection  = query_data["collection"]
        pipeline    = query_data["pipeline"]
        explanation = query_data.get("explanation", "AI-generated query")
        source      = "ollama_ai"

        # Convert any {"$date": "..."} strings to Python datetime
        pipeline = process_pipeline(pipeline)
    results = execute_query(collection, pipeline)

    # execute_query returns a dict with "error" key on failure
    if isinstance(results, dict) and "error" in results:
        return {
            "question": user_question,
            "status":   "error",
            "error":    results["error"],
            "response": f"Database error: {results['error']}"
        }

    count = len(results)

    friendly_response = format_response(user_question, results, explanation)

    return {
        "question": user_question,
        "status":   "success",
        "query_generated": {
            "collection":      collection,
            "source":          source,        # "intent_detector" or "ollama_ai"
            "explanation":     explanation,
            "pipeline_preview": str(pipeline)[:500],
        },
        "results_count": count,
        "raw_results":   results[:10],
        "response":      friendly_response
    }