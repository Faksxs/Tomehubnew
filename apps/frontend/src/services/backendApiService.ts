import { normalizeHighlightType } from '../lib/highlightType';
import { API_BASE_URL, fetchWithAuth } from './apiClient';
/**
 * TomeHub Backend API Service
 * Connects React frontend to Flask backend for RAG search and document ingestion
 */

const normalizeSourceTypeForBackend = (type: string): string => {
    const normalized = (type || '').trim().toUpperCase();
    if (normalized === 'NOTE' || normalized === 'PERSONAL') return 'PERSONAL_NOTE';
    if (normalized === 'NOTES') return 'HIGHLIGHT';
    if (normalized === 'INSIGHTS') return 'INSIGHT';
    return normalized || 'PERSONAL_NOTE';
};

export interface SearchRequest {
    question: string;
    firebase_uid: string;
    mode?: 'STANDARD' | 'EXPLORER';
    book_id?: string;
    context_book_id?: string;
    resource_type?: 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE' | 'ALL_NOTES' | null;
    scope_mode?: 'AUTO' | 'BOOK_FIRST' | 'HIGHLIGHT_FIRST' | 'GLOBAL';
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
    resolved_book_id?: string | null;
    matched_by_title?: boolean;
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
    context_book_id?: string | null;
    resource_type?: 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE' | 'ALL_NOTES' | null;
    scope_mode?: 'AUTO' | 'BOOK_FIRST' | 'HIGHLIGHT_FIRST' | 'GLOBAL';
    mode?: 'STANDARD' | 'EXPLORER';
    limit?: number;
    offset?: number;
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

export interface EpistemicDistributionRow {
    book_id: string;
    level_a: number;
    level_b: number;
    level_c: number;
    total_chunks: number;
    ratio_a: number;
    ratio_b: number;
    ratio_c: number;
    updated_at: string | null;
}

export interface EpistemicDistributionResponse {
    items: EpistemicDistributionRow[];
    count: number;
    error?: string;
}

export interface RealtimeEvent {
    event_type: 'book.updated' | 'highlight.synced' | 'note.synced' | string;
    book_id: string;
    title?: string;
    source_type?: string;
    updated_at_ms: number;
}

export interface RealtimePollResponse {
    success: boolean;
    server_time_ms: number;
    events: RealtimeEvent[];
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
    bookId?: string,
    scopeMode: 'AUTO' | 'BOOK_FIRST' | 'HIGHLIGHT_FIRST' | 'GLOBAL' = 'AUTO',
    contextBookId?: string
): Promise<SearchResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to search');
    }

    const response = await fetchWithAuth(`${API_BASE_URL}/api/search`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            question,
            firebase_uid: firebaseUid,
            mode,
            book_id: bookId,
            context_book_id: contextBookId,
            scope_mode: scopeMode
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
    resourceType: 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE' | null = null,
    limit: number = 20,
    scopeMode: 'AUTO' | 'BOOK_FIRST' | 'HIGHLIGHT_FIRST' | 'GLOBAL' = 'AUTO',
    bookId: string | null = null,
    contextBookId: string | null = null
): Promise<ChatResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to chat');
    }

    const response = await fetchWithAuth(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            message,
            firebase_uid: firebaseUid,
            session_id: sessionId,
            mode,
            resource_type: resourceType,
            scope_mode: scopeMode,
            book_id: bookId,
            context_book_id: contextBookId,
            limit
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

    const response = await fetchWithAuth(`${API_BASE_URL}/api/ingest`, {
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
    const response = await fetchWithAuth(`${API_BASE_URL}/api/feedback`, {
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
    const response = await fetchWithAuth(
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
    firebaseUid: string,
    title?: string
): Promise<IngestionStatusResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated to fetch ingestion status');
    }

    const params = new URLSearchParams();
    params.set('firebase_uid', firebaseUid);
    if (title && title.trim()) {
        params.set('title', title.trim());
    }

    const response = await fetchWithAuth(
        `${API_BASE_URL}/api/books/${encodeURIComponent(bookId)}/ingestion-status?${params.toString()}`,
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

    const response = await fetchWithAuth(`${API_BASE_URL}/api/extract-metadata`, {
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
    const normalizedType = normalizeSourceTypeForBackend(type);
    const response = await fetchWithAuth(`${API_BASE_URL}/api/add-item`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            text,
            title,
            author,
            type: normalizedType,
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
    const normalizedItems = items.map((item) => ({
        ...item,
        type: normalizeSourceTypeForBackend(item.type),
    }));
    const response = await fetchWithAuth(`${API_BASE_URL}/api/migrate_bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            items: normalizedItems,
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
        type?: 'highlight' | 'insight' | 'note';
        comment?: string;
        pageNumber?: number;
        tags?: string[];
        createdAt?: number;
    }>
): Promise<{ success: boolean; deleted: number; inserted: number }> {
    const normalizedHighlights = highlights.map((highlight) => ({
        ...highlight,
        type: normalizeHighlightType(highlight.type),
    }));
    const response = await fetchWithAuth(`${API_BASE_URL}/api/books/${encodeURIComponent(bookId)}/sync-highlights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            firebase_uid: firebaseUid,
            title,
            author,
            highlights: normalizedHighlights
        })
    });

    if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || 'Failed to sync highlights');
    }
    return response.json();
}

export interface SyncPersonalNoteRequest {
    firebase_uid: string;
    title: string;
    author: string;
    content?: string;
    tags?: string[];
    category?: 'PRIVATE' | 'DAILY' | 'IDEAS';
    delete_only?: boolean;
}

export async function syncPersonalNote(
    firebaseUid: string,
    noteId: string,
    payload: Omit<SyncPersonalNoteRequest, 'firebase_uid'>
): Promise<{ success: boolean; deleted: number; inserted: number }> {
    const response = await fetchWithAuth(`${API_BASE_URL}/api/notes/${encodeURIComponent(noteId)}/sync-personal-note`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            firebase_uid: firebaseUid,
            ...payload,
        } as SyncPersonalNoteRequest),
    });

    if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || 'Failed to sync personal note');
    }
    return response.json();
}

