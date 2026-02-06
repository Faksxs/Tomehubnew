/**
 * TomeHub Backend API Service
 * Connects React frontend to Flask backend for RAG search and document ingestion
 */

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:5000'
    : 'https://api.tomehub.nl'; // ✅ Real Production Endpoint


export interface SearchRequest {
    question: string;
    firebase_uid: string;
    mode?: 'STANDARD' | 'EXPLORER';
    book_id?: string;
}

export interface SearchResponse {
    answer: string;
    sources: Array<{
        title: string;
        page_number: number;
        similarity_score: number;
        comment?: string;
    }>;
    timestamp: string;
    metadata?: {
        search_log_id?: number;
        model_name?: string;
        status?: string;
        analytics?: any;
    };
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

export interface IngestionStatusResponse {
    status: 'NOT_FOUND' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
    file_name: string | null;
    chunk_count: number | null;
    embedding_count: number | null;
    updated_at: string | null;
}

export interface ApiError {
    error: string;
    details?: string;
}

export interface ReportSearchResponse {
    topic: string;
    count: number;
    results: Array<{
        book_id: string;
        summary_text: string;
        key_topics: string;
        entities: string;
        created_at: string | null;
        updated_at: string | null;
    }>;
}

export interface FeedbackRequest {
    firebase_uid: string;
    query: string;
    answer: string;
    rating: 1 | 0;
    comment?: string;
    search_log_id?: number;
    book_id?: string;
}

// Chat API types (for Explorer Mode with conversational memory)
export interface ChatRequest {
    message: string;
    firebase_uid: string;
    session_id?: number | null;
    book_id?: string | null;
    resource_type?: 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE' | null;
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

export interface ConcordanceResponse {
    book_id: string;
    term: string;
    contexts: Array<{
        chunk_id: string;
        page_number: number;
        snippet: string;
        keyword_found: string;
    }>;
    limit: number;
    offset: number;
    count: number;
}

export interface DistributionResponse {
    book_id: string;
    term: string;
    distribution: Array<{
        page_number: number;
        count: number;
    }>;
}

export interface ComparisonResponse {
    term: string;
    comparison: Array<{
        book_id: string;
        title: string;
        count: number;
    }>;
}

export interface IngestedBooksResponse {
    book_ids: string[];
    count: number;
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
    mode: 'STANDARD' | 'EXPLORER' = 'STANDARD',
    bookId?: string
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
            mode,
            book_id: bookId
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
    mode: 'STANDARD' | 'EXPLORER' = 'EXPLORER',
    resourceType: 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE' | null = null
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
            mode,
            resource_type: resourceType
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
    bookId?: string,
    tags?: string
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
    if (tags) {
        formData.append('tags', tags);
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
 * Submit feedback for a search response
 */
export async function submitFeedback(request: FeedbackRequest): Promise<{ success: boolean }> {
    const response = await fetch(`${API_BASE_URL}/api/feedback`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Feedback failed');
    }

    return response.json();
}

/**
 * Search file reports by key topic (JSON index)
 */
export async function searchReportsByTopic(
    topic: string,
    firebaseUid: string,
    limit: number = 20
): Promise<ReportSearchResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to search reports');
    }
    const response = await fetch(
        `${API_BASE_URL}/api/reports/search?topic=${encodeURIComponent(topic)}&limit=${encodeURIComponent(limit)}&firebase_uid=${encodeURIComponent(firebaseUid)}`,
        {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-Firebase-UID': firebaseUid
            }
        }
    );
    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Report search failed');
    }
    return response.json();
}

/**
 * Fetch ingestion status for a book
 * @param bookId - Firestore book id (mapped to DB book_id)
 * @param firebaseUid - Authenticated user's Firebase UID
 */
