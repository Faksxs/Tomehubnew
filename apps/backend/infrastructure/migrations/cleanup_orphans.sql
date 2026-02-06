
-- Cleanup Orphaned File Reports
-- These reports reference books that do not exist (deleted or phantom)
DELETE FROM TOMEHUB_FILE_REPORTS 
WHERE BOOK_ID IS NOT NULL 
AND BOOK_ID NOT IN (SELECT ID FROM TOMEHUB_BOOKS);

COMMIT;
