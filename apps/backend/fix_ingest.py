import os, re
path = 'services/ingestion_service.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace table references
text = re.sub(r'\bTOMEHUB_CONTENT\b(?!_V2|_TAGS|_CATEGORIES)', 'TOMEHUB_CONTENT_V2', text)
text = text.replace('alias = "TOMEHUB_CONTENT_V2"', 'alias = "TOMEHUB_CONTENT_V2"')

# Replace known INSERT statements specifically for TOMEHUB_CONTENT_V2
text = text.replace(
    '(firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, lemma_tokens, token_freq, categories)',
    '(firebase_uid, content_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, item_id, normalized_content, lemma_tokens, token_freq, categories)'
)

text = text.replace(
    '(firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, lemma_tokens, categories, "COMMENT", tags)',
    '(firebase_uid, content_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, item_id, normalized_content, lemma_tokens, categories, "COMMENT", tags)'
)

text = text.replace(
    '(firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, book_id, vec_embedding, normalized_content, lemma_tokens, categories, "COMMENT", tags)',
    '(firebase_uid, content_type, title, content_chunk, chunk_type, page_number, chunk_index, item_id, vec_embedding, normalized_content, lemma_tokens, categories, "COMMENT", tags)'
)

# For DELETE FROM TOMEHUB_CONTENT_V2
text = text.replace(
    'DELETE FROM TOMEHUB_CONTENT_V2 WHERE firebase_uid = :p_uid AND title = :p_title AND book_id IS NULL',
    'DELETE FROM TOMEHUB_CONTENT_V2 WHERE firebase_uid = :p_uid AND title = :p_title AND item_id IS NULL'
)

text = text.replace(
    'DELETE FROM TOMEHUB_CONTENT_V2 WHERE firebase_uid = :p_uid AND title = :p_title AND source_type',
    'DELETE FROM TOMEHUB_CONTENT_V2 WHERE firebase_uid = :p_uid AND title = :p_title AND content_type'
)

text = text.replace(
    'DELETE FROM TOMEHUB_CONTENT_V2 WHERE firebase_uid = :uid AND source_type IN',
    'DELETE FROM TOMEHUB_CONTENT_V2 WHERE firebase_uid = :uid AND content_type IN'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('ingestion_service.py fixed.')
