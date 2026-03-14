from app.services.intent_detector import detect_intent
from app.services.mongo_service import execute_query, get_schema_info
from app.services.llm_service import generate_mongo_query, format_response
import json
from datetime import datetime


def process_pipeline(pipeline: list) -> list:
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

        pipeline = process_pipeline(pipeline)
    results = execute_query(collection, pipeline)

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
            "source":          source,
            "explanation":     explanation,
            "pipeline_preview": str(pipeline)[:500],
        },
        "results_count": count,
        "raw_results":   results[:10],
        "response":      friendly_response
    }