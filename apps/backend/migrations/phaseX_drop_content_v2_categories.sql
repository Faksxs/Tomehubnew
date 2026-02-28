-- Phase X: remove denormalized CONTENT_V2.CATEGORIES and move category source to LIBRARY_ITEMS.CATEGORY_JSON.
-- Idempotent script:
-- 1) If CATEGORIES exists, backfill missing CATEGORY_JSON from latest chunk category per item.
-- 2) Drop TOMEHUB_CONTENT_V2.CATEGORIES.

DECLARE
  v_has_col NUMBER := 0;
BEGIN
  SELECT COUNT(*)
    INTO v_has_col
    FROM USER_TAB_COLUMNS
   WHERE TABLE_NAME = 'TOMEHUB_CONTENT_V2'
     AND COLUMN_NAME = 'CATEGORIES';

  IF v_has_col > 0 THEN
    EXECUTE IMMEDIATE q'~
      MERGE INTO TOMEHUB_LIBRARY_ITEMS li
      USING (
          SELECT firebase_uid, item_id, cats
          FROM (
              SELECT
                  firebase_uid,
                  item_id,
                  TRIM(DBMS_LOB.SUBSTR(categories, 4000, 1)) AS cats,
                  ROW_NUMBER() OVER (
                      PARTITION BY firebase_uid, item_id
                      ORDER BY id DESC
                  ) AS rn
              FROM TOMEHUB_CONTENT_V2
              WHERE categories IS NOT NULL
                AND DBMS_LOB.GETLENGTH(categories) > 0
          ) s
          WHERE s.rn = 1
            AND s.cats IS NOT NULL
      ) src
      ON (li.firebase_uid = src.firebase_uid AND li.item_id = src.item_id)
      WHEN MATCHED THEN
          UPDATE SET
              li.category_json = CASE
                  WHEN li.category_json IS NULL
                  THEN TO_CLOB('["' || REPLACE(REPLACE(src.cats, '"', ''), ',', '","') || '"]')
                  ELSE li.category_json
              END,
              li.updated_at = CURRENT_TIMESTAMP
    ~';

    EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT_V2 DROP COLUMN CATEGORIES';
  END IF;
END;
/
