/**
 * TomeHub Backend API Service
 * Connects React frontend to Flask backend for RAG search and document ingestion
 */

const API_BASE_URL = 'https://143.47.188.242.nip.io';

export interface SearchRequest {
    question: string;
    firebase_uid: string;
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
 */
export async function searchLibrary(
    question: string,
    firebaseUid: string
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
        } as SearchRequest),
    });

    if (!response.ok) {
        const error: ApiError = await response.json();
        throw new Error(error.details || error.error || 'Search failed');
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
