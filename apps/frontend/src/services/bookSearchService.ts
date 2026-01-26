import { ItemDraft } from "./geminiService";

// Types
export interface BookItem extends ItemDraft {
    // Inherits from ItemDraft
}

export interface SearchResult {
    results: BookItem[];
    source: 'google-books' | 'open-library' | 'llm-corrected';
    cached: boolean;
}

export interface CorrectedQuery {
    title: string | null;
    author: string | null;
    isbn: string | null;
    standardized_query: string;
    keywords: string[];
    confidence: number;
}

// Caches
const searchCache = new Map<string, SearchResult>();
const queryCache = new Map<string, CorrectedQuery>();

// Helper: Normalize query
function normalizeQuery(query: string): string {
    return query.trim().toLowerCase().replace(/\s+/g, ' ');
}

// Helper: Generate character variants (e.g. ç -> c)
function generateCharacterVariants(text: string): string[] {
    const variants = new Set<string>();
    variants.add(text);

    const map: Record<string, string> = {
        'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
        'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
    };

    let asciiVariant = text;
    for (const [char, repl] of Object.entries(map)) {
        asciiVariant = asciiVariant.replace(new RegExp(char, 'g'), repl);
    }

    if (asciiVariant !== text) {
        variants.add(asciiVariant);
    }

    return Array.from(variants).slice(0, 5);
}

// Helper: Levenshtein distance
function levenshteinDistance(a: string, b: string): number {
    const matrix: number[][] = [];

    for (let i = 0; i <= b.length; i++) {
        matrix[i] = [i];
    }

    for (let j = 0; j <= a.length; j++) {
        matrix[0][j] = j;
    }

    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            if (b.charAt(i - 1) === a.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }

    return matrix[b.length][a.length];
}

// Helper: Similarity score
function similarityScore(query: string, target: string): number {
    const normalizedQuery = normalizeQuery(query);
    const normalizedTarget = normalizeQuery(target);

    if (!normalizedQuery || !normalizedTarget) return 0;
    if (normalizedQuery === normalizedTarget) return 1.0;
    if (normalizedTarget.includes(normalizedQuery)) return 0.9;

    const maxLen = Math.max(normalizedQuery.length, normalizedTarget.length);
    if (maxLen === 0) return 0;

    const distance = levenshteinDistance(normalizedQuery, normalizedTarget);
    return 1 - (distance / maxLen);
}

// Helper: Rank results
function rankResults(query: string, results: BookItem[]): BookItem[] {
    const scored = results.map(result => {
        const titleScore = similarityScore(query, result.title);
        const authorScore = result.author ? similarityScore(query, result.author) : 0;
        const combinedScore = Math.max(titleScore, authorScore * 0.7);
        return { result, score: combinedScore };
    });

    const filtered = scored.filter(item => item.score >= 0.3);
    filtered.sort((a, b) => b.score - a.score);
    return filtered.map(item => item.result);
}

// Helper: Deduplicate
function deduplicateResults(items: BookItem[]): BookItem[] {
    const seen = new Set<string>();
    const unique: BookItem[] = [];

    for (const item of items) {
        const key = `${normalizeQuery(item.title)}|${normalizeQuery(item.author)}`;
        if (!seen.has(key)) {
            seen.add(key);
            unique.push(item);
        }
    }
    return unique;
}

