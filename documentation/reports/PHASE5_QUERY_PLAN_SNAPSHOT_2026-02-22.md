# Phase 5 Query Plan Snapshot (2026-02-22)

- Generated: `2026-02-22 22:58:53 UTC`
- Sample uid: `vpq1p0UzcCSLAh1d18WgZZWPBE63`
- Sample book_id: `1770687774840`
- SEARCH_LOGS time column: `TIMESTAMP`

## `content_uid_book_source_type`

```sql
SELECT ID
                    FROM TOMEHUB_CONTENT
                    WHERE FIREBASE_UID = :p_uid
                      AND BOOK_ID = :p_book_id
                      AND SOURCE_TYPE = :p_source
                    FETCH FIRST 100 ROWS ONLY
```

```text
Plan hash value: 1289310240
 
--------------------------------------------------------------------------
| Id  | Operation                                | Name                  |
--------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |
|*  1 |  COUNT STOPKEY                           |                       |
|   2 |   PX COORDINATOR                         |                       |
|   3 |    PX SEND QC (RANDOM)                   | :TQ10001              |
|   4 |     BUFFER SORT                          |                       |
|*  5 |      COUNT STOPKEY                       |                       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TOMEHUB_CONTENT       |
|   7 |        PX RECEIVE                        |                       |
|   8 |         PX SEND HASH (BLOCK ADDRESS)     | :TQ10000              |
|   9 |          PX SELECTOR                     |                       |
|* 10 |           INDEX RANGE SCAN               | IDX_CONT_UID_BOOK_SRC |
--------------------------------------------------------------------------
 
Query Block Name / Object Alias (identified by operation id):
-------------------------------------------------------------
 
   1 - SEL$58A6D7F6
   6 - SEL$58A6D7F6 / "TOMEHUB_CONTENT"@"SEL$1"
  10 - SEL$58A6D7F6 / "TOMEHUB_CONTENT"@"SEL$1"
 
Predicate Information (identified by operation id):
---------------------------------------------------
 
   1 - filter(ROWNUM<=100)
   5 - filter(ROWNUM<=100)
  10 - access("FIREBASE_UID"=:P_UID AND "BOOK_ID"=:P_BOOK_ID AND 
              "SOURCE_TYPE"=:P_SOURCE)
 
Note
-----
   - automatic DOP: Computed Degree of Parallelism is 2 because of no expensive parallel operation
```

## `content_uid_book_content_type`

```sql
SELECT ID
                    FROM TOMEHUB_CONTENT
                    WHERE FIREBASE_UID = :p_uid
                      AND BOOK_ID = :p_book_id
                      AND CONTENT_TYPE = :p_content_type
                    FETCH FIRST 100 ROWS ONLY
```

```text
Plan hash value: 2556300384
 
----------------------------------------------------------------------------
| Id  | Operation                                | Name                    |
----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                         |
|*  1 |  COUNT STOPKEY                           |                         |
|   2 |   PX COORDINATOR                         |                         |
|   3 |    PX SEND QC (RANDOM)                   | :TQ10001                |
|   4 |     BUFFER SORT                          |                         |
|*  5 |      COUNT STOPKEY                       |                         |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TOMEHUB_CONTENT         |
|   7 |        PX RECEIVE                        |                         |
|   8 |         PX SEND HASH (BLOCK ADDRESS)     | :TQ10000                |
|   9 |          PX SELECTOR                     |                         |
|* 10 |           INDEX RANGE SCAN               | IDX_CONT_UID_BOOK_CTYPE |
----------------------------------------------------------------------------
 
Query Block Name / Object Alias (identified by operation id):
-------------------------------------------------------------
 
   1 - SEL$58A6D7F6
   6 - SEL$58A6D7F6 / "TOMEHUB_CONTENT"@"SEL$1"
  10 - SEL$58A6D7F6 / "TOMEHUB_CONTENT"@"SEL$1"
 
Predicate Information (identified by operation id):
---------------------------------------------------
 
   1 - filter(ROWNUM<=100)
   5 - filter(ROWNUM<=100)
  10 - access("FIREBASE_UID"=:P_UID AND "BOOK_ID"=:P_BOOK_ID AND 
              "CONTENT_TYPE"=:P_CONTENT_TYPE)
 
Note
-----
   - automatic DOP: Computed Degree of Parallelism is 2 because of no expensive parallel operation
```

## `ingested_files_uid_book`

```sql
SELECT ID, STATUS, CHUNK_COUNT
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE FIREBASE_UID = :p_uid
                      AND BOOK_ID = :p_book_id
```

