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
from typing import Any, Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv
import oci
import re
import requests
from config import settings
from services.chunk_quality_audit_service import (
    analyze_chunk_quality,
    detect_repeated_margin_signatures,
    is_reference_like,
    looks_like_table_of_contents,
    normalize_line_signature,
    should_skip_for_ingestion,
)

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


def clean_text_artifacts(text: str) -> str:
    """
    Conservative OCR cleanup. Keep this deterministic and low-risk.
    """
    if not text:
        return text
    text = re.sub(r"(?<=[A-Za-zÇĞİÖŞÜçğıöşü])1(?=[A-Za-zÇĞİÖŞÜçğıöşü])", "\u0131", text)
    text = re.sub(r"(?<=[a-zçğıöşü])1\b", "\u0131", text)
    text = re.sub(r"\b~ok\b", "\u00e7ok", text, flags=re.IGNORECASE)
    text = re.sub(r"\bi~in\b", "i\u00e7in", text, flags=re.IGNORECASE)
    text = re.sub(r"\bi~inde\b", "i\u00e7inde", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_SENTENCE_END_RE = re.compile(r'[.!?…”"\')\]]\s*$')
_CONTINUATION_START_RE = re.compile(
    r'^(?:[-,;:)\]"\'“‘]|ve\b|veya\b|ama\b|ancak\b|fakat\b|ile\b|ki\b|de\b|da\b|gibi\b|icin\b|için\b)',
    flags=re.IGNORECASE,
)
_HEADING_LIKE_RE = re.compile(r"^[A-Z0-9ÇĞİÖŞÜ][A-Z0-9ÇĞİÖŞÜ\s:;,'\"()/-]{3,}$")


class BibliographyDetector:
    """
    Detect content that should not be embedded as body text.
    """

    @staticmethod
    def is_bibliography_or_index(text: str) -> bool:
        return is_reference_like(text) or looks_like_table_of_contents(text)


def calculate_sis(text: str) -> dict:
    """
    Calculate Sentence Integrity Score (SIS) for a text chunk.
    Returns a dict with score and decision.
    """
    if not text:
        return {"score": 0.0, "decision": "QUARANTINE", "details": ["empty"]}

    analysis = analyze_chunk_quality(text)
    details = list(analysis.get("flags", []))
    score = float(analysis.get("score", 0.0))

    if analysis["bibliography_like"] or analysis["toc_like"] or analysis["page_artifact"]:
        return {"score": 0.0, "decision": "QUARANTINE", "details": details or ["non_body"]}

    if analysis["broken_start"] and analysis["broken_end"]:
        score = min(score, 0.2)
    elif analysis["broken_start"] or analysis["broken_end"]:
        score = min(score, 0.45)

    if analysis["short_fragment"] and analysis["ocr_noise"]:
        score = min(score, 0.2)

    score = round(max(0.0, min(1.0, score)), 2)
    if score >= 0.65:
        decision = "EMBED"
    elif score >= 0.4:
        decision = "REVIEW"
    else:
        decision = "QUARANTINE"

    return {"score": score, "decision": decision, "details": details}


def _prune_non_body_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for chunk in chunks or []:
        text = re.sub(r"\s+", " ", str(chunk.get("text", "") or "")).strip()
        if not text:
            continue
        page_num = int(chunk.get("page_num", 0) or 0)
        skip, analysis = should_skip_for_ingestion(
            text,
            page_number=page_num,
        )
        # Keep body-like chunks, but prune obvious non-body material from raw extraction output.
        if skip and (
            analysis.get("front_matter_like")
            or analysis.get("imprint_like")
            or analysis.get("catalog_like")
            or analysis.get("address_like")
            or analysis.get("heading_like")
            or analysis.get("orphan_fragment")
            or analysis.get("page_artifact")
            or analysis.get("bibliography_like")
            or analysis.get("toc_like")
        ):
            continue
        chunk["text"] = text
        filtered.append(chunk)
    return filtered


class ChunkReconstructor:
    """
    Stateful class to buffer and reconstruct broken PDF chunks across pages.
    """

    def __init__(self):
        self.buffer_chunk = None
        self.final_chunks = []
        self.merge_stats = 0

    def add(self, new_chunk: dict):
        text = re.sub(r"\s+", " ", str(new_chunk.get("text", "") or "")).strip()
        if not text:
            return
        if BibliographyDetector.is_bibliography_or_index(text):
            self._finalize_buffer()
            return

        new_chunk["text"] = text
        if self.buffer_chunk:
            if self._should_merge(self.buffer_chunk, new_chunk):
                separator = "" if text.startswith("-") or self.buffer_chunk["text"].endswith("-") else " "
                merged_text = (self.buffer_chunk["text"].rstrip("-") + separator + text.lstrip("-")).strip()
                self.buffer_chunk["text"] = re.sub(r"\s+", " ", merged_text).strip()
                self.buffer_chunk["confidence"] = min(self.buffer_chunk["confidence"], new_chunk["confidence"])
                self.merge_stats += 1
                return
            self._finalize_buffer()

        self.buffer_chunk = new_chunk

    def _finalize_buffer(self):
        if self.buffer_chunk:
            text = re.sub(r"\s+", " ", str(self.buffer_chunk.get("text", "") or "")).strip()
            if not text:
                self.buffer_chunk = None
                return
            self.buffer_chunk["text"] = text
            self.buffer_chunk["sis"] = calculate_sis(text)
            self.final_chunks.append(self.buffer_chunk)
            self.buffer_chunk = None

    def flush(self):
        self._finalize_buffer()

    @staticmethod
    def _looks_heading(text: str) -> bool:
        value = str(text or "").strip()
        if len(value) < 4 or len(value) > 120:
            return False
        if _SENTENCE_END_RE.search(value):
            return False
        return bool(_HEADING_LIKE_RE.match(value))

    @staticmethod
    def _needs_continuation(text: str) -> bool:
        value = str(text or "").strip()
        return bool(value) and not bool(_SENTENCE_END_RE.search(value))

    @staticmethod
    def _starts_as_continuation(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        return value[0].islower() or bool(_CONTINUATION_START_RE.match(value))

    def _should_merge(self, buffer_chunk: Dict[str, Any], new_chunk: Dict[str, Any]) -> bool:
        buffer_text = str(buffer_chunk.get("text", "") or "").strip()
        next_text = str(new_chunk.get("text", "") or "").strip()
        if not buffer_text or not next_text:
            return False
        if self._looks_heading(next_text) or self._looks_heading(buffer_text):
            return False
        if BibliographyDetector.is_bibliography_or_index(next_text):
            return False

        current_page = int(buffer_chunk.get("page_num", 0) or 0)
        next_page = int(new_chunk.get("page_num", 0) or 0)
        if next_page - current_page not in (0, 1):
            return False

        if next_page == current_page and self._needs_continuation(buffer_text):
            return True
        if buffer_text.endswith("-"):
            return True
        if self._needs_continuation(buffer_text) and self._starts_as_continuation(next_text):
            return True
        if next_page == current_page and len(buffer_text.split()) <= 6:
            return True
        return False


def _collect_page_lines(page: Any) -> Dict[str, Any]:
    lines: List[Dict[str, Any]] = []
    if hasattr(page, "lines") and page.lines:
        for line_idx, line in enumerate(page.lines):
            cleaned_text = clean_text_artifacts(getattr(line, "text", ""))
            if not cleaned_text:
                continue
            lines.append(
                {
                    "text": cleaned_text,
                    "confidence": getattr(line, "confidence", 1.0) if hasattr(line, "confidence") else 1.0,
                    "line_index": line_idx,
                    "bbox": getattr(line, "bounding_polygon", None),
                }
            )
    return {"page_num": getattr(page, "page_number", 0), "lines": lines}


def _payload_get(mapping: Dict[str, Any], *keys: str):
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _collect_page_lines_from_payload(page: Dict[str, Any]) -> Dict[str, Any]:
    page_num = _payload_get(page, "page_number", "pageNumber") or 0
    line_payloads = _payload_get(page, "lines") or []
    if not line_payloads:
        paragraphs = _payload_get(page, "paragraphs") or []
        line_payloads = [
            {"text": item.get("text", ""), "confidence": item.get("confidence", 1.0)}
            for item in paragraphs
            if isinstance(item, dict)
        ]

    lines: List[Dict[str, Any]] = []
    for line_idx, line in enumerate(line_payloads):
        if not isinstance(line, dict):
            continue
        cleaned_text = clean_text_artifacts(str(_payload_get(line, "text", "value") or ""))
        if not cleaned_text:
            continue
        lines.append(
            {
                "text": cleaned_text,
                "confidence": float(_payload_get(line, "confidence") or 1.0),
                "line_index": line_idx,
                "bbox": _payload_get(line, "boundingPolygon", "bounding_polygon"),
            }
        )
    return {"page_num": int(page_num or 0), "lines": lines}


def _extract_pages_from_payload(node: Any) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    if isinstance(node, dict):
        direct_pages = _payload_get(node, "pages")
        if isinstance(direct_pages, list):
            for page in direct_pages:
                if isinstance(page, dict):
                    pages.append(page)
        for value in node.values():
            pages.extend(_extract_pages_from_payload(value))
    elif isinstance(node, list):
        for item in node:
            pages.extend(_extract_pages_from_payload(item))
    return pages


def extract_pdf_content_from_async_output(payloads: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    page_entries: List[Dict[str, Any]] = []
    for payload in payloads or []:
        for page in _extract_pages_from_payload(payload):
            page_entries.append(_collect_page_lines_from_payload(page))

    if not page_entries:
        return None

    repeated_margin_signatures = detect_repeated_margin_signatures(page_entries)
    reconstructor = ChunkReconstructor()
    for page_entry in page_entries:
        page_num = page_entry.get("page_num")
        for line in page_entry.get("lines", []):
            cleaned_text = str(line.get("text") or "").strip()
            if not cleaned_text:
                continue
            signature = normalize_line_signature(cleaned_text)
            if signature and signature in repeated_margin_signatures:
                continue
            reconstructor.add(
                {
                    "text": cleaned_text,
                    "page_num": page_num,
                    "type": "paragraph",
                    "confidence": line.get("confidence", 1.0),
                    "line_index": line.get("line_index", 0),
                }
            )
    reconstructor.flush()
    final_chunks = _prune_non_body_chunks(reconstructor.final_chunks)
    return final_chunks or None


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

        page_entries = [_collect_page_lines(page) for page in response.data.pages]
        repeated_margin_signatures = detect_repeated_margin_signatures(page_entries)
        if repeated_margin_signatures:
            _runtime_log(
                f"[INFO] Detected {len(repeated_margin_signatures)} repeated header/footer signatures",
                level="debug",
            )

        for page_entry in page_entries:
            page_num = page_entry.get("page_num")
            for line in page_entry.get("lines", []):
                cleaned_text = str(line.get("text") or "").strip()
                if not cleaned_text:
                    continue
                signature = normalize_line_signature(cleaned_text)
                if signature and signature in repeated_margin_signatures:
                    continue

                chunk = {
                    "text": cleaned_text,
                    "page_num": page_num,
                    "type": "paragraph",
                    "confidence": line.get("confidence", 1.0),
                    "line_index": line.get("line_index", 0),
                }

                if line.get("bbox") is not None:
                    try:
                        chunk["bbox"] = {
                            "points": [(p.x, p.y) for p in line["bbox"].normalized_vertices]
                        }
                    except Exception:
                        pass

                reconstructor.add(chunk)
        
        # Finalize any remaining buffer
        reconstructor.flush()
        final_chunks = _prune_non_body_chunks(reconstructor.final_chunks)
        
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] Extraction complete!")
        _runtime_log(f"[SUCCESS] Extracted {len(final_chunks)} chunks from {total_pages} pages (Merged {reconstructor.merge_stats} splits)")
        
        return final_chunks
        
    except oci.exceptions.ServiceError as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [WARNING] OCI Service Error:")
        _runtime_log(f"  Status: {e.status}")
        _runtime_log(f"  Code: {e.code}")
        _runtime_log(f"  Message: {e.message}")
        if e.status == 400 and ("Page count" in e.message or "LimitExceeded" in e.message):
            _runtime_log(f"\n[ERROR] OCI 5-page limit exceeded or file too large. Please use Async Ingestion.")
        return None
        
    except FileNotFoundError as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] File not found: {e}")
        return None
        
    except PermissionError as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Permission denied: {e}")
        return None
        
    except Exception as e:
        _runtime_log(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Unexpected error with OCI: {e}")
        return None


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
        # 1. Use OCI to extract all text, which gives us pages and chunks
        _runtime_log(f"[{datetime.now().strftime('%H:%M:%S')}] Requesting OCI Document Understanding for metadata parsing...")
        chunks = extract_pdf_content(pdf_path)
        
        if chunks:
            # Calculate page count from chunks
            metadata["page_count"] = max((c.get("page_num", 1) for c in chunks), default=0)
            
            # Extract detailed text from First Page for AI Analysis
            first_page_text = "\n".join([c.get("text", "") for c in chunks if c.get("page_num") == 1])
            
            # 2. AI Enhancement (The "Robust" Step)
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
