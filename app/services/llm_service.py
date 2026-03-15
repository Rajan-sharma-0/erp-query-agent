

import os
import json
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# Configuration - Choose provider from .env
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Lazy imports - only load what's needed
def _get_ollama_module():
    import ollama
    return ollama

def _get_gemini_module():
    import google.generativeai as genai
    return genai

def _get_openai_module():
    from openai import OpenAI
    return OpenAI

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
    """
    Generate MongoDB aggregation pipeline.
    Automatically chooses provider based on LLM_PROVIDER env variable.
    
    Returns same structure regardless of backend:
    {
        "success": bool,
        "data": {
            "collection": str,
            "pipeline": list,
            "explanation": str
        },
        "error": str (if success=False)
    }
    """
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
NOW GENERATE FOR: "{user_question}"
REMEMBER: Output ONLY the JSON object, nothing else.
"""

    # Route to appropriate provider
    if LLM_PROVIDER == "gemini":
        return _generate_with_gemini(prompt)
    elif LLM_PROVIDER == "openai":
        return _generate_with_openai(prompt)
    else:
        return _generate_with_ollama(prompt)


# ============================================
# Provider-specific implementations
# ============================================

def _generate_with_ollama(prompt: str) -> dict:
    """Generate query using local Ollama"""
    try:
        ollama = _get_ollama_module()
        OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")
        
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
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.MULTILINE)
        raw_text = re.sub(r'\s*```$', '', raw_text, flags=re.MULTILINE)
        raw_text = raw_text.strip()

        query_data = json.loads(raw_text)

        if "collection" not in query_data or "pipeline" not in query_data:
            raise ValueError("Missing 'collection' or 'pipeline' in response")

        return {"success": True, "data": query_data}

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Ollama returned invalid JSON: {str(e)}",
            "raw": raw_text if 'raw_text' in locals() else "no response"
        }
    except Exception as e:
        return {"success": False, "error": f"Ollama error: {str(e)}"}


def _generate_with_gemini(prompt: str) -> dict:
    """Generate query using Google Gemini API"""
    try:
        genai = _get_gemini_module()
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        
        if not GEMINI_API_KEY:
            return {"success": False, "error": "GEMINI_API_KEY not set in .env"}
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        
        raw_text = response.text.strip()
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.MULTILINE)
        raw_text = re.sub(r'\s*```$', '', raw_text, flags=re.MULTILINE)
        raw_text = raw_text.strip()

        query_data = json.loads(raw_text)

        if "collection" not in query_data or "pipeline" not in query_data:
            raise ValueError("Missing 'collection' or 'pipeline' in response")

        return {"success": True, "data": query_data}

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Gemini returned invalid JSON: {str(e)}",
            "raw": raw_text if 'raw_text' in locals() else "no response"
        }
    except Exception as e:
        return {"success": False, "error": f"Gemini error: {str(e)}"}


def _generate_with_openai(prompt: str) -> dict:
    """Generate query using OpenAI GPT-4"""
    try:
        OpenAI = _get_openai_module()
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        
        if not OPENAI_API_KEY:
            return {"success": False, "error": "OPENAI_API_KEY not set in .env"}
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a MongoDB expert. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        raw_text = response.choices[0].message.content.strip()
        raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.MULTILINE)
        raw_text = re.sub(r'\s*```$', '', raw_text, flags=re.MULTILINE)
        raw_text = raw_text.strip()

        query_data = json.loads(raw_text)

        if "collection" not in query_data or "pipeline" not in query_data:
            raise ValueError("Missing 'collection' or 'pipeline' in response")

        return {"success": True, "data": query_data}

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"OpenAI returned invalid JSON: {str(e)}",
            "raw": raw_text if 'raw_text' in locals() else "no response"
        }
    except Exception as e:
        return {"success": False, "error": f"OpenAI error: {str(e)}"}

def format_response(user_question: str, query_results: list, query_explanation: str) -> str:
    """
    Converts raw MongoDB results into a friendly English response.
    Uses the same LLM provider as query generation.

    WHY separate step? Raw results look like:
      [{"name": "Ali", "roll_number": "ROLL1001"}, ...]
    We want:
      "3 students were absent today: Ali (ROLL1001), Sara (ROLL1002)..."
    """

    total_count    = len(query_results)
    results_sample = query_results[:10] if total_count > 10 else query_results

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

    # Route to appropriate provider
    try:
        if LLM_PROVIDER == "gemini":
            return _format_with_gemini(prompt)
        elif LLM_PROVIDER == "openai":
            return _format_with_openai(prompt)
        else:
            return _format_with_ollama(prompt)
    except Exception as e:
        print(f"⚠️ Format response failed: {e}, using fallback")
        return _fallback_format_response(query_results, total_count)


def _format_with_ollama(prompt: str) -> str:
    """Format response using Ollama"""
    try:
        ollama = _get_ollama_module()
        OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")
        
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            options={
                "temperature": 0.3,
                "num_predict": 400,
                "num_ctx": 2048,
                "num_thread": 8,
            }
        )
        return response["message"]["content"].strip()
    except Exception as e:
        raise Exception(f"Ollama format error: {str(e)}")


def _format_with_gemini(prompt: str) -> str:
    """Format response using Gemini"""
    try:
        genai = _get_gemini_module()
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        
        if not GEMINI_API_KEY:
            raise Exception("GEMINI_API_KEY not set")
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        raise Exception(f"Gemini format error: {str(e)}")


def _format_with_openai(prompt: str) -> str:
    """Format response using OpenAI"""
    try:
        OpenAI = _get_openai_module()
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        
        if not OPENAI_API_KEY:
            raise Exception("OPENAI_API_KEY not set")
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful school ERP assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"OpenAI format error: {str(e)}")


def _fallback_format_response(query_results: list, total_count: int) -> str:
    """Fallback formatting when LLM fails"""
    lines = [f"Found {total_count} records:"]
    for i, record in enumerate(query_results[:10], 1):
        name = record.get("name", record.get("title", f"Record {i}"))
        lines.append(f"  {i}. {name}")
    if total_count > 10:
        lines.append(f"  ... and {total_count - 10} more.")
    return "\n".join(lines)