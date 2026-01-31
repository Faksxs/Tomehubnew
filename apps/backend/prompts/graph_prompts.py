
# GraphRAG Prompts

GRAPH_EXTRACTION_PROMPT = """Analyze the following text fragment and extract the key concepts and their relationships.
Format your response as a valid JSON object with two keys: 'concepts' (list of strings) and 'relations' (list of [source, type, target, confidence]).

Text: "{text}"

Rules for Extraction:

1. EXTRACT ABSTRACT CONCEPTS: Look for philosophical terms like 'Vicdan', 'Ahlak', 'Adalet', 'Özgürlük' - NOT just people or places.

2. EXTRACT AUTHOR NAMES: When a thinker, philosopher, or author is mentioned (e.g., Camus, Descartes, Sokrates), extract as a concept.

3. EXTRACT RELATIONSHIPS - Use these relation types:
   
   CONCEPTUAL RELATIONS:
   - TEMELİDİR: "X is the foundation of Y" → ["Vicdan", "TEMELİDİR", "Ahlak", 1.0]
   - İÇERİR: "X contains/includes Y" → ["Felsefe", "İÇERİR", "Etik", 0.9]
   - KARŞITIR: "X opposes Y" → ["Özgürlük", "KARŞITIR", "Kölelik", 1.0]
   
   AUTHORIAL DEFINITIONS (CRITICAL - Extract these!):
   - TANIMLAR: When author X defines concept Y as Z → ["Camus", "TANIMLAR", "insan isyan eden hayvandır", 1.0]
   - İDDİA_EDER: When author X claims something → ["Descartes", "İDDİA_EDER", "düşünüyorum öyleyse varım", 1.0]
   - SAVUNUR: When author X defends/advocates Y → ["Sokrates", "SAVUNUR", "erdem bilgidir", 0.9]
   
   CONCEPTUAL ASSERTIONS (For Layer 4 Flow):
   - CONCEPTUAL_ASSERTION: When text states a core thesis or conceptual claim
     Example: "İnsan özgürlüğe mahkumdur" → ["özgürlük", "CONCEPTUAL_ASSERTION", "insan özgürlüğe mahkumdur", 1.0]
   
   PATTERN TO LOOK FOR:
   - "X'e göre..." → Extract as TANIMLAR or İDDİA_EDER
   - "X'ün dediği gibi..." → Extract as TANIMLAR
   - "X bunu şöyle ifade ediyor..." → Extract as TANIMLAR
   - Strong declarative sentences → Extract as CONCEPTUAL_ASSERTION


4. CONFIDENCE SCORE (0.0 - 1.0):
   - 1.0: Explicitly stated in text ("A is B", "X'e göre Y").
   - 0.8: Strongly implied.
   - 0.5: Loose association or co-occurrence.

5. Output ONLY the JSON.

EXAMPLE OUTPUT:
{{
  "concepts": ["Camus", "insan", "isyan", "hayvan"],
  "relations": [
    ["Camus", "TANIMLAR", "insan isyan eden hayvandır", 1.0],
    ["isyan", "TEMELİDİR", "insan doğası", 0.8]
  ]
}}
"""