export async function getIngestionStatus(
    bookId: string,
    firebaseUid: string
): Promise<IngestionStatusResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to fetch ingestion status');
    }

    const response = await fetch(
        `${API_BASE_URL}/api/books/${encodeURIComponent(bookId)}/ingestion-status?firebase_uid=${encodeURIComponent(firebaseUid)}`,
        {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-Firebase-UID': firebaseUid
            }
        }
    );

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Failed to fetch ingestion status');
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
    firebaseUid: string,
    options?: {
        book_id?: string;
        page_number?: number;
        chunk_type?: string;
        chunk_index?: number;
        comment?: string;
        tags?: string[];
    }
): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${API_BASE_URL}/api/add-item`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            text,
            title,
            author,
            type,
            firebase_uid: firebaseUid,
            ...options
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
    items: Array<{
        text: string;
        title: string;
        author: string;
        type: string;
        book_id?: string;
        page_number?: number;
        chunk_type?: string;
        chunk_index?: number;
        comment?: string;
        tags?: string[];
    }>,
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
 * Sync highlights/insights for a specific book (replace existing)
 */
export async function syncHighlights(
    firebaseUid: string,
    bookId: string,
    title: string,
    author: string,
    highlights: Array<{
        id?: string;
        text: string;
        type?: 'highlight' | 'note';
        comment?: string;
        pageNumber?: number;
        tags?: string[];
        createdAt?: number;
    }>
): Promise<{ success: boolean; deleted: number; inserted: number }> {
    const response = await fetch(`${API_BASE_URL}/api/books/${encodeURIComponent(bookId)}/sync-highlights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            firebase_uid: firebaseUid,
            title,
            author,
            highlights
        })
    });

    if (!response.ok) {
        throw new Error('Failed to sync highlights');
    }
    return response.json();
}

/**
 * Get paginated concordance (KWIC) for a term in a book
 */
export async function getConcordance(
    firebaseUid: string,
    bookId: string,
    term: string,
    limit: number = 50,
    offset: number = 0
): Promise<ConcordanceResponse> {
    const url = new URL(`${API_BASE_URL}/api/analytics/concordance`);
    url.searchParams.append('book_id', bookId);
    url.searchParams.append('term', term);
    url.searchParams.append('limit', limit.toString());
    url.searchParams.append('offset', offset.toString());
    url.searchParams.append('firebase_uid', firebaseUid);

    const response = await fetch(url.toString(), {
        headers: {
            'Authorization': `Bearer ${firebaseUid}`, // Assuming the backend verify_firebase_token handles this dependency
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch concordance');
    }
    return response.json();
}

/**
 * Get keyword distribution across pages
 */
export async function getDistribution(
    firebaseUid: string,
    bookId: string,
    term: string
): Promise<DistributionResponse> {
    const url = new URL(`${API_BASE_URL}/api/analytics/distribution`);
    url.searchParams.append('book_id', bookId);
    url.searchParams.append('term', term);
    url.searchParams.append('firebase_uid', firebaseUid);

    const response = await fetch(url.toString(), {
        headers: {
            'Authorization': `Bearer ${firebaseUid}`,
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch distribution');
    }
    return response.json();
}

/**
 * Get comparative stats for multiple books
 */
export async function getComparativeStats(
    firebaseUid: string,
    targetBookIds: string[],
    term: string
): Promise<ComparisonResponse> {
    const response = await fetch(`${API_BASE_URL}/api/analytics/compare?firebase_uid=${encodeURIComponent(firebaseUid)}`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${firebaseUid}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            firebase_uid: firebaseUid,
            target_book_ids: targetBookIds,
            term: term
        })
    });

    if (!response.ok) {
        throw new Error('Failed to fetch comparison');
    }
    return response.json();
}

/**
 * Get list of ingested PDF book IDs
 */
export async function getIngestedBookIds(
    firebaseUid: string
): Promise<IngestedBooksResponse> {
    const url = new URL(`${API_BASE_URL}/api/analytics/ingested-books`);
    url.searchParams.append('firebase_uid', firebaseUid);

    const response = await fetch(url.toString(), {
        headers: {
            'Authorization': `Bearer ${firebaseUid}`,
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch ingested books');
    }
    return response.json();
}

