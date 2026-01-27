
-- TOMEHUB SEARCH ANALYTICS SCHEMA

-- 1. Search Logs: Captures the "Decision Snapshot" for every query
CREATE TABLE TOMEHUB_SEARCH_LOGS (
    ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    FIREBASE_UID VARCHAR2(100) NOT NULL,
    SESSION_ID VARCHAR2(100), -- Optional session tracking
    QUERY_TEXT CLOB,
    INTENT VARCHAR2(50), -- DIRECT, NARRATIVE, SYNTHESIS
    RRF_WEIGHTS VARCHAR2(100), -- e.g. "vec:60, bm25:60, graph:60"
    TOP_RESULT_ID NUMBER,
    TOP_RESULT_SCORE NUMBER,
    EXECUTION_TIME_MS NUMBER,
    TIMESTAMP TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    STRATEGY_DETAILS CLOB -- JSON blob of debug info (e.g. which strategy found what)
);

-- Index for fast lookup by user
CREATE INDEX idx_search_logs_uid ON TOMEHUB_SEARCH_LOGS(FIREBASE_UID);
CREATE INDEX idx_search_logs_time ON TOMEHUB_SEARCH_LOGS(TIMESTAMP);

-- 2. Feedback: Captures user judgment (linked to search log)
-- We check if table exists first (it might from previous steps), if so we alter it.
-- But since this is a schema file, we'll write the CREATE usually. 
-- The migration script will handle "exists" check.

CREATE TABLE TOMEHUB_FEEDBACK (
    ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    FIREBASE_UID VARCHAR2(100) NOT NULL,
    SEARCH_LOG_ID NUMBER, -- Foreign Key to Search Log
    QUERY_TEXT CLOB,
    GENERATED_ANSWER CLOB,
    RATING NUMBER(1), -- 1 (Up) or 0 (Down)
    FEEDBACK_TEXT CLOB,
    CONTEXT_BOOK_ID VARCHAR2(100),
    TIMESTAMP TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_search_log FOREIGN KEY (SEARCH_LOG_ID) REFERENCES TOMEHUB_SEARCH_LOGS(ID)
);
