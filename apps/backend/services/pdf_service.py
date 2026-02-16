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
import logging
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
import oci
import re
from config import settings

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)


def _runtime_log(message: str, level: str = "info") -> None:
    normalized = (level or "info").lower()
    msg = str(message)
    if normalized == "info":
        lowered = msg.lower()
        if "[error]" in lowered:
            normalized = "error"
        elif "[warning]" in lowered or "[warn]" in lowered:
            normalized = "warning"
        elif "[debug]" in lowered:
            normalized = "debug"
    if normalized == "debug":
        if settings.DEBUG_VERBOSE_PIPELINE:
            logger.debug(msg)
        return
    if normalized == "warning":
        logger.warning(msg)
        return
    if normalized == "error":
        logger.error(msg)
        return
    logger.info(msg)


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
    
    _runtime_log(f"[DEBUG] OCI Key File Path: {key_file} (Exists: {os.path.exists(key_file)})")
    required_vars["key_file"] = key_file
    
    return required_vars


def clean_text_artifacts(text: str) -> str:
    """
    Clean common OCR and encoding artifacts from extracted text,
    specifically targeting Turkish character corruptions.
    """
    if not text:
        return text
        
    # 1. Fix numeric '1' acting as 'ı' or 'l' inside words
    # e.g., "Anlam1" -> "Anlamı", "h1z" -> "hız"
    # Strategy: 1 between letters is usually ı
    text = re.sub(r'(?<=[a-zA-ZçğıöşüÇĞİÖŞÜ])1(?=[a-zA-ZçğıöşüÇĞİÖŞÜ])', 'ı', text)
    # End of word '1' (e.g. "Anlam1")
    text = re.sub(r'(?<=[a-zçğıöşü])1\b', 'ı', text)

    # 1.5 Fix specific OCR artifacts reported by user (Aggressive Pass)
    # Generic 'ii' -> 'ü' heuristic (Safe for Turkish context)
    text = text.replace('ii', 'ü')
    text = text.replace('I I', 'Ü')

    # Fix Capital 'O' / '0' acting as 'ü' or 'ö' inside lowercase words
    # e.g. "gOnOmuz" -> "günümüz", "yOnO" -> "yönü"
    # We iterate to catch consecutive/nested O's
    for _ in range(2):
        text = re.sub(r'(?<=[a-zçğıöşü])O(?=[a-zçğıöşüO])', 'ü', text)
        text = re.sub(r'(?<=[a-zçğıöşüO])O(?=[a-zçğıöşü])', 'ü', text)
        text = re.sub(r'(?<=[a-zçğıöşü])0(?=[a-zçğıöşü0])', 'ü', text)
        # Handle word-ending O if preceded by lowercase (e.g. yOnO)
        text = re.sub(r'(?<=[a-zçğıöşü])O\b', 'ü', text)

    # Specific word repairs
    specific_fixes = {
        '<;ev': 'çev',
        '~ikago': 'Chicago',
        '~iddet': 'şiddet',
        ';alt~malar': 'çalışmalar',
        'Ele~tirisi': 'Eleştirisi',
        '~Ankara': 'Ankara',
        '~izgi': 'çizgi',
        '~izmek': 'çizmek',
        '~e~it': 'çeşit',
        '~iinkii': 'çünkü',
        'miizik': 'müzik',
        'biitiin': 'bütün',
        'goriint': 'görünt',
        'dOnyas': 'dünyas',
        'kOitOrel': 'kültürel',
    }
    for bad, good in specific_fixes.items():
        text = text.replace(bad, good)

    # 2. Fix Tilde '~' usages (likely 'ç' or 'ş' or 'ğ')
    # High frequency map
    replacements = {
        r'\b~ok\b': 'çok',
        r'~ok\b': 'çok',
        r'\bi~in\b': 'için',
        r'\bi~inde': 'içinde',
        r'\bge~me': 'geçme',
        r'~ünkü': 'çünkü',
        r'~ıkış': 'çıkış',
        r'~alış': 'çalış',
        r'ka~Tn': 'kaçın',  # heuristic
        r'sonu~': 'sonuç',
        r'ama~': 'amaç',
        r'b~r': 'bir',      # maybe?
        r'olu~tur': 'oluştur',
        r'geli~': 'geliş',
        r'deği~': 'değiş',
        r'konu~': 'konuş',
        r'ya~a': 'yaşa',
        r'dönu~': 'dönüş',
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 3. Generic fallback for ~
    # If ~ follows a/o/u -> likely ç ? (aç, çok, uç)
    # If ~ follows e/i/ö/ü -> likely ç/ş?
    # This is dangerous. Better to just handle the explicit ones above logic 
    # and maybe valid single char errors.
    
    # 4. Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

class BibliographyDetector:
    """
    Detects if a text block is likely part of a Bibliography, Index, or Reference list.
    """
    @staticmethod
    def is_bibliography_or_index(text: str) -> bool:
        if not text: return False
        
        # 1. Header Detection (Strong signal)
        # Matches: "KAYNAKÇA", "BIBLIOGRAPHY", "DİZİN", "INDEX", "KAYNAKLAR"
        if re.search(r'^\s*(KAYNAKÇA|KAYNAKLAR|BIBLIOGRAPHY|DİZİN|INDEX|REFERANSLAR)\s*$', text, re.IGNORECASE):
            return True
            
        # 2. Pattern density check
        # Bibliographies have many years (19xx, 20xx) and city names or "Yay."
        year_matches = len(re.findall(r'\b(19|20)\d{2}\b', text))
        
        # Heuristic: If we have > 3 years in a short text (e.g. < 500 chars), likely a list
        if len(text) < 500 and year_matches >= 3:
            return True
            
        # 3. Index check: High density of page numbers at end of lines
        # e.g. "Adorno, 12, 45, 67"
        lines = text.split('\n')
        index_lines = 0
        for line in lines:
            line = line.strip()
            if not line: continue
            # Ends with number or number list
            if re.search(r',\s*\d+(?:,\s*\d+)*\s*$', line):
                index_lines += 1
            # Or starts with Name, Name...
            if re.match(r'^[A-Z][a-z]+,\s[A-Z]', line):
                index_lines += 0.5 # Weaker signal for index
                
        if len(lines) > 5 and (index_lines / len(lines)) > 0.4:
            return True
            
        return False

def calculate_sis(text: str) -> dict:
    """
    Calculate Sentence Integrity Score (SIS) for a text chunk.
    Returns a dict with score and decision.
    """
    score = 0.0
    details = []

    if not text:
        return {'score': 0, 'decision': 'QUARANTINE', 'details': ['empty']}
        
    # 0. Bibliography/Index Detection
    if BibliographyDetector.is_bibliography_or_index(text):
        return {'score': 0, 'decision': 'QUARANTINE', 'details': ['bibliography_detected']}

    # 1. Ends with sentence terminator (Strongest signal)
    if re.search(r'[.!?…"]\s*$', text):
        score += 0.4
        details.append("valid_ending")
    else:
        details.append("missing_ending")

    # 2. Starts with capital letter
    if text and text[0].isupper():
        score += 0.3
        details.append("valid_start")
    else:
        details.append("lowercase_start")

    # 3. Word count sanity check (e.g. > 3 words)
    words = text.split()
    if len(words) > 3:
        score += 0.3
        details.append("valid_length")
    else:
        details.append("too_short")

    # Normalize float
    score = round(score, 2)

    # Decision Logic
    if score >= 0.7:
        decision = 'EMBED'
    elif score >= 0.4:
        decision = 'REVIEW' # Potentially mergeable but isolated here
    else:
        decision = 'QUARANTINE'

    return {'score': score, 'decision': decision, 'details': details}


class ChunkReconstructor:
    """
    Stateful class to buffer and reconstruct broken PDF chunks across pages.
    """
    def __init__(self):
        self.buffer_chunk = None
        self.final_chunks = []
        self.merge_stats = 0

    def add(self, new_chunk: dict):
        """
        Add a new raw chunk candidate. Decides whether to buffer, merge, or finalize.
        """
        text = new_chunk.get('text', '').strip()
        if not text:
            return

        # Condition 1: Check if we have a buffer waiting
        if self.buffer_chunk:
            buffer_text = self.buffer_chunk['text']
            
            # MERGE CRITERIA:
            # 1. Buffer implies continuation (no sentence end punctuation)
            # 2. New chunk implies continuation (starts lowercase or connector)
            
            buffer_needs_continuation = not re.search(r'[.!?…"]\s*$', buffer_text)
            
            # Check for suffixes or conjunctions at start of new text
            # e.g., "-dan", "ve", "ile"
            lower_start = text[0].islower()
            starts_with_connector = re.match(r'^(-|ve\b|ile\b|ama\b|ki\b|de\b|da\b)', text, re.IGNORECASE)
            
            should_merge = buffer_needs_continuation and (lower_start or starts_with_connector)

            if should_merge:
                # MERGE!
                # If starts with hyphen (suffix), join directly without space ideally, or handle hyphen logic
                # For now, simplistic join with space, but if hyphen, maybe remove space?
                # Case: "kaynaklan-" + "an" -> "kaynaklanan" (If PDF cut word)
                # Case: "bitiyor" + "-dan" -> "bitiyor -dan" (Bad OCR?) or "bitiyor" + " ve"
                
                separator = " "
                if text.startswith("-"):
                    separator = "" # Join suffix directly? Or keep hyphen? 
                    # Usually "-dan" in new line implies separate word in English wrap, but in Turkish PDF extract?
                    # Let's assume space for safety unless we do sophisticated word reconstruction
                
                merged_text = buffer_text + separator + text
                
                # Update buffer with merged content
                self.buffer_chunk['text'] = merged_text
                # Keep page_num of start (or range?) - Keep start page
                # Update confidence (min? avg?)
                self.buffer_chunk['confidence'] = min(self.buffer_chunk['confidence'], new_chunk['confidence'])
                self.merge_stats += 1
                return
            else:
                # No merge. Flush buffer, start new buffer.
                self._finalize_buffer()
        
        # If we are here, either buffer was flushed or didn't exist.
        # Set this new chunk as the current buffer
        self.buffer_chunk = new_chunk

    def _finalize_buffer(self):
        if self.buffer_chunk:
            # Calculate SIS before finalizing
            sis = calculate_sis(self.buffer_chunk['text'])
            self.buffer_chunk['sis'] = sis
            self.final_chunks.append(self.buffer_chunk)
            self.buffer_chunk = None

    def flush(self):
        """Finalize any remaining buffer."""
        self._finalize_buffer()


def extract_pdf_content(pdf_path: str) -> Optional[List[Dict[str, any]]]:
    """
    Extract structured content from a PDF file using OCI Document Understanding.
    Includes Smart Chunk Reconstruction and SIS Scoring.
    """
    _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting PDF extraction (Smart Mode)...")
    _runtime_log(f"[INFO] File: {pdf_path}")
    
    # Validate file exists
    if not os.path.exists(pdf_path):
        _runtime_log(f"[ERROR] File not found: {pdf_path}")
        return None
    
    # Validate file is PDF
    if not pdf_path.lower().endswith('.pdf'):
        _runtime_log(f"[ERROR] File is not a PDF: {pdf_path}")
        return None
    
    try:
        # Load OCI configuration
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Loading OCI configuration...")
        config = get_oci_config()
        
        # Create AI Document client
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Creating OCI Document client...")
        ai_client = oci.ai_document.AIServiceDocumentClient(config)
        
        # Read PDF file
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Reading PDF file...")
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        file_size_mb = len(pdf_bytes) / (1024 * 1024)
        _runtime_log(f"[INFO] File size: {file_size_mb:.2f} MB")
        
        # Encode to base64
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Encoding file...")
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Create inline document (no mime_type parameter in current OCI SDK)
        inline_document = oci.ai_document.models.InlineDocumentDetails(
            data=pdf_base64
        )
        
        # Create analyze request with text extraction and layout analysis
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Preparing analysis request...")
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
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Sending to OCI Document Understanding...")
        _runtime_log(f"[INFO] This may take a few moments for large documents...")
        
        response = ai_client.analyze_document(analyze_request)
        
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Analysis complete!")
        
        # Extract structured chunks using Smart Reconstructor
        reconstructor = ChunkReconstructor()
        
        total_pages = len(response.data.pages)
        _runtime_log(f"[INFO] Processing {total_pages} pages...")
        
        for page in response.data.pages:
            page_num = page.page_number
            # print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing page {page_num}/{total_pages}...")
            
            # Process lines (paragraphs)
            if hasattr(page, 'lines') and page.lines:
                for line_idx, line in enumerate(page.lines):
                    cleaned_text = clean_text_artifacts(line.text)
                    chunk = {
                        'text': cleaned_text,
                        'page_num': page_num,
                        'type': 'paragraph',  # Default type
                        'confidence': line.confidence if hasattr(line, 'confidence') else 1.0,
                        'line_index': line_idx
                    }
                    
                    # Add bounding box if available
                    if hasattr(line, 'bounding_polygon'):
                        chunk['bbox'] = {
                            'points': [(p.x, p.y) for p in line.bounding_polygon.normalized_vertices]
                        }
                    
                    # Feed to reconstructor
                    reconstructor.add(chunk)

            # Optional: Process words if needed (skipped for now)
        
        # Finalize any remaining buffer
        reconstructor.flush()
        final_chunks = reconstructor.final_chunks
        
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] Extraction complete!")
        _runtime_log(f"[SUCCESS] Extracted {len(final_chunks)} chunks from {total_pages} pages (Merged {reconstructor.merge_stats} splits)")
        
        return final_chunks
        
    except oci.exceptions.ServiceError as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [WARNING] OCI Service Error:")
        _runtime_log(f"  Status: {e.status}")
        _runtime_log(f"  Code: {e.code}")
        _runtime_log(f"  Message: {e.message}")
        _runtime_log(f"\n[INFO] Falling back to PyPDF2 extraction...")
        return extract_pdf_with_pypdf2(pdf_path)
        
    except FileNotFoundError as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] File not found: {e}")
        return None
        
    except PermissionError as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Permission denied: {e}")
        return None
        
    except Exception as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [WARNING] Unexpected error with OCI: {e}")
        _runtime_log(f"[INFO] Falling back to PyPDF2 extraction...")
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
            _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Sending PDF first page to AI for metadata extraction...")
            ai_meta = await extract_metadata_from_text_async(first_page_text)
            
            # AI Authority: If AI finds a title, use it (usually cleaner than PDF metadata)
            if ai_meta.get("title"):
                metadata["title"] = ai_meta["title"]
            if ai_meta.get("author"):
                metadata["author"] = ai_meta["author"]

        _runtime_log(f"[SUCCESS] Extracted metadata (AI-Enhanced): {metadata}")
        
    except Exception as e:
        _runtime_log(f"[ERROR] Metadata extraction failed: {e}")
        
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
        
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Using PyPDF2 for extraction...")
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
        
        _runtime_log(f"[SUCCESS] PyPDF2 extracted {len(chunks)} chunks from {len(reader.pages)} pages")
        return chunks if chunks else None
        
    except Exception as e:
        _runtime_log(f"[ERROR] PyPDF2 extraction also failed: {e}")
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
        
        _runtime_log(f"[SUCCESS] Saved chunks to: {output_path}")
        return True
        
    except Exception as e:
        _runtime_log(f"[ERROR] Failed to save chunks: {e}")
        return False


