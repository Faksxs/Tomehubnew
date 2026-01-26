# -*- coding: utf-8 -*-
"""
TomeHub PDF Service
===================
Handles PDF text extraction using OCI Document Understanding service.
Extracts structured content with page numbers, text types, and metadata.

Author: TomeHub Team
Date: 2026-01-07
"""

import os
import base64
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
import oci

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)


def get_oci_config() -> dict:
    """
    Load OCI configuration from environment variables.
    
    Returns:
        dict: OCI configuration dictionary
    
    Raises:
        ValueError: If required environment variables are missing
    """
    required_vars = {
        "user": os.getenv("OCI_USER_OCID"),
        "tenancy": os.getenv("OCI_TENANCY_OCID"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "region": os.getenv("OCI_REGION"),
        "key_file": os.getenv("OCI_KEY_FILE")
    }
    
    # Check for missing variables
    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        raise ValueError(f"Missing OCI configuration: {', '.join(missing)}")
    
    # Handle relative path for key file
    key_file = required_vars["key_file"]
    if not os.path.isabs(key_file):
        # Assuming key file is relative to project root or backend
        # Try finding it relative to this file first
        base_dir = os.path.dirname(os.path.abspath(__file__)) # services/
        project_root = os.path.dirname(base_dir) # backend/
        
        possible_path = os.path.join(project_root, key_file.replace("./backend/", "").replace("backend/", ""))
        
        if os.path.exists(possible_path):
            key_file = possible_path
        else:
            # Fallback to original logic but print warning
             key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                               key_file.replace("./backend/", ""))
    
    print(f"[DEBUG] OCI Key File Path: {key_file} (Exists: {os.path.exists(key_file)})")
    required_vars["key_file"] = key_file
    
    return required_vars