```text
Plan hash value: 310928899
 
--------------------------------------------------------------
| Id  | Operation                   | Name                   |
--------------------------------------------------------------
|   0 | SELECT STATEMENT            |                        |
|   1 |  TABLE ACCESS BY INDEX ROWID| TOMEHUB_INGESTED_FILES |
|*  2 |   INDEX UNIQUE SCAN         | UQ_INGEST_BOOK_UID     |
--------------------------------------------------------------
 
Query Block Name / Object Alias (identified by operation id):
-------------------------------------------------------------
 
   1 - SEL$1 / "TOMEHUB_INGESTED_FILES"@"SEL$1"
   2 - SEL$1 / "TOMEHUB_INGESTED_FILES"@"SEL$1"
 
Predicate Information (identified by operation id):
---------------------------------------------------
 
   2 - access("BOOK_ID"=:P_BOOK_ID AND "FIREBASE_UID"=:P_UID)
 
Note
-----
   - automatic DOP: Computed Degree of Parallelism is 1 because of no expensive parallel operation
```

## `ingestion_status_view_uid`

```sql
SELECT ITEM_ID, INGESTION_STATUS, CHUNK_COUNT
                    FROM VW_TOMEHUB_INGESTION_STATUS_BY_ITEM
                    WHERE FIREBASE_UID = :p_uid
                    FETCH FIRST 100 ROWS ONLY
```

```text
Plan hash value: 1616411059
 
-------------------------------------------------------------------------
| Id  | Operation                              | Name                   |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                       |                        |
|*  1 |  COUNT STOPKEY                         |                        |
|*  2 |   VIEW                                 |                        |
|*  3 |    WINDOW SORT PUSHED RANK             |                        |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED| TOMEHUB_INGESTED_FILES |
|*  5 |      INDEX RANGE SCAN                  | IDX_INGEST_UID_BOOK    |
-------------------------------------------------------------------------
 
Query Block Name / Object Alias (identified by operation id):
-------------------------------------------------------------
 
   1 - SEL$FD4820B2
   2 - SEL$3        / "I"@"SEL$2"
   3 - SEL$3       
   4 - SEL$3        / "F"@"SEL$3"
   5 - SEL$3        / "F"@"SEL$3"
 
Predicate Information (identified by operation id):
---------------------------------------------------
 
   1 - filter(ROWNUM<=100)
   2 - filter("I"."RN"=1)
   3 - filter(ROW_NUMBER() OVER ( PARTITION BY 
              "F"."FIREBASE_UID","F"."BOOK_ID" ORDER BY "F"."UPDATED_AT" DESC  NULLS 
              LAST,"F"."ID" DESC  NULLS LAST)<=1)
   5 - access("F"."FIREBASE_UID"=:P_UID)
 
Note
-----
   - automatic DOP: Computed Degree of Parallelism is 1 because of no expensive parallel operation
```

## `search_logs_recent_window`

```sql
SELECT ID, "TIMESTAMP"
                        FROM TOMEHUB_SEARCH_LOGS
                        WHERE "TIMESTAMP" >= SYSTIMESTAMP - INTERVAL '30' DAY
                        ORDER BY "TIMESTAMP" DESC
                        FETCH FIRST 200 ROWS ONLY
```

```text
Plan hash value: 3849672434
 
------------------------------------------------------------
| Id  | Operation                    | Name                |
------------------------------------------------------------
|   0 | SELECT STATEMENT             |                     |
|*  1 |  COUNT STOPKEY               |                     |
|   2 |   PX COORDINATOR             |                     |
|   3 |    PX SEND QC (ORDER)        | :TQ10001            |
|   4 |     VIEW                     |                     |
|*  5 |      SORT ORDER BY STOPKEY   |                     |
|   6 |       PX RECEIVE             |                     |
|   7 |        PX SEND RANGE         | :TQ10000            |
|*  8 |         SORT ORDER BY STOPKEY|                     |
|   9 |          PX BLOCK ITERATOR   |                     |
|* 10 |           TABLE ACCESS FULL  | TOMEHUB_SEARCH_LOGS |
------------------------------------------------------------
 
Query Block Name / Object Alias (identified by operation id):
-------------------------------------------------------------
 
   1 - SEL$2
   4 - SEL$1 / "from$_subquery$_002"@"SEL$2"
   5 - SEL$1
  10 - SEL$1 / "TOMEHUB_SEARCH_LOGS"@"SEL$1"
 
Predicate Information (identified by operation id):
---------------------------------------------------
 
   1 - filter(ROWNUM<=200)
   5 - filter(ROWNUM<=200)
   8 - filter(ROWNUM<=200)
  10 - filter(SYS_EXTRACT_UTC(INTERNAL_FUNCTION("TIMESTAMP"))>=SYS_EXTRA
              CT_UTC(SYSTIMESTAMP(6)-INTERVAL'+30 00:00:00' DAY(2) TO SECOND(0)))
 
Note
-----
   - automatic DOP: Computed Degree of Parallelism is 2
```

