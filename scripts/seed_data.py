import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from dotenv import load_dotenv
from faker import Faker
from datetime import datetime, timedelta
import random

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME", "erp_db")]

fake = Faker()

def clear_collections():
    db.students.drop()
    db.teachers.drop()
    db.classes.drop()
    db.attendance.drop()
    db.assignments.drop()

def seed_teachers():
    subjects = ["Mathematics", "Science", "English", "History", "Geography",
                "Physics", "Chemistry", "Biology", "Computer Science", "Art"]
    
    teachers = []
    for i, subject in enumerate(subjects):
        teachers.append({
            "name": fake.name(),
            "email": fake.email(),
            "subject": subject,
            "phone": fake.phone_number()[:15]
        })
    
    result = db.teachers.insert_many(teachers)
    return result.inserted_ids

def seed_classes(teacher_ids):
    class_definitions = [
        {"name": "Class 6", "section": "A"},
        {"name": "Class 6", "section": "B"},
        {"name": "Class 7", "section": "A"},
        {"name": "Class 7", "section": "B"},
        {"name": "Class 8", "section": "A"},
        {"name": "Class 8", "section": "B"},
        {"name": "Class 9", "section": "A"},
        {"name": "Class 9", "section": "B"},
        {"name": "Class 10", "section": "A"},
        {"name": "Class 10", "section": "B"},
    ]
    
    classes = []
    for i, cls in enumerate(class_definitions):
        classes.append({
            "name": cls["name"],
            "section": cls["section"],
            "teacher_id": teacher_ids[i % len(teacher_ids)]
        })
    
    result = db.classes.insert_many(classes)
    return result.inserted_ids

def seed_students(class_ids):
    students = []
    for i in range(200):
        students.append({
            "name": fake.name(),
            "roll_number": f"ROLL{1000 + i}",
            "class_id": random.choice(class_ids),
            "section": random.choice(["A", "B"]),
            "email": fake.email(),
            "phone": fake.phone_number()[:15]
        })
    
    result = db.students.insert_many(students)
    return result.inserted_ids

def seed_attendance(student_ids, class_ids):
    attendance_records = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for days_ago in range(30):
        date = today - timedelta(days=days_ago)
        
        if date.weekday() >= 5:
            continue
        
        for student_id in student_ids:
            status = "present" if random.random() < 0.85 else "absent"
            attendance_records.append({
                "student_id": student_id,
                "class_id": random.choice(class_ids),
                "date": date,
                "status": status
            })
    
    batch_size = 1000
    for i in range(0, len(attendance_records), batch_size):
        db.attendance.insert_many(attendance_records[i:i+batch_size])

def seed_assignments(class_ids, student_ids):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    assignment_titles = [
        "Math Homework Chapter 5", "Science Lab Report", "English Essay",
        "History Project", "Geography Map Work", "Physics Problem Set",
        "Chemistry Experiment", "Biology Diagrams", "Computer Program",
        "Art Portfolio", "Math Test Prep", "Reading Assignment",
        "Current Events Report", "Math Quiz", "Literature Review"
    ]
    
    assignments = []
    for i in range(50):
        due_offset = random.randint(-7, 14)
        created_offset = random.randint(due_offset - 14, due_offset - 1)
        
        submitting_students = random.sample(
            list(student_ids), 
            k=random.randint(0, min(20, len(student_ids)))
        )
        
        submissions = []
        for student_id in submitting_students:
            submissions.append({
                "student_id": student_id,
                "submitted_at": today + timedelta(days=random.randint(created_offset, due_offset))
            })
        
        assignments.append({
            "title": random.choice(assignment_titles) + f" #{i+1}",
            "class_id": random.choice(class_ids),
            "due_date": today + timedelta(days=due_offset),
            "created_date": today + timedelta(days=created_offset),
            "submissions": submissions
        })
    
    result = db.assignments.insert_many(assignments)

def create_indexes():
    db.students.create_index("class_id")
    db.students.create_index("section")
    db.attendance.create_index("student_id")
    db.attendance.create_index("date")
    db.attendance.create_index([("student_id", 1), ("date", 1)])
    db.assignments.create_index("due_date")
    db.assignments.create_index("class_id")

def main():
    clear_collections()
    
    teacher_ids = seed_teachers()
    class_ids = seed_classes(teacher_ids)
    student_ids = seed_students(class_ids)
    seed_attendance(student_ids, class_ids)
    seed_assignments(class_ids, student_ids)
    create_indexes()

if __name__ == "__main__":
    main()