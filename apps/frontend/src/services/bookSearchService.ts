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

function isIsbn(query: string): boolean {
    const clean = query.replace(/[-\s]/g, '');
    return (clean.length === 10 || clean.length === 13) && /^\d+X?$/i.test(clean);
}

function normalizeQuery(query: string): string {
    return query
        .trim()
        .toLocaleLowerCase('tr-TR')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\u0131/g, 'i')
        .replace(/\s+/g, ' ');
}

function tokenize(query: string): string[] {
    return normalizeQuery(query)
        .split(' ')
        .map((t) => t.trim())
        .filter((t) => t.length >= 2);
}

function toAsciiBasic(text: string): string {
    return text
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[\u00e7\u00c7]/g, 'c')
        .replace(/[\u011f\u011e]/g, 'g')
        .replace(/[\u0131\u0130]/g, 'i')
        .replace(/[\u00f6\u00d6]/g, 'o')
        .replace(/[\u015f\u015e]/g, 's')
        .replace(/[\u00fc\u00dc]/g, 'u');
}

function expandCrossLingualVariants(query: string): string[] {
    const variants = new Set<string>();
    const normalized = normalizeQuery(query);
    const tokens = tokenize(normalized);
    if (!tokens.length) return [];

    const lexicon: Record<string, string[]> = {
        etik: ['ethics', 'ethic'],
        ahlak: ['ethics', 'morality'],
        kotuluk: ['evil'],
        kavrayisi: ['understanding'],
        uzerine: ['on'],
        deneme: ['essay'],
        felsefesi: ['philosophy'],
        felsefe: ['philosophy'],
    };

    const translated = tokens.map((t) => (lexicon[t] && lexicon[t][0]) ? lexicon[t][0] : t);
    if (translated.join(' ') !== tokens.join(' ')) {
        variants.add(translated.join(' '));
    }

    // Keep author signal, but rewrite known Turkish concept words to common English catalog terms.
    if (tokens.includes('badiou') && (tokens.includes('etik') || tokens.includes('ahlak'))) {
        variants.add('alain badiou ethics');
        variants.add('ethics alain badiou');
        variants.add('ethics an essay on the understanding of evil alain badiou');
    }

    return Array.from(variants);
}

function buildQueryVariants(query: string): string[] {
    const variants = new Set<string>();
    const normalized = normalizeQuery(query);
    const tokens = tokenize(query);

    variants.add(query);
    variants.add(normalized);
    variants.add(toAsciiBasic(query));
    variants.add(toAsciiBasic(normalized));
    expandCrossLingualVariants(query).forEach((v) => variants.add(v));

    if (tokens.length >= 3) {
        const authorGuess = `${tokens[tokens.length - 2]} ${tokens[tokens.length - 1]}`;
        const titleGuess = tokens.slice(0, -2).join(' ');

        variants.add(`${authorGuess} ${titleGuess}`);
        variants.add(`intitle:${titleGuess} inauthor:${authorGuess}`);
        variants.add(`inauthor:${authorGuess}`);
    }

    return Array.from(variants)
        .map((v) => normalizeQuery(v))
        .filter((v) => !!v);
}

// Helper: Generate character variants (real Turkish + mojibake fallback)
function generateCharacterVariants(text: string): string[] {
    const variants = new Set<string>();
    variants.add(text);
    variants.add(toAsciiBasic(text));

    const map: Record<string, string> = {
        '\u00e7': 'c', '\u011f': 'g', '\u0131': 'i', '\u00f6': 'o', '\u015f': 's', '\u00fc': 'u',
        '\u00c7': 'C', '\u011e': 'G', '\u0130': 'I', '\u00d6': 'O', '\u015e': 'S', '\u00dc': 'U',
        'Ã§': 'c', 'ÄŸ': 'g', 'Ä±': 'i', 'Ã¶': 'o', 'ÅŸ': 's', 'Ã¼': 'u',
        'Ã‡': 'C', 'Äž': 'G', 'Ä°': 'I', 'Ã–': 'O', 'Åž': 'S', 'Ãœ': 'U'
    };

    let asciiVariant = text;
    for (const [char, repl] of Object.entries(map)) {
        asciiVariant = asciiVariant.replace(new RegExp(char, 'g'), repl);
    }

    if (asciiVariant !== text) {
        variants.add(asciiVariant);
    }

    return Array.from(variants).slice(0, 8);
}

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

function tokenOverlapScore(query: string, target: string): number {
    const qTokens = tokenize(query);
    const tTokens = tokenize(target);
    if (!qTokens.length || !tTokens.length) return 0;
    const tSet = new Set(tTokens);
    const overlap = qTokens.filter((t) => tSet.has(t)).length;
    return overlap / qTokens.length;
}

