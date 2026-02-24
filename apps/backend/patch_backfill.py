import os

path = 'scripts/apply_phase2_backfill.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# I am replacing the src_base SQL query inside _backfill_library_items
old_select = """
        src_base AS (
            SELECT
                ca.ITEM_ID,
                ca.FIREBASE_UID,
                CASE
                    WHEN ca.HAS_BOOKISH = 1 THEN 'BOOK'
                    WHEN ca.HAS_ARTICLE = 1 THEN 'ARTICLE'
                    WHEN ca.HAS_WEBSITE = 1 THEN 'WEBSITE'
                    WHEN ca.CNT_PERSONAL_NOTE > 0 OR ca.CNT_INSIGHT > 0 THEN 'PERSONAL_NOTE'
                    ELSE 'BOOK'
                END AS ITEM_TYPE,
                COALESCE(b.TITLE, ca.REP_TITLE) AS TITLE,
                COALESCE(NULLIF(TRIM(b.AUTHOR), ''), ca.REP_AUTHOR) AS AUTHOR,
                CAST(NULL AS VARCHAR2(2000)) AS SOURCE_URL,
                COALESCE(b.CREATED_AT, ca.MIN_CREATED_AT, CURRENT_TIMESTAMP) AS CREATED_AT_SRC,
                COALESCE(b.LAST_UPDATED, ca.MAX_UPDATED_AT, CURRENT_TIMESTAMP) AS UPDATED_AT_SRC,
                ca.CNT_PERSONAL_NOTE,
                ca.CNT_INSIGHT
            FROM content_agg ca
            LEFT JOIN TOMEHUB_BOOKS b
              ON b.ID = ca.ITEM_ID
             AND b.FIREBASE_UID = ca.FIREBASE_UID
        )
"""

new_select = """
        src_base AS (
            SELECT
                ca.ITEM_ID,
                ca.FIREBASE_UID,
                CASE
                    WHEN ca.HAS_BOOKISH = 1 THEN 'BOOK'
                    WHEN ca.HAS_ARTICLE = 1 THEN 'ARTICLE'
                    WHEN ca.HAS_WEBSITE = 1 THEN 'WEBSITE'
                    WHEN ca.CNT_PERSONAL_NOTE > 0 OR ca.CNT_INSIGHT > 0 THEN 'PERSONAL_NOTE'
                    ELSE 'BOOK'
                END AS ITEM_TYPE,
                COALESCE(b.TITLE, ca.REP_TITLE) AS TITLE,
                COALESCE(NULLIF(TRIM(b.AUTHOR), ''), ca.REP_AUTHOR) AS AUTHOR,
                b.PUBLISHER AS PUBLISHER,
                b.PUBLICATION_DATE AS PUBLICATION_YEAR,
                b.ISBN AS ISBN,
                b.EXTERNAL_URL AS SOURCE_URL,
                b.PAGE_COUNT AS PAGE_COUNT,
                b.COVER_URL AS COVER_URL,
                b.SUMMARY AS SUMMARY_TEXT,
                b.GENERAL_NOTES AS GENERAL_NOTES,
                b.TAGS AS TAGS_JSON,
                b.CATEGORY AS CATEGORY_JSON,
                b.READING_STATUS AS READING_STATUS,
                b.STATUS AS STATUS,
                b.IS_FAVORITE AS IS_FAVORITE,
                COALESCE(b.CREATED_AT, ca.MIN_CREATED_AT, CURRENT_TIMESTAMP) AS CREATED_AT_SRC,
                COALESCE(b.LAST_UPDATED, ca.MAX_UPDATED_AT, CURRENT_TIMESTAMP) AS UPDATED_AT_SRC,
                ca.CNT_PERSONAL_NOTE,
                ca.CNT_INSIGHT
            FROM content_agg ca
            LEFT JOIN TOMEHUB_BOOKS b
              ON b.ID = ca.ITEM_ID
             AND b.FIREBASE_UID = ca.FIREBASE_UID
        )
"""

text = text.replace(old_select.strip(), new_select.strip())