// API: Google Books with OpenLibrary Fallback
async function searchGoogleBooks(query: string): Promise<BookItem[]> {
    try {
        const variants = generateCharacterVariants(query);
        const results: BookItem[] = [];
        let googleBooksWorked = false;

        for (const variant of variants) {
            const apiUrl = `https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(variant)}&maxResults=10`;

            try {
                const response = await fetch(apiUrl);

                // Check for service unavailable or other errors
                if (!response.ok) {
                    if (response.status === 503) {
                        console.warn('Google Books returned 503 (Service Unavailable)');
                    }
                    continue;
                }

                const data = await response.json();
                if (!data.items) continue;

                const books = data.items.map((item: any) => ({
                    title: item.volumeInfo.title || '',
                    author: item.volumeInfo.authors?.[0] || 'Unknown',
                    publisher: item.volumeInfo.publisher || '',
                    isbn: item.volumeInfo.industryIdentifiers?.[0]?.identifier || '',
                    translator: '',
                    tags: item.volumeInfo.categories || [],
                    summary: item.volumeInfo.description || '',
                    publishedDate: item.volumeInfo.publishedDate || '',
                    url: item.volumeInfo.infoLink || '',
                    coverUrl: item.volumeInfo.imageLinks?.thumbnail || null,
                    pageCount: item.volumeInfo.pageCount || undefined,
                } as BookItem));

                results.push(...books);
                googleBooksWorked = true;
                if (results.length >= 3) break;
            } catch (error) {
                console.warn(`Google Books fetch failed for variant "${variant}":`, error);
                // Continue to next variant or fallback
            }
        }

        // If Google Books worked, return results
        if (googleBooksWorked && results.length > 0) {
            return results;
        }

        // Fallback to OpenLibrary if Google Books failed or returned no results
        console.warn('Google Books failed or returned no results, trying OpenLibrary fallback...');
        const openLibraryResults = await searchOpenLibrary(query);

        if (openLibraryResults.length > 0) {
            console.log('✓ Successfully fetched from OpenLibrary (fallback)');
            return openLibraryResults;
        }

        return results; // Return whatever we got, even if empty
    } catch (error) {
        console.error('Google Books error:', error);

        // Try OpenLibrary as fallback
        try {
            console.warn('Attempting OpenLibrary fallback after Google Books error...');
            const openLibraryResults = await searchOpenLibrary(query);
            if (openLibraryResults.length > 0) {
                console.log('✓ Successfully fetched from OpenLibrary (fallback)');
                return openLibraryResults;
            }
        } catch (fallbackError) {
            console.error('OpenLibrary fallback also failed:', fallbackError);
        }

        return [];
    }
}

// API: Open Library
async function searchOpenLibrary(query: string): Promise<BookItem[]> {
    try {
        const variants = generateCharacterVariants(query);
        const results: BookItem[] = [];

        for (const variant of variants) {
            const apiUrl = `https://openlibrary.org/search.json?q=${encodeURIComponent(variant)}&limit=10`;
            const response = await fetch(apiUrl);
            if (!response.ok) continue;

            const data = await response.json();
            if (!data.docs || data.docs.length === 0) continue;

            const books = data.docs.map((doc: any) => ({
                title: doc.title || '',
                author: doc.author_name?.[0] || 'Unknown',
                publisher: doc.publisher?.[0] || '',
                isbn: doc.isbn?.[0] || '',
                translator: '',
                tags: doc.subject?.slice(0, 5) || [],
                summary: '',
                publishedDate: doc.first_publish_year?.toString() || '',
                url: `https://openlibrary.org${doc.key}`,
                coverUrl: doc.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg` : null,
                pageCount: doc.number_of_pages_median || doc.number_of_pages || undefined,
            } as BookItem));

            results.push(...books);
            if (results.length >= 3) break;
        }
        return results;
    } catch (error) {
        console.error('Open Library error:', error);
        return [];
    }
}

// MAIN EXPORT
export async function searchBooks(query: string): Promise<SearchResult> {
    if (!query.trim()) return { results: [], source: 'google-books', cached: false };

    const normalized = normalizeQuery(query);
    const cacheKey = `search:${normalized}`;

    if (searchCache.has(cacheKey)) {
        console.log('✓ Cache hit for:', normalized);
        return { ...searchCache.get(cacheKey)!, cached: true };
    }

    console.log('🔍 Searching for:', normalized);

    // 1. Try APIs directly
    const [googleResults, openLibResults] = await Promise.all([
        searchGoogleBooks(normalized),
        searchOpenLibrary(normalized),
    ]);

    let allResults = [...googleResults, ...openLibResults];
    const uniqueResults = deduplicateResults(allResults);
    const rankedResults = rankResults(query, uniqueResults);

    // 2. Return results
    const result: SearchResult = {
        results: rankedResults.slice(0, 10),
        source: googleResults.length > 0 ? 'google-books' : 'open-library',
        cached: false,
    };
    searchCache.set(cacheKey, result);
    return result;
}

export function clearSearchCache(): void {
    searchCache.clear();
    queryCache.clear();
    console.log('✓ Search cache cleared');
}
