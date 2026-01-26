
# GraphRAG Prompts

GRAPH_EXTRACTION_PROMPT = """Analyze the following text fragment and extract the key concepts and their relationships.
Format your response as a valid JSON object with two keys: 'concepts' (list of strings) and 'relations' (list of [source, type, target]).

Text: "{text}"

Rules for Extraction:
1. EXTRACT ABSTRACT CONCEPTS: Look for philosophical terms like 'Vicdan', 'Ahlak', 'Adalet', 'Özgürlük' - NOT just people or places.
2. EXTRACT RELATIONSHIPS: capture logical or causal links.
   - Example: ["Vicdan", "TEMELİDİR", "Ahlak"] (Conscience is the basis of Morality)
   - Example: ["Sokrates", "SAVUNUR", "Tümevarım"] (Socrates defends Induction)
3. Output ONLY the JSON.
"""
