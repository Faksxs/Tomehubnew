-- Phase X: Chat Title Lock
-- Prevent repeated title generation attempts

ALTER TABLE TOMEHUB_CHAT_SESSIONS
ADD (TITLE_LOCKED NUMBER(1) DEFAULT 0);

CREATE INDEX idx_chat_title_locked ON TOMEHUB_CHAT_SESSIONS(TITLE_LOCKED);