function rankResults(query: string, results: BookItem[]): BookItem[] {
    const queryNorm = normalizeQuery(query);
    const queryTokens = tokenize(query);
    const queryIsIsbn = isIsbn(queryNorm);

    const scored = results.map((result) => {
        // If it's an ISBN search, and the result's ISBN matches the query, give it a perfect score.
        if (queryIsIsbn && result.isbn) {
            const cleanQueryIsbn = queryNorm.replace(/[-\s]/g, '');
            const cleanResultIsbn = result.isbn.replace(/[-\s]/g, '');
            if (cleanResultIsbn.includes(cleanQueryIsbn) || cleanQueryIsbn.includes(cleanResultIsbn)) {
                return { result, score: 1.0 };
            }
        }

        const title = result.title || '';
        const author = result.author || '';

        const titleScore = similarityScore(queryNorm, title);
        const authorScore = similarityScore(queryNorm, author);
        const titleTokenScore = tokenOverlapScore(queryNorm, title);
        const authorTokenScore = tokenOverlapScore(queryNorm, author);

        const queryHasAuthorHint = queryTokens.length >= 2 && authorTokenScore >= 0.5;
        const combinedScore = Math.max(
            titleScore * 0.45 + titleTokenScore * 0.45 + authorTokenScore * 0.1,
            authorScore * 0.6 + authorTokenScore * 0.4
        ) + (queryHasAuthorHint ? 0.1 : 0);

        return { result, score: combinedScore };
    });

    const filtered = scored.filter((item) => item.score >= 0.1);
    if (filtered.length === 0) {
        scored.sort((a, b) => b.score - a.score);
        return scored.slice(0, 5).map((item) => item.result);
    }

    filtered.sort((a, b) => b.score - a.score);
    return filtered.map((item) => item.result);
}

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

async function searchGoogleBooks(query: string): Promise<BookItem[]> {
    try {
        let variants: string[];
        if (isIsbn(query)) {
            const cleanIsbn = query.replace(/[-\s]/g, '');
            variants = [`isbn:${cleanIsbn}`];
        } else {
            variants = buildQueryVariants(query).flatMap(generateCharacterVariants);
        }

        const results: BookItem[] = [];
        let googleBooksWorked = false;

        for (const variant of variants) {
            const apiUrl = `https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(variant)}&maxResults=10`;

            try {
                const response = await fetch(apiUrl);
                if (!response.ok) {
                    if (response.status === 503 || response.status === 429) {
                        console.warn(`Google Books throttled/unavailable (${response.status})`);
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
                    sourceLanguageHint: item.volumeInfo.language || undefined,
                } as BookItem));

                results.push(...books);
                googleBooksWorked = true;
                if (results.length >= 10) break;
            } catch (error) {
                console.warn(`Google Books fetch failed for variant "${variant}":`, error);
            }
        }

        if (googleBooksWorked && results.length > 0) {
            return results;
        }

        console.warn('Google Books failed or returned no results, trying OpenLibrary fallback...');
        const openLibraryResults = await searchOpenLibrary(query);

        if (openLibraryResults.length > 0) {
            console.log('OpenLibrary fallback succeeded');
            return openLibraryResults;
        }

        return results;
    } catch (error) {
        console.error('Google Books error:', error);

        try {
            const openLibraryResults = await searchOpenLibrary(query);
            if (openLibraryResults.length > 0) {
                console.log('OpenLibrary fallback succeeded');
                return openLibraryResults;
            }
        } catch (fallbackError) {
            console.error('OpenLibrary fallback also failed:', fallbackError);
        }

        return [];
    }
}

async function searchOpenLibrary(query: string): Promise<BookItem[]> {
    try {
        let variants: string[];
        if (isIsbn(query)) {
            const cleanIsbn = query.replace(/[-\s]/g, '');
            variants = [cleanIsbn];
        } else {
            variants = buildQueryVariants(query).flatMap(generateCharacterVariants);
        }
        const results: BookItem[] = [];

        for (const variant of variants) {
            let apiUrl = `https://openlibrary.org/search.json?q=${encodeURIComponent(variant)}&limit=10`;
            if (isIsbn(query)) {
                apiUrl = `https://openlibrary.org/search.json?isbn=${encodeURIComponent(variant)}&limit=10`;
            }

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
                sourceLanguageHint: doc.language?.[0] || undefined,
            } as BookItem));

            results.push(...books);
            if (results.length >= 15) break;
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
        return { ...searchCache.get(cacheKey)!, cached: true };
    }

    const [googleResults, openLibResults] = await Promise.all([
        searchGoogleBooks(normalized),
        searchOpenLibrary(normalized),
    ]);

    const allResults = [...googleResults, ...openLibResults];
    const uniqueResults = deduplicateResults(allResults);
    const rankedResults = rankResults(query, uniqueResults);

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
}
