/**
 * Resilient Book Lookup Service with Fallback Strategy
 * 
 * Provides fallback mechanisms when Google Books API fails.
 * Fallback chain: Google Books → OpenLibrary → CrossRef
 */

// Normalized book data structure used across all sources
export interface NormalizedBookData {
    title: string;
    author: string;
    publisher?: string;
    isbn?: string;
    publishedDate?: string;
    summary?: string;
    coverUrl?: string | null;
    tags?: string[];
}

/**
 * Fetch book data from Google Books API
 */
async function fetchFromGoogleBooks(query: string): Promise<NormalizedBookData | null> {
    try {
        const apiUrl = `https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(query)}&maxResults=1`;
        const response = await fetch(apiUrl);

        // Check for specific error codes
        if (!response.ok) {
            if (response.status === 503) {
                console.warn('Google Books API returned 503 (Service Unavailable)');
            }
            return null;
        }

        const data = await response.json();
        const item = data.items?.[0];

        if (!item) return null;

        const volumeInfo = item.volumeInfo || {};

        return {
            title: volumeInfo.title || '',
            author: volumeInfo.authors?.[0] || 'Unknown',
            publisher: volumeInfo.publisher || '',
            isbn: volumeInfo.industryIdentifiers?.[0]?.identifier || '',
            publishedDate: volumeInfo.publishedDate || '',
            summary: volumeInfo.description || '',
            coverUrl: volumeInfo.imageLinks?.thumbnail?.replace(/^http:\/\//i, 'https://').replace('&edge=curl', '') || null,
            tags: volumeInfo.categories || [],
        };
    } catch (error) {
        console.warn('Google Books fetch failed:', error);
        return null;
    }
}

/**
 * Fetch book data from OpenLibrary API
 */
async function fetchFromOpenLibrary(query: string): Promise<NormalizedBookData | null> {
    try {
        const apiUrl = `https://openlibrary.org/search.json?q=${encodeURIComponent(query)}&limit=1`;
        const response = await fetch(apiUrl);

        if (!response.ok) {
            console.warn('OpenLibrary API returned error:', response.status);
            return null;
        }

        const data = await response.json();
        const doc = data.docs?.[0];

        if (!doc) return null;

        return {
            title: doc.title || '',
            author: doc.author_name?.[0] || 'Unknown',
            publisher: doc.publisher?.[0] || '',
            isbn: doc.isbn?.[0] || '',
            publishedDate: doc.first_publish_year?.toString() || '',
            summary: '', // OpenLibrary doesn't provide summaries in search results
            coverUrl: doc.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg` : null,
            tags: doc.subject?.slice(0, 5) || [],
        };
    } catch (error) {
        console.warn('OpenLibrary fetch failed:', error);
        return null;
    }
}

/**
 * Fetch book data from CrossRef API (primarily for academic works)
 */
async function fetchFromCrossRef(query: string): Promise<NormalizedBookData | null> {
    try {
        const apiUrl = `https://api.crossref.org/works?query=${encodeURIComponent(query)}&rows=1`;
        const response = await fetch(apiUrl);

        if (!response.ok) {
            console.warn('CrossRef API returned error:', response.status);
            return null;
        }

        const data = await response.json();
        const item = data.message?.items?.[0];

        if (!item) return null;

        const author = item.author?.[0];
        const authorName = author
            ? `${author.given || ''} ${author.family || ''}`.trim()
            : 'Unknown';

        return {
            title: Array.isArray(item.title) ? item.title[0] : item.title || '',
            author: authorName,
            publisher: item.publisher || '',
            isbn: '', // CrossRef typically doesn't have ISBNs
            publishedDate: item.published?.['date-parts']?.[0]?.[0]?.toString() || '',
            summary: item.abstract || '',
            coverUrl: null, // CrossRef doesn't provide cover images
            tags: item.subject || [],
        };
    } catch (error) {
        console.warn('CrossRef fetch failed:', error);
        return null;
    }
}

/**
 * Main fallback orchestrator - tries multiple sources in order
 * 
 * @param title - Book title
 * @param author - Book author (optional)
 * @param isbn - Book ISBN (optional)
 * @returns Normalized book data or null if all sources fail
 */
export async function fetchBookWithFallback(
    title: string,
    author?: string,
    isbn?: string
): Promise<NormalizedBookData | null> {
    // Build query string
    let query = title;
    if (author) query += ` ${author}`;
    if (isbn) query += ` ${isbn}`;

    // Try Google Books first (primary source)
    console.log('Attempting to fetch from Google Books...');
    const googleResult = await fetchFromGoogleBooks(query);
    if (googleResult) {
        console.log('✓ Successfully fetched from Google Books');
        return googleResult;
    }

    // Fallback to OpenLibrary
    console.warn('Google Books failed, trying OpenLibrary...');
    const openLibraryResult = await fetchFromOpenLibrary(query);
    if (openLibraryResult) {
        console.log('✓ Successfully fetched from OpenLibrary (fallback)');
        return openLibraryResult;
    }

    // Fallback to CrossRef (last resort, best for academic works)
    console.warn('OpenLibrary failed, trying CrossRef...');
    const crossRefResult = await fetchFromCrossRef(query);
    if (crossRefResult) {
        console.log('✓ Successfully fetched from CrossRef (fallback)');
        return crossRefResult;
    }

    // All sources failed
    console.error('All book lookup sources failed for query:', query);
    return null;
}

/**
 * Fetch cover image with fallback strategy
 * Specifically optimized for cover image lookup
 */
export async function fetchCoverWithFallback(
    title: string,
    author?: string,
    isbn?: string
): Promise<string | null> {
    // Try ISBN-based lookup first if available
    if (isbn) {
        const cleanIsbn = isbn.replace(/[^0-9X]/gi, '');

        // Try OpenLibrary ISBN lookup (fastest for covers)
        try {
            const coverUrl = `https://covers.openlibrary.org/b/isbn/${cleanIsbn}-L.jpg`;
            const response = await fetch(coverUrl, { method: 'HEAD' });
            if (response.ok) {
                console.log('✓ Cover found via OpenLibrary ISBN');
                return coverUrl;
            }
        } catch (e) {
            // Silent fail, continue to other methods
        }
    }

    // Use full fallback chain for cover
    const bookData = await fetchBookWithFallback(title, author, isbn);
    return bookData?.coverUrl || null;
}
