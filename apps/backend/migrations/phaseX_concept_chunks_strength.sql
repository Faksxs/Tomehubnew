-- Phase X: Concept Chunks Strength + Justification
-- NOTE: If STRENGTH already populated, modify precision may fail. Add new column if needed.

-- Strength stays NUMBER (existing column) to avoid ORA-01440 on populated tables.
-- We store 0.0-1.0 values directly; no precision change required.

-- Explainability note
ALTER TABLE TOMEHUB_CONCEPT_CHUNKS
ADD (JUSTIFICATION CLOB);
