# Flask API Usage Guide

## Overview

The `app.py` Flask API provides RESTful endpoints to connect your React frontend with the TomeHub backend services.

## Installation

Install Flask dependencies:
```bash
pip install flask flask-cors
```

Or install all requirements:
```bash
pip install -r backend/requirements.txt
```

## Starting the Server

```bash
python backend/app.py
```

The API will be available at: `http://localhost:5000`

## Endpoints

### 1. Health Check

**GET /** - Verify API is running

**Response:**
```json
{
  "status": "online",
  "service": "TomeHub API",
  "version": "1.0.0",
  "timestamp": "2026-01-07T19:35:00"
}
```

**Example:**
```bash
curl http://localhost:5000/
```

### 2. Search (RAG)

**POST /api/search** - Ask questions about your library

**Request Body:**
```json
{
  "question": "What is Dasein?",
  "firebase_uid": "user_123"
}
```

**Response:**
```json
{
  "answer": "According to Heidegger, Dasein is...",
  "sources": [
    {
      "title": "Being and Time - Heidegger",
      "page_number": 42,
      "similarity_score": 0.05
    }
  ],
  "timestamp": "2026-01-07T19:35:00"
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"question": "What is phenomenology?", "firebase_uid": "test_user_001"}'
```

**Example (JavaScript):**
```javascript
const response = await fetch('http://localhost:5000/api/search', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    question: 'What is Dasein?',
    firebase_uid: 'user_123'
  })
});

const data = await response.json();
console.log(data.answer);
console.log(data.sources);
```

### 3. Ingest Document

**POST /api/ingest** - Add a new book to the library

**Request Body:**
```json
{
  "pdf_path": "C:\\Books\\being_and_time.pdf",
  "title": "Being and Time",
  "author": "Martin Heidegger",
  "firebase_uid": "user_123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully ingested 'Being and Time' by Martin Heidegger",
  "timestamp": "2026-01-07T19:35:00"
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "book.pdf",
    "title": "Meditations",
    "author": "Marcus Aurelius",
    "firebase_uid": "test_user_001"
  }'
```

**Example (JavaScript):**
```javascript
const response = await fetch('http://localhost:5000/api/ingest', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    pdf_path: 'C:\\Books\\meditations.pdf',
    title: 'Meditations',
    author: 'Marcus Aurelius',
    firebase_uid: 'user_123'
  })
});

const data = await response.json();
console.log(data.message);
```

## Error Responses

### 400 Bad Request
Missing or invalid parameters:
```json
{
  "error": "Missing required field: question"
}
```

### 404 Not Found
Endpoint doesn't exist:
```json
{
  "error": "Endpoint not found",
  "details": "The requested endpoint does not exist"
}
```

### 500 Internal Server Error
Server-side error:
```json
{
  "error": "Internal server error",
  "details": "Error message details"
}
```

## CORS Configuration

The API is configured to accept requests from:
- `http://localhost:5173` (Vite default)
- `http://localhost:3000` (Create React App default)

To add more origins, edit `app.py`:
```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5173", "http://your-domain.com"],
        ...
    }
})
```

## React Integration Example

```jsx
import { useState } from 'react';

function SearchComponent() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState([]);

  const handleSearch = async () => {
    const response = await fetch('http://localhost:5000/api/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question: question,
        firebase_uid: 'user_123'
      })
    });

    const data = await response.json();
    setAnswer(data.answer);
    setSources(data.sources);
  };

  return (
    <div>
      <input 
        value={question} 
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask a question..."
      />
      <button onClick={handleSearch}>Search</button>
      
      {answer && (
        <div>
          <h3>Answer:</h3>
          <p>{answer}</p>
          
          <h4>Sources:</h4>
          <ul>
            {sources.map((source, i) => (
              <li key={i}>
                {source.title} (p.{source.page_number})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

## Testing the API

### Using curl:
```bash
# Health check
curl http://localhost:5000/

# Search
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "firebase_uid": "test_user_001"}'
```

### Using Postman:
1. Create new POST request
2. URL: `http://localhost:5000/api/search`
3. Headers: `Content-Type: application/json`
4. Body (raw JSON):
```json
{
  "question": "What is phenomenology?",
  "firebase_uid": "test_user_001"
}
```

## Production Deployment

For production, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Or use Docker:
```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

## Next Steps

1. Test API endpoints with curl or Postman
2. Integrate with React frontend
3. Add authentication middleware
4. Implement rate limiting
5. Add request logging
6. Deploy to production
