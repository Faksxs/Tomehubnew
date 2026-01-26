# -*- coding: utf-8 -*-
"""
TomeHub EPUB Service
====================
Handles EPUB text extraction and smart chunking.
Strategies:
- Extracts text chapter by chapter.
- Merges small paragraphs to reduce noise.
- Splits large chapters into logical manageable chunks (500-1000 tokens).

Author: TomeHub Team
Date: 2026-01-09
"""

import os
import bs4
import ebooklib
from ebooklib import epub
from typing import List, Dict, Optional
from datetime import datetime

# Chunking Configuration
MIN_CHUNK_SIZE = 300   # Minimum characters to form a chunk (approx 50-60 words)
MAX_CHUNK_SIZE = 3000  # Maximum characters per chunk (approx 500-600 words)
OVERLAP_SIZE = 200     # Overlap between split chunks to preserve context

def extract_epub_content(epub_path: str) -> Optional[List[Dict[str, any]]]:
    """
    Extract content from an EPUB file with smart chunking.
    
    Args:
        epub_path (str): Path to the EPUB file.
        
    Returns:
        List[Dict]: List of chunks with 'text', 'chapter', 'chunk_index'.
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting EPUB extraction: {epub_path}")
    
    if not os.path.exists(epub_path):
        print(f"[ERROR] File not found: {epub_path}")
        return None
        
    try:
        book = epub.read_epub(epub_path)
        chunks = []
        global_chunk_index = 0
        
        # Iterate document items
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                # Extract raw HTML content
                content = item.get_content()
                
                # Parse with BeautifulSoup
                soup = bs4.BeautifulSoup(content, 'html.parser')
                
                # Try to find a chapter title
                chapter_title = "Unknown Chapter"
                headers = soup.find_all(['h1', 'h2', 'h3'])
                if headers:
                    chapter_title = headers[0].get_text().strip()
                
                # Get all text paragraphs
                paragraphs = [p.get_text().strip() for p in soup.find_all('p')]
                paragraphs = [p for p in paragraphs if p] # Filter empty
                
                if not paragraphs:
                    continue
                
                # --- SMART CHUNKING LOGIC ---
                current_chunk = ""
                
                for p in paragraphs:
                    # If adding this paragraph keeps us under MAX_CHUNK_SIZE
                    if len(current_chunk) + len(p) + 1 < MAX_CHUNK_SIZE:
                        current_chunk += p + "\n\n"
                    else:
                        # Current chunk is full, save it if it meets MIN requirements
                        if len(current_chunk) >= MIN_CHUNK_SIZE:
                            chunks.append({
                                'text': current_chunk.strip(),
                                'chapter': chapter_title,
                                'chunk_index': global_chunk_index,
                                'type': 'epub_chunk'
                            })
                            global_chunk_index += 1
                        
                        # Start new chunk with overlap if possible/needed, or just the new paragraph
                        # For simplicity and to avoid cutting mid-sentence logic too abruptly, 
                        # we start fresh with the current paragraph.
                        # Advanced: We could keep the last sentence of previous chunk for overlap.
                        current_chunk = p + "\n\n"
                
                # Add the remaining tail
                if len(current_chunk) >= MIN_CHUNK_SIZE:
                    chunks.append({
                        'text': current_chunk.strip(),
                        'chapter': chapter_title,
                        'chunk_index': global_chunk_index,
                        'type': 'epub_chunk'
                    })
                    global_chunk_index += 1
                    
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Extracted {len(chunks)} chunks from EPUB.")
        return chunks

    except Exception as e:
        print(f"[ERROR] EPUB extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Test block
    path = input("Enter EPUB path: ").strip().strip('"')
    if path:
        results = extract_epub_content(path)
        if results:
            print(f"First chunk preview: {results[0]['text'][:200]}...")
