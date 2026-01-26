-- Add book_id column to TOMEHUB_CONTENT table
-- This links content chunks to specific books in the library

ALTER TABLE TOMEHUB_CONTENT 
ADD (book_id VARCHAR2(255));

-- Create an index on book_id for faster filtering during Contextual Retrieval
CREATE INDEX idx_content_book_id ON TOMEHUB_CONTENT(book_id);

-- Create a composite index on firebase_uid, book_id, and passage_type
-- This optimizes Hybrid RAG queries that filter by user, book, and content type
CREATE INDEX idx_content_user_book_type ON TOMEHUB_CONTENT(firebase_uid, book_id, passage_type);

-- Verify the change
SELECT index_name, column_name, column_position 
FROM user_ind_columns 
WHERE table_name = 'TOMEHUB_CONTENT' 
  AND index_name = 'IDX_CONTENT_USER_BOOK_TYPE'
ORDER BY column_position;