# ============================================================================
# TEST BLOCK
# ============================================================================

if __name__ == "__main__":
    _runtime_log("=" * 70)
    _runtime_log("TomeHub PDF Service - Test")
    _runtime_log("=" * 70)
    
    # Test with a sample PDF
    # Replace this with your actual PDF path
    test_pdf_path = input("\nEnter the path to a test PDF file: ").strip()
    
    # Remove quotes if user copied path with quotes
    test_pdf_path = test_pdf_path.strip('"').strip("'")
    
    if not test_pdf_path:
        _runtime_log("[INFO] No file provided. Using default test path...")
        test_pdf_path = "test.pdf"
    
    # Extract content
    chunks = extract_pdf_content(test_pdf_path)
    
    if chunks:
        _runtime_log("\n" + "=" * 70)
        _runtime_log("Extraction Results")
        _runtime_log("=" * 70)
        
        _runtime_log(f"\nTotal chunks extracted: {len(chunks)}")
        
        # Show first 3 chunks
        _runtime_log("\nFirst 3 chunks (metadata):")
        _runtime_log("-" * 70)
        
        for i, chunk in enumerate(chunks[:3], 1):
            _runtime_log(f"\nChunk {i}:")
            _runtime_log(f"  Page: {chunk['page_num']}")
            _runtime_log(f"  Type: {chunk['type']}")
            _runtime_log(f"  Confidence: {chunk['confidence']:.2%}")
            _runtime_log(f"  Text length: {len(chunk['text'])} characters")
            _runtime_log(f"  Text preview: {chunk['text'][:100]}...")
            
            if 'bbox' in chunk:
                _runtime_log(f"  Has bounding box: Yes")
        
        # Statistics
        _runtime_log("\n" + "=" * 70)
        _runtime_log("Statistics")
        _runtime_log("=" * 70)
        
        pages = set(chunk['page_num'] for chunk in chunks)
        _runtime_log(f"Total pages: {len(pages)}")
        _runtime_log(f"Total chunks: {len(chunks)}")
        _runtime_log(f"Average chunks per page: {len(chunks) / len(pages):.1f}")
        
        # Count by type
        from collections import Counter
        type_counts = Counter(chunk['type'] for chunk in chunks)
        _runtime_log(f"\nChunks by type:")
        for chunk_type, count in type_counts.items():
            _runtime_log(f"  {chunk_type}: {count}")
        
        # Save to file
        output_file = "pdf_extraction_output.json"
        save_chunks_to_file(chunks, output_file)
        
        _runtime_log("\n" + "=" * 70)
        _runtime_log("[SUCCESS] PDF extraction test complete!")
        _runtime_log("=" * 70)
        _runtime_log("\nNext steps:")
        _runtime_log("  1. Review the extracted chunks")
        _runtime_log("  2. Pipe chunks into embedding_service.py")
        _runtime_log("  3. Store in Oracle database with vectors")
        
    else:
        _runtime_log("\n[FAILED] Could not extract content from PDF")
        _runtime_log("\nPlease check:")
        _runtime_log("  1. PDF file path is correct")
        _runtime_log("  2. OCI credentials are configured")
        _runtime_log("  3. You have internet connectivity")
        _runtime_log("  4. The PDF is not corrupted or password-protected")