export async function purgeResourceContent(
    firebaseUid: string,
    bookId: string
): Promise<{ success: boolean; deleted: number; aux_deleted?: Record<string, number> }> {
    const response = await fetchWithAuth(`${API_BASE_URL}/api/resources/${encodeURIComponent(bookId)}/purge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            firebase_uid: firebaseUid,
        }),
    });

    if (!response.ok) {
        throw new Error('Failed to purge resource content');
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

    const response = await fetchWithAuth(url.toString(), {
        headers: {
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

    const response = await fetchWithAuth(url.toString(), {
        headers: {
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
    const response = await fetchWithAuth(`${API_BASE_URL}/api/analytics/compare?firebase_uid=${encodeURIComponent(firebaseUid)}`, {
        method: 'POST',
        headers: {
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

    const response = await fetchWithAuth(url.toString(), {
        headers: {
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch ingested books');
    }
    return response.json();
}

export async function getEpistemicDistribution(
    firebaseUid: string,
    bookId?: string,
    limit: number = 250
): Promise<EpistemicDistributionResponse> {
    const url = new URL(`${API_BASE_URL}/api/analytics/epistemic-distribution`);
    url.searchParams.append('firebase_uid', firebaseUid);
    url.searchParams.append('limit', String(limit));
    if (bookId) {
        url.searchParams.append('book_id', bookId);
    }

    const response = await fetchWithAuth(url.toString(), {
        headers: {
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch epistemic distribution');
    }
    return response.json();
}

export async function pollRealtimeEvents(
    firebaseUid: string,
    sinceMs: number = 0,
    limit: number = 100
): Promise<RealtimePollResponse> {
    if (!firebaseUid) {
        throw new Error('User must be authenticated for realtime polling');
    }
    const url = new URL(`${API_BASE_URL}/api/realtime/poll`);
    url.searchParams.append('firebase_uid', firebaseUid);
    url.searchParams.append('since_ms', String(Math.max(0, Math.floor(sinceMs || 0))));
    url.searchParams.append('limit', String(Math.min(300, Math.max(1, Math.floor(limit || 100)))));

    const response = await fetchWithAuth(url.toString(), {
        headers: { 'Content-Type': 'application/json' }
    });
    if (response.status === 404) {
        throw new Error('REALTIME_ENDPOINT_NOT_FOUND');
    }
    if (!response.ok) {
        let message = 'Realtime polling failed';
        try {
            const error: ApiError = await response.json();
            message = error.details || error.error || message;
        } catch {
            // Keep fallback message when response is not JSON.
        }
        throw new Error(message);
    }
    return response.json();
}

/**
 * Scan an ISBN barcode from a photo using server-side pyzbar decoding.
 * @param file - Image file containing the barcode
 * @returns The decoded ISBN string
 * @throws Error('NO_BARCODE_FOUND') if no barcode detected, or other error message
 */
export async function scanIsbnFromPhoto(file: File): Promise<string> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetchWithAuth(`${API_BASE_URL}/api/scan-isbn`, {
        method: 'POST',
        body: formData,
    });

    if (response.status === 404) {
        throw new Error('NO_BARCODE_FOUND');
    }

    if (!response.ok) {
        const error: ApiError = await response.json().catch(() => ({ error: 'Scan failed' }));
        throw new Error(error.details || error.error || 'Barcode scan failed');
    }

    const data = await response.json();
    return data.isbn as string;
}