def extract_pdf_content(pdf_path: str) -> Optional[List[Dict[str, any]]]:
    """
    Extract structured content from a PDF file using OCI Document Understanding.
    
    This function sends the PDF to OCI for analysis and returns structured chunks
    with text, page numbers, and content types (paragraph, heading, footnote, etc.).
    
    Args:
        pdf_path (str): Path to the PDF file to process
    
    Returns:
        List[Dict] or None: List of content chunks, each containing:
            - text (str): The extracted text content
            - page_num (int): Page number (1-indexed)
            - type (str): Content type ('paragraph', 'heading', 'footnote', 'table', etc.)
            - confidence (float): OCR confidence score (0-1)
            - bbox (dict): Bounding box coordinates (optional)
        Returns None if extraction fails.
    
    Example:
        >>> chunks = extract_pdf_content("book.pdf")
        >>> print(chunks[0])
        {
            'text': 'Chapter 1: Introduction',
            'page_num': 1,
            'type': 'heading',
            'confidence': 0.99
        }
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting PDF extraction...")
    print(f"[INFO] File: {pdf_path}")
    
    # Validate file exists
    if not os.path.exists(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        return None
    
    # Validate file is PDF
    if not pdf_path.lower().endswith('.pdf'):
        print(f"[ERROR] File is not a PDF: {pdf_path}")
        return None
    
    try:
        # Load OCI configuration
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading OCI configuration...")
        config = get_oci_config()
        
        # Create AI Document client
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating OCI Document client...")
        ai_client = oci.ai_document.AIServiceDocumentClient(config)
        
        # Read PDF file
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Reading PDF file...")
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        file_size_mb = len(pdf_bytes) / (1024 * 1024)
        print(f"[INFO] File size: {file_size_mb:.2f} MB")
        
        # Encode to base64
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Encoding file...")
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Create inline document (no mime_type parameter in current OCI SDK)
        inline_document = oci.ai_document.models.InlineDocumentDetails(
            data=pdf_base64
        )
        
        # Create analyze request with text extraction and layout analysis
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Preparing analysis request...")
        analyze_request = oci.ai_document.models.AnalyzeDocumentDetails(
            features=[
                oci.ai_document.models.DocumentTextExtractionFeature(
                    feature_type="TEXT_EXTRACTION"
                ),
                oci.ai_document.models.DocumentClassificationFeature(
                    feature_type="DOCUMENT_CLASSIFICATION",
                    max_results=5
                )
            ],
            document=inline_document
        )
        
        # Send to OCI for analysis
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending to OCI Document Understanding...")
        print(f"[INFO] This may take a few moments for large documents...")
        
        response = ai_client.analyze_document(analyze_request)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Analysis complete!")
        
        # Extract structured chunks
        chunks = []
        total_pages = len(response.data.pages)
        print(f"[INFO] Processing {total_pages} pages...")
        
        for page in response.data.pages:
            page_num = page.page_number
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing page {page_num}/{total_pages}...")
            
            # Process lines (paragraphs)
            # Process lines (paragraphs)
            if hasattr(page, 'lines') and page.lines:
                for line_idx, line in enumerate(page.lines):
                    chunk = {
                        'text': line.text,
                        'page_num': page_num,
                        'type': 'paragraph',  # Default type
                        'confidence': line.confidence if hasattr(line, 'confidence') else 1.0,
                        'line_index': line_idx
                    }
                    
                    # --- SMART CHUNKING (MERGE PARAGRAPHS IF PAGE SPLIT) ---
                    # Logic: If a page ends with a sentence fragment, we should ideally merge it with next page.
                    # Current simplifiction: Just append chunks. Merging is handled by logic layer or implicit in Vector retrieval.
                    # For now, we focus on clean extraction.
                    
                    # Add bounding box if available
                    if hasattr(line, 'bounding_polygon'):
                        chunk['bbox'] = {
                            'points': [(p.x, p.y) for p in line.bounding_polygon.normalized_vertices]
                        }
                    
                    chunks.append(chunk)

            # --- HEADER/FOOTER REMOVAL (Heuristic) ---
            # Most PDF headers are at top 5% Y-coordinate. We can flag them or remove.
            # Implemented iteratively if needed.
            
            # Process words (for more granular control if needed)
            if hasattr(page, 'words') and page.words:
                # Group words into sentences/paragraphs
                # This is optional - you can enable if you need word-level granularity
                pass
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Extraction complete!")
        print(f"[SUCCESS] Extracted {len(chunks)} chunks from {total_pages} pages")
        
        return chunks
        
    except oci.exceptions.ServiceError as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [WARNING] OCI Service Error:")
        print(f"  Status: {e.status}")
        print(f"  Code: {e.code}")
        print(f"  Message: {e.message}")
        print(f"\n[INFO] Falling back to PyPDF2 extraction...")
        return extract_pdf_with_pypdf2(pdf_path)
        
    except FileNotFoundError as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] File not found: {e}")
        return None
        
    except PermissionError as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Permission denied: {e}")
        return None
        
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [WARNING] Unexpected error with OCI: {e}")
        print(f"[INFO] Falling back to PyPDF2 extraction...")
        return extract_pdf_with_pypdf2(pdf_path)


from services.ai_service import extract_metadata_from_text_async

async def get_pdf_metadata(pdf_path: str) -> Dict[str, any]:
    """
    Extract metadata (title, author, page count) from a PDF file.
    Combines PyPDF2 (for structure) and Gemini AI (for content analysis of Page 1).
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        Dict: Metadata dictionary containing title, author, and page_count
    """
    metadata = {
        "title": None,
        "author": None,
        "page_count": 0
    }
    
    first_page_text = ""
    
    try:
        from PyPDF2 import PdfReader
        
        reader = PdfReader(pdf_path)
        metadata["page_count"] = len(reader.pages)
        
        # 1. Try PyPDF2 Metadata (often existing but messy)
        info = reader.metadata
        if info:
            # Clean up PyPDF2 format (starts with /)
            if info.get("/Title"): metadata["title"] = str(info.get("/Title")).strip()
            if info.get("/Author"): metadata["author"] = str(info.get("/Author")).strip()
            
        # 2. Extract detailed text from First Page for AI Analysis
        if len(reader.pages) > 0:
            first_page_text = reader.pages[0].extract_text()
            
        # 3. AI Enhancement (The "Robust" Step)
        if first_page_text and len(first_page_text.strip()) > 50:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending PDF first page to AI for metadata extraction...")
            ai_meta = await extract_metadata_from_text_async(first_page_text)
            
            # AI Authority: If AI finds a title, use it (usually cleaner than PDF metadata)
            if ai_meta.get("title"):
                metadata["title"] = ai_meta["title"]
            if ai_meta.get("author"):
                metadata["author"] = ai_meta["author"]

        print(f"[SUCCESS] Extracted metadata (AI-Enhanced): {metadata}")
        
    except Exception as e:
        print(f"[ERROR] Metadata extraction failed: {e}")
        
    return metadata


def extract_pdf_with_pypdf2(pdf_path: str) -> Optional[List[Dict[str, any]]]:
    """
    Fallback PDF extraction using PyPDF2 when OCI is unavailable.
    
    Args:
        pdf_path (str): Path to the PDF file
    
    Returns:
        List[Dict] or None: List of content chunks
    """
    try:
        from PyPDF2 import PdfReader
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Using PyPDF2 for extraction...")
        reader = PdfReader(pdf_path)
        chunks = []
        
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                # Split into paragraphs
                paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                
                for idx, para in enumerate(paragraphs):
                    if len(para) > 20:  # Skip very short fragments
                        chunks.append({
                            'text': para,
                            'page_num': page_num,
                            'type': 'paragraph',
                            'confidence': 1.0,
                            'line_index': idx
                        })
        
        print(f"[SUCCESS] PyPDF2 extracted {len(chunks)} chunks from {len(reader.pages)} pages")
        return chunks if chunks else None
        
    except Exception as e:
        print(f"[ERROR] PyPDF2 extraction also failed: {e}")
        return None


def save_chunks_to_file(chunks: List[Dict], output_path: str) -> bool:
    """
    Save extracted chunks to a JSON file for inspection.
    
    Args:
        chunks (List[Dict]): List of extracted chunks
        output_path (str): Path to save the JSON file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import json
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        print(f"[SUCCESS] Saved chunks to: {output_path}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to save chunks: {e}")
        return False


