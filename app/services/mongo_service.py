"""
mongo_service.py
----------------
Handles ALL communication with MongoDB.
Other files just call functions here — they don't touch MongoDB directly.
This is called the "Service Layer" pattern.
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Create ONE connection and reuse it (efficient)
# MongoClient is thread-safe, so one instance is fine
_client = None
_db = None

def get_db():
    """Get database connection. Creates it if it doesn't exist yet."""
    global _client, _db
    if _client is None:
        _client = MongoClient(os.getenv("MONGODB_URI"))
        _db = _client[os.getenv("DATABASE_NAME", "erp_db")]
    return _db

def execute_query(collection_name: str, pipeline: list) -> list:
    """
    Execute a MongoDB aggregation pipeline.
    
    Why aggregation pipeline?
    - Simple find() can only filter documents
    - Aggregation can JOIN collections, GROUP, COUNT, SORT, etc.
    - It handles ALL 15 of our query types
    
    Args:
        collection_name: which collection to query (e.g., "students")
        pipeline: list of aggregation stages
    
    Returns:
        List of result documents
    """
    db = get_db()
    
    if collection_name not in db.list_collection_names():
        return {"error": f"Collection '{collection_name}' does not exist"}
    
    collection = db[collection_name]
    
    # Execute and convert cursor to list
    # limit(200) prevents accidentally returning 100k records
    results = list(collection.aggregate(pipeline))
    
    # Convert ObjectId and datetime to strings (JSON can't serialize them)
    return serialize_results(results)

def serialize_results(results: list) -> list:
    """
    MongoDB returns ObjectId and datetime objects.
    JSON can't handle these types, so we convert them to strings.
    """
    from bson import ObjectId
    
    serialized = []
    for doc in results:
        serialized.append(serialize_doc(doc))
    return serialized

def serialize_doc(doc):
    """Recursively convert a document's non-JSON-serializable types."""
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
    """
    Returns a description of our database schema.
    We pass this to the AI so it knows what collections/fields exist.
    
    WHY? Without this, the AI would guess field names and get them wrong.
    """
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