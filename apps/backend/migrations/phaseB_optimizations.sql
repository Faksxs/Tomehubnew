-- Phase B: Performance Optimizations
-- Adds missing indexes identified during profiling

-- 1. Index on TOMEHUB_CONTENT(firebase_uid)
-- Critical for every search query as it filters by user
CREATE INDEX idx_content_firebase_uid ON TOMEHUB_CONTENT(firebase_uid);

-- 2. Indexes on TOMEHUB_RELATIONS for join performance
-- Necessary for graph traversal (src -> dst joins)
CREATE INDEX idx_relations_src_id ON TOMEHUB_RELATIONS(src_id);
CREATE INDEX idx_relations_dst_id ON TOMEHUB_RELATIONS(dst_id);

-- 3. Functional Index for Concept Lookup
-- Optimizes SELECT ... FROM TOMEHUB_CONCEPTS WHERE LOWER(name) LIKE ...
CREATE INDEX idx_concepts_name_lower ON TOMEHUB_CONCEPTS(LOWER(name));

-- 4. Index on TOMEHUB_CONCEPT_CHUNKS(concept_id)
-- Already has a PK on (concept_id, content_id), but separate index on concept_id 
-- might help if PK order is different. 
-- Wait, PK is (CONCEPT_ID, CONTENT_ID) so index on CONCEPT_ID is already there (prefix).

COMMIT;
