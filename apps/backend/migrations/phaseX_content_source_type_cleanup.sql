-- Normalize legacy source_type values

BEGIN
    UPDATE TOMEHUB_CONTENT
    SET source_type = 'HIGHLIGHT'
    WHERE source_type = 'NOTES';

    UPDATE TOMEHUB_CONTENT
    SET source_type = 'PERSONAL_NOTE'
    WHERE source_type = 'NOTE';
END;
/
