
import json

PROMPT_ENRICH_BOOK = """
Enrich this book data with missing details (summary, tags, publisher, publication year, page count).

Current Data:
{json_data}

CRITICAL LANGUAGE INSTRUCTION:
1. DETECT the language of the book title and author.
2. IF the book is clearly English, generate 'summary' and 'tags' in ENGLISH.
3. IF the book is Turkish OR the language is unclear/ambiguous, generate 'summary' and 'tags' in TURKISH (Default).

Return the COMPLETE updated JSON object.
- Ensure 'summary' is detailed (at least 3 sentences).
- Ensure 'tags' has at least 3 relevant genres/topics.
- Do NOT change the title or author if they look correct.
- For 'translator' and 'pageCount', return 'null' if you are purely guessing.

INCLUDE a 'confidence_scores' object in your JSON response:
{{
  "translator": "high" | "medium" | "low",
  "pageCount": "high" | "medium" | "low"
}}

Return ONLY valid JSON. No markdown.
"""

try:
    print("Attempting to format prompt...")
    book_data = {"title": "Test Book", "author": "Test Author"}
    prompt = PROMPT_ENRICH_BOOK.format(json_data=json.dumps(book_data, ensure_ascii=False))
    print("Success!")
    print(prompt[:100])
except KeyError as e:
    print(f"KeyError detected: {repr(e)}")
except Exception as e:
    print(f"Other error: {e}")
