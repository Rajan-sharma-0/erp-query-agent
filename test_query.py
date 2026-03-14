import requests
import json

BASE_URL = "http://localhost:8000"

# All 15 questions from the assignment
questions = [
    # Level 1
    "List all students in Class 6",
    "Show attendance of students for today",
    "List all teachers in the system",
    "Show all assignments created today",
    # Level 2
    "Show students who were absent yesterday",
    "List assignments due this week",
    "Show students belonging to section A of class 6",
    "Show all assignments scheduled this month",
    # Level 3
    "Count how many students were absent today",
    "Show the number of assignments submitted per class",
    "Find the class with the highest number of absent students today",
    # Level 4
    "Show students who have not submitted any assignment",
    "List teachers and the classes they teach",
    "Show attendance percentage of each student",
    # Level 5
    "Show the top 5 students with the highest attendance percentage",
]

print("🧪 Testing all 15 queries...\n")
print("=" * 60)

for i, question in enumerate(questions, 1):
    print(f"\n[Q{i}] {question}")
    print("-" * 40)
    
    response = requests.post(
        f"{BASE_URL}/api/query",
        json={"question": question, "show_query": False}
    )
    
    data = response.json()
    
    if data["status"] == "success":
        print(f"✅ Results: {data.get('results_count', 0)}")
        print(f"💬 {data['response'][:200]}...")
    else:
        print(f"❌ Error: {data.get('error', 'Unknown error')}")

print("\n" + "=" * 60)
print("🎉 Testing complete!")