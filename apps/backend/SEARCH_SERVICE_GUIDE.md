# Search Service Usage Guide

## Overview

The `search_service.py` module implements RAG (Retrieval-Augmented Generation) for semantic search and AI-powered question answering from your personal library.

## Features

✅ Semantic search using vector similarity  
✅ AI-powered question answering with Gemini  
✅ Source citations with page numbers  
✅ Context-aware responses  
✅ Efficient database queries  

## Functions

### `search_similar_content(query_text, firebase_uid, top_k=5)`

Search for semantically similar content.

**Parameters:**
- `query_text` (str): Search query
- `firebase_uid` (str): User identifier
- `top_k` (int): Number of results (default: 5)

**Returns:**
List of dictionaries with:
- `content_chunk`: Text content
- `page_number`: Page number
- `title`: Book/document title
- `similarity_score`: Similarity score (0 = identical)

**Example:**
```python
from search_service import search_similar_content

results = search_similar_content(
    "What is Dasein?",
    "user_123",
    top_k=5
)

for result in results:
    print(f"{result['title']} (p.{result['page_number']})")
    print(f"Score: {result['similarity_score']:.4f}")
    print(f"Content: {result['content_chunk'][:100]}...\n")
```

### `generate_answer(question, firebase_uid)`

Generate AI-powered answer using RAG.

**Parameters:**
- `question` (str): User's question
- `firebase_uid` (str): User identifier

**Returns:**
Tuple of (answer, sources):
- `answer` (str): AI-generated answer
- `sources` (List[Dict]): Source citations

**Example:**
```python
from search_service import generate_answer

answer, sources = generate_answer(
    "What does Heidegger say about being-in-the-world?",
    "user_123"
)

print("Answer:", answer)
print("\nSources:")
for source in sources:
    print(f"- {source['title']}, p.{source['page_number']}")
```

## Interactive Testing

Run the test interface:

```bash
python backend/search_service.py
```

Example session:
```
======================================================================
TomeHub RAG Search Service - Interactive Test
======================================================================

Enter Firebase UID (press Enter for test_user_001): 

[INFO] Using user ID: test_user_001

======================================================================

Enter your question (or 'quit' to exit): What is phenomenology?

======================================================================
RAG Question Answering
======================================================================

[QUESTION] What is phenomenology?

======================================================================
Step 1: Retrieving Relevant Context
======================================================================
[19:30:15] Searching for: 'What is phenomenology?'
[19:30:15] Generating query embedding...
[19:30:16] Connecting to database...
[19:30:16] Searching for similar content...
[19:30:17] Found 5 similar chunks

======================================================================
Step 2: Building Context
======================================================================
[19:30:17] Added source 1: Being and Time - Heidegger (p.42)
[19:30:17] Added source 2: Being and Time - Heidegger (p.45)
...

======================================================================
Step 3: Generating AI Answer
======================================================================
[19:30:18] Sending to Gemini...
[19:30:20] Answer generated successfully

======================================================================
AI ANSWER
======================================================================

According to [Source 1], phenomenology is the study of structures of 
consciousness as experienced from the first-person point of view...

======================================================================
SOURCES USED
======================================================================
1. Being and Time - Heidegger (p.42, p.45, p.48)
======================================================================
```

## Integration Example

Build a Flask API endpoint:

```python
from flask import Flask, request, jsonify
from search_service import generate_answer

app = Flask(__name__)

@app.route('/api/ask', methods=['POST'])
def ask_question():
    data = request.json
    question = data.get('question')
    user_id = data.get('firebase_uid')
    
    answer, sources = generate_answer(question, user_id)
    
    if answer:
        return jsonify({
            'answer': answer,
            'sources': sources
        })
    else:
        return jsonify({'error': 'Failed to generate answer'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

## How RAG Works

1. **Retrieval**: Convert question to vector, search database for similar chunks
2. **Augmentation**: Build context from retrieved chunks
3. **Generation**: Send context + question to Gemini for answer

## Performance Notes

- **Search time**: ~1-2 seconds (embedding + database query)
- **Generation time**: ~2-3 seconds (Gemini API)
- **Total time**: ~3-5 seconds per question
- **Accuracy**: Depends on quality of ingested content

## Prompt Engineering

The system uses a structured prompt:
```
Based on the following pieces of context from the user's personal library:
[CONTEXT]

Please answer the following question: [QUESTION]

Instructions:
- Provide a clear, comprehensive answer based on the context above
- Cite specific sources when making claims
- If the answer is not in the context, state that you don't know
- Be scholarly and precise in your response
```

## Next Steps

1. Test with your ingested books
2. Build Flask API endpoints
3. Integrate with React frontend
4. Add conversation history
5. Implement follow-up questions
