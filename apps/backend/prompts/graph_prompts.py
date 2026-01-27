
# GraphRAG Prompts

GRAPH_EXTRACTION_PROMPT = """Analyze the following text fragment and extract the key concepts and their relationships.
Format your response as a valid JSON object with two keys: 'concepts' (list of strings) and 'relations' (list of [source, type, target, confidence]).

Text: "{text}"

Rules for Extraction:
1. EXTRACT ABSTRACT CONCEPTS: Look for philosophical terms like 'Vicdan', 'Ahlak', 'Adalet', 'Özgürlük' - NOT just people or places.
2. EXTRACT RELATIONSHIPS: capture logical or causal links.
   - Example directly stated: ["Vicdan", "TEMELİDİR", "Ahlak", 1.0]
   - Example implied: ["Sokrates", "SAVUNUR", "Tümevarım", 0.7]
3. CONFIDENCE SCORE (0.0 - 1.0):
   - 1.0: Explicitly stated in text ("A is B", "X causes Y").
   - 0.8: Strongly implied.
   - 0.5: Loose association or co-occurrence.
4. Output ONLY the JSON.
"""
