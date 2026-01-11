-- Add book_id column to TOMEHUB_CONTENT table
-- This links content chunks to specific books in the library

ALTER TABLE TOMEHUB_CONTENT 
ADD (book_id VARCHAR2(255));

-- Create an index on book_id for faster filtering during Contextual Retrieval
CREATE INDEX idx_content_book_id ON TOMEHUB_CONTENT(book_id);

-- Verify the change
SELECT column_name, data_type 
FROM user_tab_columns 
WHERE table_name = 'TOMEHUB_CONTENT' AND column_name = 'BOOK_ID';
