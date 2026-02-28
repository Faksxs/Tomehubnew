-- Phase X: Remove unused TOMEHUB_CONCEPTS.EMBEDDING column.
-- This column is no longer used by runtime queries; DESCRIPTION_EMBEDDING remains active.
-- Idempotent: safe to run multiple times.

DECLARE
  v_has_idx NUMBER := 0;
  v_has_col NUMBER := 0;
BEGIN
  SELECT COUNT(*)
    INTO v_has_idx
    FROM USER_INDEXES
   WHERE INDEX_NAME = 'IDX_CONCEPTS_VEC';

  IF v_has_idx > 0 THEN
    EXECUTE IMMEDIATE 'DROP INDEX IDX_CONCEPTS_VEC';
  END IF;

  SELECT COUNT(*)
    INTO v_has_col
    FROM USER_TAB_COLUMNS
   WHERE TABLE_NAME = 'TOMEHUB_CONCEPTS'
     AND COLUMN_NAME = 'EMBEDDING';

  IF v_has_col > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONCEPTS DROP COLUMN EMBEDDING';
  END IF;
END;
/
