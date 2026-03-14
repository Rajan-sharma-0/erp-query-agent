# ERP Query Agent 🤖

A GenAI-powered system that converts natural language questions into MongoDB queries for a school ERP system.

## Architecture
User Question → Gemini AI → MongoDB Query → MongoDB Atlas → Gemini AI → Friendly Response

## Tech Stack
- **Backend**: Python + FastAPI
- **Database**: MongoDB Atlas (free tier)
- **AI**: Google Gemini 1.5 Flash (free tier)
- **Libraries**: PyMongo, Pydantic, python-dotenv

## Quick Start

### Prerequisites
- Python 3.10+
- MongoDB Atlas account (free)
- Google Gemini API key (free)

### Installation
```bash
git clone https://github.com/YOUR_USERNAME/erp-query-agent
cd erp-query-agent
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Configuration
Create `.env` file:
```
GEMINI_API_KEY=your_key_here
MONGODB_URI=your_mongodb_uri_here
DATABASE_NAME=erp_db
```

### Run
```bash
python scripts/seed_data.py  # Seed database (run once)
python main.py               # Start server
```

Visit http://localhost:8000/docs for interactive API.

## Example Queries

| Question | Level |
|----------|-------|
| List all students in Class 6 | Basic |
| Show students absent yesterday | Filtering |
| Count absent students today | Aggregation |
| Show attendance % per student | Multi-Collection |
| Top 5 students by attendance | Analytical |