old_insert_sel = """
        SELECT
            sb.ITEM_ID,
            sb.FIREBASE_UID,
            sb.ITEM_TYPE,
            sb.TITLE,
            sb.AUTHOR,
            sb.SOURCE_URL,
            CASE
                WHEN sb.ITEM_TYPE = 'PERSONAL_NOTE' AND sb.CNT_PERSONAL_NOTE > 0 THEN 'EXCLUDED_BY_DEFAULT'
                ELSE 'DEFAULT'
            END AS SEARCH_VISIBILITY,
            CASE
                WHEN sb.ITEM_TYPE = 'PERSONAL_NOTE' AND sb.CNT_PERSONAL_NOTE = 0 AND sb.CNT_INSIGHT > 0 THEN 'IDEAS'
                ELSE NULL
            END AS PERSONAL_NOTE_CATEGORY,
            sb.CREATED_AT_SRC,
            sb.UPDATED_AT_SRC
        FROM src_base sb
"""

new_insert_sel = """
        SELECT
            sb.ITEM_ID,
            sb.FIREBASE_UID,
            sb.ITEM_TYPE,
            sb.TITLE,
            sb.AUTHOR,
            sb.PUBLISHER,
            sb.PUBLICATION_YEAR,
            sb.ISBN,
            sb.SOURCE_URL,
            sb.PAGE_COUNT,
            sb.COVER_URL,
            sb.SUMMARY_TEXT,
            sb.GENERAL_NOTES,
            sb.TAGS_JSON,
            sb.CATEGORY_JSON,
            sb.READING_STATUS,
            sb.STATUS,
            sb.IS_FAVORITE,
            CASE
                WHEN sb.ITEM_TYPE = 'PERSONAL_NOTE' AND sb.CNT_PERSONAL_NOTE > 0 THEN 'EXCLUDED_BY_DEFAULT'
                ELSE 'DEFAULT'
            END AS SEARCH_VISIBILITY,
            CASE
                WHEN sb.ITEM_TYPE = 'PERSONAL_NOTE' AND sb.CNT_PERSONAL_NOTE = 0 AND sb.CNT_INSIGHT > 0 THEN 'IDEAS'
                ELSE NULL
            END AS PERSONAL_NOTE_CATEGORY,
            sb.CREATED_AT_SRC,
            sb.UPDATED_AT_SRC
        FROM src_base sb
"""

text = text.replace(old_insert_sel.strip(), new_insert_sel.strip())

old_insert_stmt = """
        INSERT (
            ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, SOURCE_URL,
            SEARCH_VISIBILITY, PERSONAL_NOTE_CATEGORY, ORIGIN_SYSTEM, ORIGIN_COLLECTION, SYNC_RUN_ID,
            CREATED_AT, UPDATED_AT
        )
        VALUES (
            src.ITEM_ID, src.FIREBASE_UID, src.ITEM_TYPE, src.TITLE, src.AUTHOR, src.SOURCE_URL,
            src.SEARCH_VISIBILITY, src.PERSONAL_NOTE_CATEGORY, 'ORACLE_NATIVE', 'TOMEHUB_CONTENT_AGG', :p_run_id,
            src.CREATED_AT_SRC, src.UPDATED_AT_SRC
        )
"""

new_insert_stmt = """
        INSERT (
            ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, PUBLISHER, PUBLICATION_YEAR, ISBN, SOURCE_URL,
            PAGE_COUNT, COVER_URL, SUMMARY_TEXT, GENERAL_NOTES, TAGS_JSON, CATEGORY_JSON, READING_STATUS, STATUS, IS_FAVORITE,
            SEARCH_VISIBILITY, PERSONAL_NOTE_CATEGORY, ORIGIN_SYSTEM, ORIGIN_COLLECTION, SYNC_RUN_ID,
            CREATED_AT, UPDATED_AT
        )
        VALUES (
            src.ITEM_ID, src.FIREBASE_UID, src.ITEM_TYPE, src.TITLE, src.AUTHOR, src.PUBLISHER, src.PUBLICATION_YEAR, src.ISBN, src.SOURCE_URL,
            src.PAGE_COUNT, src.COVER_URL, src.SUMMARY_TEXT, src.GENERAL_NOTES, src.TAGS_JSON, src.CATEGORY_JSON, src.READING_STATUS, src.STATUS, src.IS_FAVORITE,
            src.SEARCH_VISIBILITY, src.PERSONAL_NOTE_CATEGORY, 'ORACLE_NATIVE', 'TOMEHUB_CONTENT_AGG', :p_run_id,
            src.CREATED_AT_SRC, src.UPDATED_AT_SRC
        )
"""

