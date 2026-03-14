"""
intent_detector.py
------------------
Detects SIMPLE query intents and returns the MongoDB pipeline directly,
WITHOUT calling the AI at all.

WHY? gemma3:1b is too small to reliably generate MongoDB JSON.
     For all 15 assignment queries, we use pre-built pipelines.
     AI (Ollama) is only called for truly unknown/custom queries.
"""

import re
from datetime import datetime, timedelta


def get_date_range(period: str):
    """Returns (start, end) datetime tuple for a given period."""
    now   = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    ranges = {
        "today":      (today,                          today + timedelta(days=1)),
        "yesterday":  (today - timedelta(days=1),      today),
        "this_week":  (today - timedelta(days=today.weekday()),
                       today - timedelta(days=today.weekday()) + timedelta(days=7)),
        "this_month": (today.replace(day=1),
                       today.replace(day=1, month=today.month % 12 + 1)
                       if today.month < 12
                       else today.replace(day=1, month=1, year=today.year + 1)),
    }
    return ranges.get(period, (today, today + timedelta(days=1)))


def detect_intent(question: str):
    """
    Matches the question against known patterns.
    Returns a pre-built pipeline dict, or None if no pattern matches.

    Return format:
    {
        "collection": "teachers",
        "pipeline":   [...],
        "explanation": "one line description"
    }
    """
    q = question.lower().strip()

    # ────────────────────────────────────────────────────
    # LEVEL 1 — Basic Queries
    # ────────────────────────────────────────────────────

    # "list all teachers" / "show teachers" / "all teachers in system"
    if re.search(r'\bteachers?\b', q) and not re.search(r'class|teach\b', q.replace("teachers","").replace("teacher","")):
        return {
            "collection": "teachers",
            "pipeline": [
                {"$project": {"_id": 0, "name": 1, "subject": 1, "email": 1, "phone": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns all teachers — no filter applied"
        }

    # "list all students" / "show all students" / "students list"
    # Exclude queries with filters like class, section, absent, percentage
    if (re.search(r'\bstudents?\b', q)
            and not re.search(r'class\s*\d|section|absent|attendance|submit|percent|top\s*\d|not\s+submit', q)):
        return {
            "collection": "students",
            "pipeline": [
                {"$project": {"_id": 0, "name": 1, "roll_number": 1, "section": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns all students — no filter applied"
        }

    # "show all assignments created today" / "assignments added today"
    if re.search(r'\bassignment', q) and re.search(r'\btoday\b', q) and re.search(r'creat|new|add', q):
        start, end = get_date_range("today")
        return {
            "collection": "assignments",
            "pipeline": [
                {"$match": {"created_date": {"$gte": start, "$lt": end}}},
                {"$project": {"_id": 0, "title": 1, "due_date": 1, "created_date": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns assignments created today"
        }

    # "show attendance of a student for today" / "attendance today"
    if re.search(r'\battendance\b', q) and re.search(r'\btoday\b', q) and not re.search(r'percent|%|absent', q):
        start, end = get_date_range("today")
        return {
            "collection": "attendance",
            "pipeline": [
                {"$match": {"date": {"$gte": start, "$lt": end}}},
                {"$lookup": {"from": "students", "localField": "student_id", "foreignField": "_id", "as": "student"}},
                {"$unwind": "$student"},
                {"$project": {"_id": 0, "name": "$student.name", "roll_number": "$student.roll_number", "status": 1, "date": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns all attendance records for today"
        }

    # ────────────────────────────────────────────────────
    # LEVEL 2 — Filtering Queries
    # ────────────────────────────────────────────────────

    # "absent yesterday"
    if re.search(r'\babsent\b', q) and re.search(r'\byesterday\b', q):
        start, end = get_date_range("yesterday")
        return {
            "collection": "attendance",
            "pipeline": [
                {"$match": {"status": "absent", "date": {"$gte": start, "$lt": end}}},
                {"$lookup": {"from": "students", "localField": "student_id", "foreignField": "_id", "as": "student"}},
                {"$unwind": "$student"},
                {"$project": {"_id": 0, "name": "$student.name", "roll_number": "$student.roll_number", "date": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns students absent yesterday"
        }

    # "absent today"
    if re.search(r'\babsent\b', q) and re.search(r'\btoday\b', q):
        start, end = get_date_range("today")
        return {
            "collection": "attendance",
            "pipeline": [
                {"$match": {"status": "absent", "date": {"$gte": start, "$lt": end}}},
                {"$lookup": {"from": "students", "localField": "student_id", "foreignField": "_id", "as": "student"}},
                {"$unwind": "$student"},
                {"$project": {"_id": 0, "name": "$student.name", "roll_number": "$student.roll_number"}},
                {"$limit": 200}
            ],
            "explanation": "Returns students absent today"
        }

    # "assignments due this week"
    if re.search(r'\bassignment', q) and re.search(r'due|this\s+week', q) and not re.search(r'month', q):
        start, end = get_date_range("this_week")
        return {
            "collection": "assignments",
            "pipeline": [
                {"$match": {"due_date": {"$gte": start, "$lt": end}}},
                {"$project": {"_id": 0, "title": 1, "due_date": 1}},
                {"$sort": {"due_date": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns assignments due this week"
        }

    # "section A of class 6" / "class 6 section A"
    class_section = re.search(r'class\s*(\d+).*section\s*([a-b])|section\s*([a-b]).*class\s*(\d+)', q)
    if class_section:
        g = class_section.groups()
        # groups: (class_num, section) or (None, None, section, class_num)
        class_num = g[0] or g[3]
        section   = (g[1] or g[2] or "").upper()
        return {
            "collection": "classes",
            "pipeline": [
                {"$match": {"name": f"Class {class_num}", "section": section}},
                {"$lookup": {"from": "students", "localField": "_id", "foreignField": "class_id", "as": "students"}},
                {"$unwind": "$students"},
                {"$replaceRoot": {"newRoot": "$students"}},
                {"$project": {"_id": 0, "name": 1, "roll_number": 1, "section": 1}},
                {"$limit": 200}
            ],
            "explanation": f"Returns students in Class {class_num} Section {section}"
        }

    # "students in class 6" (no section specified)
    class_only = re.search(r'class\s*(\d+)', q)
    if class_only and re.search(r'\bstudent', q):
        class_num = class_only.group(1)
        return {
            "collection": "classes",
            "pipeline": [
                {"$match": {"name": f"Class {class_num}"}},
                {"$lookup": {"from": "students", "localField": "_id", "foreignField": "class_id", "as": "students"}},
                {"$unwind": "$students"},
                {"$replaceRoot": {"newRoot": "$students"}},
                {"$project": {"_id": 0, "name": 1, "roll_number": 1, "section": 1}},
                {"$limit": 200}
            ],
            "explanation": f"Returns all students in Class {class_num}"
        }

    # "assignments this month" / "exams scheduled this month"
    if re.search(r'\bassignment|exam\b', q) and re.search(r'this\s+month|month', q):
        start, end = get_date_range("this_month")
        return {
            "collection": "assignments",
            "pipeline": [
                {"$match": {"due_date": {"$gte": start, "$lt": end}}},
                {"$project": {"_id": 0, "title": 1, "due_date": 1}},
                {"$sort": {"due_date": 1}},
                {"$limit": 200}
            ],
            "explanation": "Returns assignments/exams due this month"
        }

    # ────────────────────────────────────────────────────
    # LEVEL 3 — Aggregation Queries
    # ────────────────────────────────────────────────────

    # "count absent today" / "how many absent today"
    if re.search(r'count|how\s+many', q) and re.search(r'\babsent\b', q) and re.search(r'\btoday\b', q):
        start, end = get_date_range("today")
        return {
            "collection": "attendance",
            "pipeline": [
                {"$match": {"status": "absent", "date": {"$gte": start, "$lt": end}}},
                {"$count": "absent_count"}
            ],
            "explanation": "Counts absent students for today"
        }

    # "assignments submitted per class" / "submissions per class"
    if re.search(r'\bassignment', q) and re.search(r'submit|per\s+class|each\s+class', q):
        return {
            "collection": "assignments",
            "pipeline": [
                {"$unwind": "$submissions"},
                {"$group": {"_id": "$class_id", "total_submissions": {"$sum": 1}}},
                {"$lookup": {"from": "classes", "localField": "_id", "foreignField": "_id", "as": "class_info"}},
                {"$unwind": "$class_info"},
                {"$project": {
                    "_id": 0,
                    "class": {"$concat": ["$class_info.name", " - ", "$class_info.section"]},
                    "total_submissions": 1
                }},
                {"$sort": {"total_submissions": -1}},
                {"$limit": 200}
            ],
            "explanation": "Counts assignment submissions grouped by class"
        }

    # "class with highest absent" / "most absent class"
    if re.search(r'\bclass\b', q) and re.search(r'highest|most', q) and re.search(r'\babsent\b', q):
        start, end = get_date_range("today")
        return {
            "collection": "attendance",
            "pipeline": [
                {"$match": {"status": "absent", "date": {"$gte": start, "$lt": end}}},
                {"$group": {"_id": "$class_id", "absent_count": {"$sum": 1}}},
                {"$lookup": {"from": "classes", "localField": "_id", "foreignField": "_id", "as": "class_info"}},
                {"$unwind": "$class_info"},
                {"$project": {
                    "_id": 0,
                    "class": {"$concat": ["$class_info.name", " - Sec ", "$class_info.section"]},
                    "absent_count": 1
                }},
                {"$sort": {"absent_count": -1}},
                {"$limit": 1}
            ],
            "explanation": "Finds the class with most absences today"
        }

    # ────────────────────────────────────────────────────
    # LEVEL 4 — Multi-Collection Queries
    # ────────────────────────────────────────────────────

    # "students who have not submitted" / "students with no submission"
    if re.search(r'\bstudent', q) and re.search(r'not\s+submit|haven.t\s+submit|no\s+submit|without\s+submit', q):
        return {
            "collection": "students",
            "pipeline": [
                {"$lookup": {
                    "from": "assignments",
                    "let":  {"sid": "$_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$in": ["$$sid", "$submissions.student_id"]}}}
                    ],
                    "as": "submitted"
                }},
                {"$match": {"submitted": {"$size": 0}}},
                {"$project": {"_id": 0, "name": 1, "roll_number": 1, "section": 1}},
                {"$limit": 200}
            ],
            "explanation": "Finds students with zero assignment submissions"
        }

    # "teachers and classes they teach" / "teacher class list"
    if re.search(r'\bteacher', q) and re.search(r'class|teach', q):
        return {
            "collection": "teachers",
            "pipeline": [
                {"$lookup": {"from": "classes", "localField": "_id", "foreignField": "teacher_id", "as": "classes"}},
                {"$project": {
                    "_id": 0, "name": 1, "subject": 1,
                    "classes": {"$map": {
                        "input": "$classes", "as": "c",
                        "in": {"$concat": ["$$c.name", " - Sec ", "$$c.section"]}
                    }}
                }},
                {"$limit": 200}
            ],
            "explanation": "Lists each teacher with classes they are assigned to"
        }

    # "attendance percentage" / "attendance % of each student"  (NOT top N)
    if re.search(r'\battendance\b', q) and re.search(r'percent|%', q) and not re.search(r'top\s*\d', q):
        return {
            "collection": "attendance",
            "pipeline": [
                {"$group": {
                    "_id": "$student_id",
                    "total":   {"$sum": 1},
                    "present": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}}
                }},
                {"$lookup": {"from": "students", "localField": "_id", "foreignField": "_id", "as": "student"}},
                {"$unwind": "$student"},
                {"$project": {
                    "_id": 0,
                    "name":        "$student.name",
                    "roll_number": "$student.roll_number",
                    "attendance_percentage": {
                        "$round": [{"$multiply": [{"$divide": ["$present", "$total"]}, 100]}, 1]
                    }
                }},
                {"$sort": {"attendance_percentage": -1}},
                {"$limit": 200}
            ],
            "explanation": "Calculates attendance percentage for every student"
        }

    # ────────────────────────────────────────────────────
    # LEVEL 5 — Analytical Queries
    # ────────────────────────────────────────────────────

    # "top 5 students by attendance" / "top 10 attendance"
    top_match = re.search(r'top\s*(\d+)', q)
    if top_match and re.search(r'\battendance\b', q):
        limit = int(top_match.group(1))
        return {
            "collection": "attendance",
            "pipeline": [
                {"$group": {
                    "_id": "$student_id",
                    "total":   {"$sum": 1},
                    "present": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}}
                }},
                {"$lookup": {"from": "students", "localField": "_id", "foreignField": "_id", "as": "student"}},
                {"$unwind": "$student"},
                {"$project": {
                    "_id": 0,
                    "name":        "$student.name",
                    "roll_number": "$student.roll_number",
                    "attendance_percentage": {
                        "$round": [{"$multiply": [{"$divide": ["$present", "$total"]}, 100]}, 1]
                    }
                }},
                {"$sort": {"attendance_percentage": -1}},
                {"$limit": limit}
            ],
            "explanation": f"Returns top {limit} students by attendance percentage"
        }

    # No pattern matched — let Ollama handle it
    return None