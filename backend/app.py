# -*- coding: utf-8 -*-
"""
TomeHub Flask API
=================
RESTful API for TomeHub personal library backend.
Connects React frontend with RAG search and document ingestion services.

Author: TomeHub Team
Date: 2026-01-07
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import traceback
import sys
import os

# Add backend dir to path for package imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import TomeHub services from packages
from services.search_service import generate_answer
from services.ingestion_service import ingest_book

import logging

# Configure logging to file
logging.basicConfig(
    filename='backend_error.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for React frontend
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5173", "http://localhost:3000", "http://localhost:3001", "http://localhost:4000", "http://localhost:4001", "https://84.235.173.208.nip.io"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@app.route('/', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify API is running.
    
    Returns:
        JSON response with API status
    """
    return jsonify({
        'status': 'online',
        'service': 'TomeHub API',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    }), 200


# ============================================================================
# SEARCH ENDPOINT
# ============================================================================

# Import Smart Search Service (Layer 2)
from services.smart_search_service import perform_smart_search

@app.route('/api/smart-search', methods=['POST'])
def smart_search():
    """
    Smart Search (Layer 2): Pure weighted search with unlimited results.
    Returns ALL matching notes ordered by field-weighted relevance.
    """
    try:
        data = request.json
        question = data.get('question', '').strip()
        firebase_uid = data.get('firebase_uid', '').strip()
        
        if not question:
            return jsonify({'error': 'Question is required'}), 400
        
        if not firebase_uid:
            return jsonify({'error': 'Firebase UID is required'}), 400
        
        print(f"\n[SMART SEARCH] Query: '{question}' | User: {firebase_uid}")
        
        # Perform pure search - NO AI generation
        from services.smart_search_service import perform_smart_search
        results = perform_smart_search(question, firebase_uid)
        
        return jsonify({
            'results': results,
            'total': len(results),
            'query': question
        })
        
    except Exception as e:
        print(f"[ERROR] Smart search failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search():
    """
    RAG-powered search endpoint.
    
    Request Body:
        {
            "question": str,      # User's question
            "firebase_uid": str,  # User identifier
            "book_id": str        # (Optional) Restrict context to specific book
        }
    """
    try:
        # ... (validation omitted for brevity) ...
        question = request.json.get('question')
        firebase_uid = request.json.get('firebase_uid')
        book_id = request.json.get('book_id') # NEW
        
        # ...
        
        # Generate answer using RAG
        answer, sources = generate_answer(question, firebase_uid, context_book_id=book_id)
        
        if answer is None:
            # Distinguish between error vs no content
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [API] No relevant content found (or AI error)")
            return jsonify({
                'answer': "I couldn't find any relevant information in your library to answer this question. Please ensure you have migrated your content.",
                'sources': [],
                'timestamp': datetime.now().isoformat()
            }), 200
        
        # Return response
        response = {
            'answer': answer,
            'sources': sources,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [API] Search successful")
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [API ERROR] Search failed: {e}")
        logging.error(f"Search failed: {e}", exc_info=True)
        traceback.print_exc()
        
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


# ============================================================================
# INGESTION ENDPOINT
# ============================================================================

import os
import uuid
from werkzeug.utils import secure_filename

# ... imports ...

@app.route('/api/ingest', methods=['POST'])
def ingest():
    """
    Document ingestion endpoint.
    Handles file upload and processing.
    
    Request (multipart/form-data):
    Request (multipart/form-data):
        file: The PDF/EPUB file
        title: Book title
        author: Book author
        firebase_uid: User identifier
        book_id: Unique book identifier (optional, generated if missing)
    """
    temp_path = None
    try:
        # Check if file part exists
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in request'}), 400
        
        file = request.files['file']
        
        # Check if file selected
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if file:
            # Create uploads directory if not exists
            upload_dir = os.path.join(os.getcwd(), 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save file securely with unique name
            original_filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{original_filename}"
            temp_path = os.path.join(upload_dir, unique_filename)
            file.save(temp_path)
            
            # Extract form data
            title = request.form.get('title')
            author = request.form.get('author')
            firebase_uid = request.form.get('firebase_uid')
            book_id = request.form.get('book_id')
            
            # Validate required fields
            if not title:
                return jsonify({'error': 'Missing required field: title'}), 400
            if not author:
                return jsonify({'error': 'Missing required field: author'}), 400
            if not firebase_uid:
                return jsonify({'error': 'Missing required field: firebase_uid'}), 400
            
            # Log request
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [API] Ingestion request")
            print(f"  User: {firebase_uid}")
            print(f"  Title: {title}")
            print(f"  File: {original_filename}")
            
            # Trigger ingestion using the temp file path
            success = ingest_book(temp_path, title, author, firebase_uid, book_id)
            
            if success:
                response = {
                    'success': True,
                    'message': f"Successfully ingested '{title}'",
                    'timestamp': datetime.now().isoformat()
                }
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [API] Ingestion successful")
                return jsonify(response), 200
            else:
                return jsonify({
                    'error': 'Ingestion failed during processing',
                    'details': 'Check server logs'
                }), 500
            
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [API ERROR] Ingestion failed: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500
        
    finally:
        # Cleanup: Remove temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [API] Cleaned up temp file")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [API ERROR] Cleanup failed: {e}")


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'Endpoint not found',
        'details': 'The requested endpoint does not exist'
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors."""
    return jsonify({
        'error': 'Method not allowed',
        'details': 'The HTTP method is not supported for this endpoint'
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        'error': 'Internal server error',
        'details': 'An unexpected error occurred'
    }), 500


# ============================================================================
# MAIN EXECUTION
# ============================================================================

from services.ingestion_service import ingest_book, ingest_text_item, process_bulk_items_logic

@app.route('/api/migrate_bulk', methods=['POST'])
def migrate_bulk():
    """
    Endpoint for bulk migration of items.
    Expects JSON: { "items": [...], "firebase_uid": "..." }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        items = data.get('items', [])
        firebase_uid = data.get('firebase_uid')
        
        if not items or not isinstance(items, list):
             return jsonify({'error': 'Invalid items list'}), 400
             
        if not firebase_uid:
            return jsonify({'error': 'Missing firebase_uid'}), 400
            
        # Process the batch
        result = process_bulk_items_logic(items, firebase_uid)
        
        return jsonify({
            'success': True,
            'processed': len(items),
            'results': result
        }), 200
            
    except Exception as e:
        print(f"Error in /api/migrate_bulk: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/add-item', methods=['POST'])
def add_item():
    """
    Endpoint to add existing text items (notes, book metadata) to AI.
    Request JSON:
        {
            "text": str,
            "title": str, 
            "author": str,
            "type": str,
            "firebase_uid": str
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        success = ingest_text_item(
            text=data.get('text', ''),
            title=data.get('title', 'Untitled'),
            author=data.get('author', 'Unknown'),
            source_type=data.get('type', 'NOTE'),
            firebase_uid=data.get('firebase_uid')
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Item added to AI library'}), 200
        else:
            return jsonify({'error': 'Failed to add item'}), 500
            
    except Exception as e:
        print(f"Error in /api/add-item: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print(f"[INFO] Ingest endpoint: POST http://localhost:5000/api/ingest")
    print(f"\n[INFO] CORS enabled for React frontend")
    print(f"[INFO] Allowed origins: http://localhost:5173, http://localhost:3000")
    print("\n" + "=" * 70)
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