text = text.replace(old_insert_stmt.strip(), new_insert_stmt.strip())

old_update_stmt = """
        UPDATE SET
            li.ITEM_TYPE = COALESCE(li.ITEM_TYPE, src.ITEM_TYPE),
            li.TITLE = COALESCE(li.TITLE, src.TITLE),
            li.AUTHOR = COALESCE(li.AUTHOR, src.AUTHOR),
            li.SOURCE_URL = COALESCE(li.SOURCE_URL, src.SOURCE_URL),
            li.PERSONAL_NOTE_CATEGORY = COALESCE(li.PERSONAL_NOTE_CATEGORY, src.PERSONAL_NOTE_CATEGORY),
            li.SEARCH_VISIBILITY = COALESCE(li.SEARCH_VISIBILITY, src.SEARCH_VISIBILITY),
            li.ORIGIN_SYSTEM = COALESCE(li.ORIGIN_SYSTEM, 'ORACLE_NATIVE'),
            li.ORIGIN_COLLECTION = COALESCE(li.ORIGIN_COLLECTION, 'TOMEHUB_CONTENT_AGG'),
            li.SYNC_RUN_ID = COALESCE(li.SYNC_RUN_ID, :p_run_id),
            li.UPDATED_AT = COALESCE(li.UPDATED_AT, src.UPDATED_AT_SRC)
"""

new_update_stmt = """
        UPDATE SET
            li.ITEM_TYPE = COALESCE(li.ITEM_TYPE, src.ITEM_TYPE),
            li.TITLE = COALESCE(li.TITLE, src.TITLE),
            li.AUTHOR = COALESCE(li.AUTHOR, src.AUTHOR),
            li.PUBLISHER = COALESCE(li.PUBLISHER, src.PUBLISHER),
            li.PUBLICATION_YEAR = COALESCE(li.PUBLICATION_YEAR, src.PUBLICATION_YEAR),
            li.ISBN = COALESCE(li.ISBN, src.ISBN),
            li.SOURCE_URL = COALESCE(li.SOURCE_URL, src.SOURCE_URL),
            li.PAGE_COUNT = COALESCE(li.PAGE_COUNT, src.PAGE_COUNT),
            li.COVER_URL = COALESCE(li.COVER_URL, src.COVER_URL),
            li.SUMMARY_TEXT = COALESCE(li.SUMMARY_TEXT, src.SUMMARY_TEXT),
            li.GENERAL_NOTES = COALESCE(li.GENERAL_NOTES, src.GENERAL_NOTES),
            li.TAGS_JSON = COALESCE(li.TAGS_JSON, src.TAGS_JSON),
            li.CATEGORY_JSON = COALESCE(li.CATEGORY_JSON, src.CATEGORY_JSON),
            li.READING_STATUS = COALESCE(li.READING_STATUS, src.READING_STATUS),
            li.STATUS = COALESCE(li.STATUS, src.STATUS),
            li.IS_FAVORITE = COALESCE(li.IS_FAVORITE, src.IS_FAVORITE),
            li.PERSONAL_NOTE_CATEGORY = COALESCE(li.PERSONAL_NOTE_CATEGORY, src.PERSONAL_NOTE_CATEGORY),
            li.SEARCH_VISIBILITY = COALESCE(li.SEARCH_VISIBILITY, src.SEARCH_VISIBILITY),
            li.ORIGIN_SYSTEM = COALESCE(li.ORIGIN_SYSTEM, 'ORACLE_NATIVE'),
            li.ORIGIN_COLLECTION = COALESCE(li.ORIGIN_COLLECTION, 'TOMEHUB_CONTENT_AGG'),
            li.SYNC_RUN_ID = COALESCE(li.SYNC_RUN_ID, :p_run_id),
            li.UPDATED_AT = CURRENT_TIMESTAMP
"""

text = text.replace(old_update_stmt.strip(), new_update_stmt.strip())

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Patched apply_phase2_backfill.py")
