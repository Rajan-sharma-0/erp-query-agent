import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

_client = None
_db = None

def get_db():
    global _client, _db
    if _client is None:
        _client = MongoClient(os.getenv("MONGODB_URI"))
        _db = _client[os.getenv("DATABASE_NAME", "erp_db")]
    return _db

def execute_query(collection_name: str, pipeline: list) -> list:
    db = get_db()
    
    if collection_name not in db.list_collection_names():
        return {"error": f"Collection '{collection_name}' does not exist"}
    
    collection = db[collection_name]
    results = list(collection.aggregate(pipeline))
    return serialize_results(results)

def serialize_results(results: list) -> list:
    from bson import ObjectId
    
    serialized = []
    for doc in results:
        serialized.append(serialize_doc(doc))
    return serialized

def serialize_doc(doc):
    from bson import ObjectId
    
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return doc

def get_schema_info() -> str:
    return """
DATABASE: erp_db
Collections and their fields:

1. students
   - _id: ObjectId
   - name: string (student's full name)
   - roll_number: string (e.g., "ROLL1001")
   - class_id: ObjectId (references classes._id)
   - section: string ("A" or "B")
   - email: string
   - phone: string

2. teachers
   - _id: ObjectId
   - name: string
   - email: string
   - subject: string (e.g., "Mathematics", "Science")
   - phone: string

3. classes
   - _id: ObjectId
   - name: string (e.g., "Class 6", "Class 7")
   - section: string ("A" or "B")
   - teacher_id: ObjectId (references teachers._id)

4. attendance
   - _id: ObjectId
   - student_id: ObjectId (references students._id)
   - class_id: ObjectId (references classes._id)
   - date: datetime (stored as midnight UTC, e.g., 2024-01-15 00:00:00)
   - status: string ("present" or "absent")

5. assignments
   - _id: ObjectId
   - title: string
   - class_id: ObjectId (references classes._id)
   - due_date: datetime
   - created_date: datetime
   - submissions: array of objects [{student_id: ObjectId, submitted_at: datetime}]

IMPORTANT NOTES FOR QUERY GENERATION:
- All date fields store datetime objects (midnight UTC)
- To query "today", use: $gte start-of-today AND $lt start-of-tomorrow
- To match ObjectIds across collections, use $lookup (like SQL JOIN)
- class_id in students is a reference, NOT the class name string
- "section A of class 6" means: classes where name="Class 6" AND section="A"
  then find students whose class_id matches that class's _id
"""