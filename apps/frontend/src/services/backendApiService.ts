/**
 * TomeHub Backend API Service
 * Connects React frontend to Flask backend for RAG search and document ingestion
 */

const API_BASE_URL = 'http://localhost:5000'; // Updated for local testing

export interface SearchRequest {
    question: string;
    firebase_uid: string;
    mode?: 'STANDARD' | 'EXPLORER';
}

export interface SearchResponse {
    answer: string;
    sources: Array<{
        title: string;
        page_number: number;
        similarity_score: number;
    }>;
    timestamp: string;
}


export interface IngestRequest {
    pdf_path: string;
    title: string;
    author: string;
    firebase_uid: string;
}

export interface IngestResponse {
    success: boolean;
    message: string;
    timestamp: string;
}

export interface ApiError {
    error: string;
    details?: string;
}

// Chat API types (for Explorer Mode with conversational memory)
export interface ChatRequest {
    message: string;
    firebase_uid: string;
    session_id?: number | null;
    book_id?: string | null;
    mode?: 'STANDARD' | 'EXPLORER';
}

export interface ChatResponse {
    answer: string;
    session_id: number;
    sources: Array<{
        id?: number;
        title: string;
        score: number;
        page_number: number;
        content?: string;
    }>;
    timestamp: string;
    conversation_state?: {
        active_topic?: string;
        assumptions?: Array<{ id: number; text: string; confidence: string }>;
        open_questions?: string[];
        established_facts?: Array<{ text: string; source: string }>;
    };
    thinking_history?: Array<{
        attempt: number;
        answer: string;
        evaluation: {
            verdict: string;
            overall_score: number;
            explanation: string;
        };
        latency: number;
    }>;
}

/**
 * Check if backend API is online
 */
export async function checkApiHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${API_BASE_URL}/`);
        const data = await response.json();
        return data.status === 'online';
    } catch (error) {
        console.error('API health check failed:', error);
        return false;
    }
}

/**
 * Search library using RAG
 * @param question - The user's question
 * @param firebaseUid - The authenticated user's Firebase UID
 * @param mode - Search mode (STANDARD or EXPLORER)
 */
export async function searchLibrary(
    question: string,
    firebaseUid: string,
    mode: 'STANDARD' | 'EXPLORER' = 'STANDARD'
): Promise<SearchResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to search');
    }

    const response = await fetch(`${API_BASE_URL}/api/search`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            question,
            firebase_uid: firebaseUid,
            mode
        } as SearchRequest),
    });

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Search failed');
    }

    return response.json();
}

/**
 * Send a chat message with conversational memory (for Explorer Mode)
 * @param message - The user's message
 * @param firebaseUid - The authenticated user's Firebase UID
 * @param sessionId - Optional session ID for continuing a conversation
 * @param mode - Chat mode (EXPLORER for deep conversational analysis)
 */
export async function sendChatMessage(
    message: string,
    firebaseUid: string,
    sessionId: number | null = null,
    mode: 'STANDARD' | 'EXPLORER' = 'EXPLORER'
): Promise<ChatResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to chat');
    }

    const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            message,
            firebase_uid: firebaseUid,
            session_id: sessionId,
            mode
        } as ChatRequest),
    });

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Chat failed');
    }

    return response.json();
}

/**
 * Ingest a PDF file into the library
 * @param file - The PDF file object
 * @param title - Book title
 * @param author - Book author
 * @param firebaseUid - The authenticated user's Firebase UID
 */
export async function ingestDocument(
    file: File,
    title: string,
    author: string,
    firebaseUid: string,
    bookId?: string
): Promise<IngestResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to ingest documents');
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    formData.append('author', author);
    formData.append('firebase_uid', firebaseUid);
    if (bookId) {
        formData.append('book_id', bookId);
    }

    const response = await fetch(`${API_BASE_URL}/api/ingest`, {
        method: 'POST',
        body: formData, // No Content-Type header needed, fetch sets it for FormData
    });

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Ingestion failed');
    }

    return response.json();
}

/**
 * Extract metadata from a PDF file
 * @param file - The PDF file object
 */
export async function extractMetadata(file: File): Promise<{
    title: string | null;
    author: string | null;
    page_count: number;
}> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/extract-metadata`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.error || 'Metadata extraction failed');
    }

    return response.json();
}

/**
 * Add a text item (note or book metadata) to the AI library
 */
export async function addTextItem(
    text: string,
    title: string,
    author: string,
    type: string,
    firebaseUid: string
): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${API_BASE_URL}/api/add-item`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            text,
            title,
            author,
            type,
            firebase_uid: firebaseUid
        })
    });

    if (!response.ok) {
        throw new Error('Failed to add item');
    }

    return response.json();
}

/**
 * Bulk migrate items to AI library
 */
export async function migrateBulkItems(
    items: Array<{ text: string, title: string, author: string, type: string }>,
    firebaseUid: string
): Promise<{ success: boolean; processed: number; results: any }> {
    const response = await fetch(`${API_BASE_URL}/api/migrate_bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            items,
            firebase_uid: firebaseUid
        })
    });

    if (!response.ok) {
        throw new Error('Failed to migrate batch');
    }

    return response.json();
}

/**
 * Get list of already ingested books
 */
export async function getIngestedBooks(firebaseUid: string): Promise<{ books: Array<{ title: string, author: string, book_id: string }> }> {
    try {
        const response = await fetch(`${API_BASE_URL}/api/ingested-books?firebase_uid=${firebaseUid}`);
        if (!response.ok) return { books: [] };
        return response.json();
    } catch (error) {
        console.error('Failed to fetch ingested books:', error);
        return { books: [] };
    }
}
