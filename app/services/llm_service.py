"""
llm_service.py
--------------
Uses LOCAL Ollama + gemma3:1b (optimized for AMD Ryzen CPU)
- num_thread: 8     → uses all Ryzen cores
- num_ctx: 2048     → smaller context = faster
- num_predict: 800  → fewer max tokens = faster
- Short prompts     → less to process = faster

Expected speed: 15-30 seconds per query on Ryzen 5000
"""

import os
import json
import re
import ollama
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# Get model name from .env
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")

def get_current_datetime_context() -> str:
    """
    Returns current date/time info injected into the prompt.
    WHY? So the model knows what "today", "yesterday", "this week"
    means in actual real dates when building date filters.
    """
    now = datetime.now()
    today_start     = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start  = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)

    week_start = today_start - timedelta(days=today_start.weekday())
    week_end   = week_start + timedelta(days=7)

    month_start = today_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    return f"""DATES:
today_start={today_start.isoformat()}
today_end={tomorrow_start.isoformat()}
yesterday_start={yesterday_start.isoformat()}
yesterday_end={today_start.isoformat()}
week_start={week_start.isoformat()}
week_end={week_end.isoformat()}
month_start={month_start.isoformat()}
month_end={month_end.isoformat()}"""


def generate_mongo_query(user_question: str, schema_info: str) -> dict:
    datetime_context = get_current_datetime_context()

    prompt = f"""
You are an expert MongoDB aggregation pipeline generator for a school ERP system.

{schema_info}

{datetime_context}

USER QUESTION: "{user_question}"

YOUR JOB: Generate a MongoDB aggregation pipeline JSON to answer this question.

============================
OUTPUT FORMAT (strict JSON):
============================
{{
    "collection": "the_starting_collection",
    "pipeline": [ ...stages... ],
    "explanation": "one line description"
}}

============================
CRITICAL RULES:
============================
1. Output ONLY raw JSON — no markdown, no ```json, no explanation outside JSON
2. For "list all X" or "show all X" with NO filters → use EMPTY pipeline: []
   Example: "show all students" → pipeline: [{{"$limit": 200}}]
3. NEVER apply date filters unless the question explicitly mentions a date/time word
   (today, yesterday, this week, this month, specific date)
4. NEVER filter on class_id using dates — class_id is an ObjectId, NOT a date
5. For $lookup always use:
   - localField: the field in current collection that holds the foreign _id
   - foreignField: "_id"  ← almost always "_id"

============================
QUERY PATTERNS (follow exactly):
============================

PATTERN A — List all with no filter:
Question: "list all students" / "show all teachers" / "show students list"
→ {{
    "collection": "students",
    "pipeline": [
        {{"$project": {{"name": 1, "roll_number": 1, "section": 1, "_id": 0}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Returns all students"
}}

PATTERN B — Filter by class name:
Question: "students in class 6"
→ {{
    "collection": "classes",
    "pipeline": [
        {{"$match": {{"name": "Class 6"}}}},
        {{"$lookup": {{
            "from": "students",
            "localField": "_id",
            "foreignField": "class_id",
            "as": "students"
        }}}},
        {{"$unwind": "$students"}},
        {{"$replaceRoot": {{"newRoot": "$students"}}}},
        {{"$project": {{"name": 1, "roll_number": 1, "section": 1, "_id": 0}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Finds Class 6, then gets all students in it"
}}

PATTERN C — Filter by class AND section:
Question: "students in section A of class 6"
→ {{
    "collection": "classes",
    "pipeline": [
        {{"$match": {{"name": "Class 6", "section": "A"}}}},
        {{"$lookup": {{
            "from": "students",
            "localField": "_id",
            "foreignField": "class_id",
            "as": "students"
        }}}},
        {{"$unwind": "$students"}},
        {{"$replaceRoot": {{"newRoot": "$students"}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Finds Class 6 Section A, then gets students"
}}

PATTERN D — Absent students TODAY:
→ {{
    "collection": "attendance",
    "pipeline": [
        {{"$match": {{
            "status": "absent",
            "date": {{
                "$gte": {{"$date": "TODAY_START_ISO"}},
                "$lt": {{"$date": "TOMORROW_START_ISO"}}
            }}
        }}}},
        {{"$lookup": {{
            "from": "students",
            "localField": "student_id",
            "foreignField": "_id",
            "as": "student"
        }}}},
        {{"$unwind": "$student"}},
        {{"$project": {{"_id": 0, "name": "$student.name", "roll_number": "$student.roll_number", "date": 1}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Gets absent attendance records for today with student names"
}}

PATTERN E — Attendance percentage per student:
→ {{
    "collection": "attendance",
    "pipeline": [
        {{"$group": {{
            "_id": "$student_id",
            "total": {{"$sum": 1}},
            "present": {{"$sum": {{"$cond": [{{"$eq": ["$status", "present"]}}, 1, 0]}}}}
        }}}},
        {{"$lookup": {{
            "from": "students",
            "localField": "_id",
            "foreignField": "_id",
            "as": "student"
        }}}},
        {{"$unwind": "$student"}},
        {{"$project": {{
            "_id": 0,
            "name": "$student.name",
            "roll_number": "$student.roll_number",
            "attendance_percentage": {{
                "$round": [{{"$multiply": [{{"$divide": ["$present", "$total"]}}, 100]}}, 2]
            }}
        }}}},
        {{"$sort": {{"attendance_percentage": -1}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Calculates attendance percentage for each student"
}}

PATTERN F — Top 5 by attendance:
Same as PATTERN E but add {{"$limit": 5}} at end.

PATTERN G — Assignments due this week:
→ {{
    "collection": "assignments",
    "pipeline": [
        {{"$match": {{
            "due_date": {{
                "$gte": {{"$date": "WEEK_START_ISO"}},
                "$lt": {{"$date": "WEEK_END_ISO"}}
            }}
        }}}},
        {{"$project": {{"title": 1, "due_date": 1, "_id": 0}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Gets assignments due this week"
}}

PATTERN H — Students who haven't submitted assignment:
→ {{
    "collection": "students",
    "pipeline": [
        {{"$lookup": {{
            "from": "assignments",
            "let": {{"sid": "$_id"}},
            "pipeline": [
                {{"$match": {{
                    "$expr": {{"$in": ["$$sid", "$submissions.student_id"]}}
                }}}}
            ],
            "as": "submitted_assignments"
        }}}},
        {{"$match": {{"submitted_assignments": {{"$size": 0}}}}}},
        {{"$project": {{"name": 1, "roll_number": 1, "_id": 0}}}},
        {{"$limit": 200}}
    ],
    "explanation": "Finds students with zero assignment submissions"
}}

PATTERN I — Teachers and their classes:
→ {{
    "collection": "teachers",
    "pipeline": [
        {{"$lookup": {{
            "from": "classes",
            "localField": "_id",
            "foreignField": "teacher_id",
            "as": "classes"
        }}}},
        {{"$project": {{
            "_id": 0,
            "name": 1,
            "subject": 1,
            "classes": {{"$map": {{
                "input": "$classes",
                "as": "c",
                "in": {{"$concat": ["$$c.name", " - ", "$$c.section"]}}
            }}}}
        }}}},
        {{"$limit": 200}}
    ],
    "explanation": "Lists each teacher with the classes they teach"
}}

PATTERN J — Count absent students today (aggregation):
→ {{
    "collection": "attendance",
    "pipeline": [
        {{"$match": {{
            "status": "absent",
            "date": {{
                "$gte": {{"$date": "TODAY_START_ISO"}},
                "$lt": {{"$date": "TOMORROW_START_ISO"}}
            }}
        }}}},
        {{"$count": "absent_count"}}
    ],
    "explanation": "Counts absent records for today"
}}

============================
SUBSTITUTE REAL DATES:
TODAY_START_ISO = {datetime_context.split("Today start:")[1].split("→")[0].strip() if "Today start:" in datetime_context else "use today's date"}
============================

Now generate for: "{user_question}"
REMEMBER: Output ONLY the JSON object, nothing else.
"""

    try:
        response = ollama.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={
                "temperature": 0.2,
                "num_predict": 800,
                "num_ctx": 2048,
                "num_thread": 8,
            }
        )
        raw_text = response["response"].strip()

        # Strip markdown code fences if AI adds them anyway
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.MULTILINE)
        raw_text = re.sub(r'\s*```$', '', raw_text, flags=re.MULTILINE)
        raw_text = raw_text.strip()

        query_data = json.loads(raw_text)

        if "collection" not in query_data or "pipeline" not in query_data:
            raise ValueError("Missing 'collection' or 'pipeline' in AI response")

        return {"success": True, "data": query_data}

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"AI returned invalid JSON: {str(e)}",
            "raw": raw_text if 'raw_text' in locals() else "no response"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def format_response(user_question: str, query_results: list, query_explanation: str) -> str:
    """
    Converts raw MongoDB results into a friendly English response.

    WHY separate step? Raw results look like:
      [{"name": "Ali", "roll_number": "ROLL1001"}, ...]
    We want:
      "3 students were absent today: Ali (ROLL1001), Sara (ROLL1002)..."
    """

    total_count    = len(query_results)

    # Only send first 10 records to model — enough to format nicely + saves tokens
    results_sample = query_results[:10] if total_count > 10 else query_results

    # Handle empty results immediately without calling the model
    if total_count == 0:
        return f"No records found for: '{user_question}'. The database returned 0 results."

    prompt = f"""You are a school ERP assistant. Answer the user's question using the data below.

Question: "{user_question}"
Query did: {query_explanation}
Total records: {total_count}
{"(Showing first 10 of " + str(total_count) + ")" if total_count > 10 else ""}

Data:
{json.dumps(results_sample, indent=2, default=str)}

Write a short, clear, friendly answer. Plain text only. No markdown."""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            options={
                "temperature": 0.3,
                "num_predict": 400,  # formatting needs fewer tokens
                "num_ctx":     2048,
                "num_thread":  8,
            }
        )
        return response["message"]["content"].strip()

    except Exception as e:
        # Fallback: format manually without AI
        print(f"⚠️ Format response failed: {e}, using fallback")
        lines = [f"Found {total_count} records:"]
        for i, record in enumerate(query_results[:10], 1):
            # Show name + one other field if available
            name = record.get("name", record.get("title", f"Record {i}"))
            lines.append(f"  {i}. {name}")
        if total_count > 10:
            lines.append(f"  ... and {total_count - 10} more.")
        return "\n".join(lines)