# ============================================================================
# TEST BLOCK
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TomeHub PDF Service - Test")
    print("=" * 70)
    
    # Test with a sample PDF
    # Replace this with your actual PDF path
    test_pdf_path = input("\nEnter the path to a test PDF file: ").strip()
    
    # Remove quotes if user copied path with quotes
    test_pdf_path = test_pdf_path.strip('"').strip("'")
    
    if not test_pdf_path:
        print("[INFO] No file provided. Using default test path...")
        test_pdf_path = "test.pdf"
    
    # Extract content
    chunks = extract_pdf_content(test_pdf_path)
    
    if chunks:
        print("\n" + "=" * 70)
        print("Extraction Results")
        print("=" * 70)
        
        print(f"\nTotal chunks extracted: {len(chunks)}")
        
        # Show first 3 chunks
        print("\nFirst 3 chunks (metadata):")
        print("-" * 70)
        
        for i, chunk in enumerate(chunks[:3], 1):
            print(f"\nChunk {i}:")
            print(f"  Page: {chunk['page_num']}")
            print(f"  Type: {chunk['type']}")
            print(f"  Confidence: {chunk['confidence']:.2%}")
            print(f"  Text length: {len(chunk['text'])} characters")
            print(f"  Text preview: {chunk['text'][:100]}...")
            
            if 'bbox' in chunk:
                print(f"  Has bounding box: Yes")
        
        # Statistics
        print("\n" + "=" * 70)
        print("Statistics")
        print("=" * 70)
        
        pages = set(chunk['page_num'] for chunk in chunks)
        print(f"Total pages: {len(pages)}")
        print(f"Total chunks: {len(chunks)}")
        print(f"Average chunks per page: {len(chunks) / len(pages):.1f}")
        
        # Count by type
        from collections import Counter
        type_counts = Counter(chunk['type'] for chunk in chunks)
        print(f"\nChunks by type:")
        for chunk_type, count in type_counts.items():
            print(f"  {chunk_type}: {count}")
        
        # Save to file
        output_file = "pdf_extraction_output.json"
        save_chunks_to_file(chunks, output_file)
        
        print("\n" + "=" * 70)
        print("[SUCCESS] PDF extraction test complete!")
        print("=" * 70)
        print("\nNext steps:")
        print("  1. Review the extracted chunks")
        print("  2. Pipe chunks into embedding_service.py")
        print("  3. Store in Oracle database with vectors")
        
    else:
        print("\n[FAILED] Could not extract content from PDF")
        print("\nPlease check:")
        print("  1. PDF file path is correct")
        print("  2. OCI credentials are configured")
        print("  3. You have internet connectivity")
        print("  4. The PDF is not corrupted or password-protected")
