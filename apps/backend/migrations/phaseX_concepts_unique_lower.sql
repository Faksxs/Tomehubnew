-- Phase X: Enforce case-insensitive uniqueness on concept names
-- Requires duplicates to be merged before running.

CREATE UNIQUE INDEX uidx_concepts_name_lower ON TOMEHUB_CONCEPTS(LOWER(name));
