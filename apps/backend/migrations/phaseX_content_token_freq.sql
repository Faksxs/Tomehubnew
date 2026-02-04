-- Phase X: Add token frequency JSON for lemma-based analytics
-- Adds TOKEN_FREQ (JSON stored as CLOB) to TOMEHUB_CONTENT

ALTER TABLE TOMEHUB_CONTENT ADD (
    TOKEN_FREQ CLOB
);

COMMENT ON COLUMN TOMEHUB_CONTENT.TOKEN_FREQ IS 'Lemma frequency JSON: {"kitap": 12, "okumak": 3}';

