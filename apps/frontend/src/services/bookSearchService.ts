import { ItemDraft } from "./geminiService";

export interface BookItem extends ItemDraft {
    allIsbns?: string[];
    _provider?: "google-books" | "open-library" | "open-library-bib";
}

export interface SearchResult {
    results: BookItem[];
    source: "google-books" | "open-library" | "llm-corrected";
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

const searchCache = new Map<string, SearchResult>();
const queryCache = new Map<string, CorrectedQuery>();

const GOOGLE_MAX_RESULTS = 20;
const OPENLIB_MAX_RESULTS = 20;

function normalizeQuery(query: string): string {
    return query
        .trim()
        .toLocaleLowerCase("tr-TR")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\u0131/g, "i")
        .replace(/\s+/g, " ");
}

function tokenize(query: string): string[] {
    return normalizeQuery(query)
        .split(" ")
        .map((t) => t.trim())
        .filter((t) => t.length >= 2);
}

function toAsciiBasic(text: string): string {
    return text
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[\u00e7\u00c7]/g, "c")
        .replace(/[\u011f\u011e]/g, "g")
        .replace(/[\u0131\u0130]/g, "i")
        .replace(/[\u00f6\u00d6]/g, "o")
        .replace(/[\u015f\u015e]/g, "s")
        .replace(/[\u00fc\u00dc]/g, "u");
}

function normalizeIsbnRaw(value: string): string {
    return String(value || "").replace(/[^0-9Xx]/g, "").toUpperCase();
}

function isValidIsbn10(isbn: string): boolean {
    if (!/^\d{9}[\dX]$/.test(isbn)) return false;
    let sum = 0;
    for (let i = 0; i < 10; i += 1) {
        const ch = isbn[i];
        const digit = ch === "X" ? 10 : Number(ch);
        sum += digit * (10 - i);
    }
    return sum % 11 === 0;
}

function isValidIsbn13(isbn: string): boolean {
    if (!/^\d{13}$/.test(isbn)) return false;
    let sum = 0;
    for (let i = 0; i < 12; i += 1) {
        sum += Number(isbn[i]) * (i % 2 === 0 ? 1 : 3);
    }
    const check = (10 - (sum % 10)) % 10;
    return check === Number(isbn[12]);
}

function isbn10To13(isbn10: string): string | null {
    if (!isValidIsbn10(isbn10)) return null;
    const core = `978${isbn10.slice(0, 9)}`;
    let sum = 0;
    for (let i = 0; i < 12; i += 1) {
        sum += Number(core[i]) * (i % 2 === 0 ? 1 : 3);
    }
    const check = (10 - (sum % 10)) % 10;
    return `${core}${check}`;
}

function isbn13To10(isbn13: string): string | null {
    if (!isValidIsbn13(isbn13) || !isbn13.startsWith("978")) return null;
    const core = isbn13.slice(3, 12);
    let sum = 0;
    for (let i = 0; i < 9; i += 1) {
        sum += Number(core[i]) * (10 - i);
    }
    const rem = 11 - (sum % 11);
    const check = rem === 10 ? "X" : rem === 11 ? "0" : String(rem);
    return `${core}${check}`;
}

function normalizeValidIsbn(value: string): string | null {
    const raw = normalizeIsbnRaw(value);
    if (raw.length === 13 && isValidIsbn13(raw)) return raw;
    if (raw.length === 10 && isValidIsbn10(raw)) return raw;
    return null;
}

function getEquivalentIsbnSet(value: string): Set<string> {
    const out = new Set<string>();
    const normalized = normalizeValidIsbn(value);
    if (!normalized) return out;
    out.add(normalized);
    if (normalized.length === 10) {
        const as13 = isbn10To13(normalized);
        if (as13) out.add(as13);
    } else if (normalized.length === 13) {
        const as10 = isbn13To10(normalized);
        if (as10) out.add(as10);
    }
    return out;
}

export function isIsbn(query: string): boolean {
    return getEquivalentIsbnSet(query).size > 0;
}

function extractGoogleIsbns(industryIdentifiers: any[] | undefined): string[] {
    const unique = new Set<string>();
    for (const id of industryIdentifiers || []) {
        const normalized = normalizeValidIsbn(String(id?.identifier || ""));
        if (normalized) unique.add(normalized);
    }
    return Array.from(unique);
}

function extractOpenLibraryIsbns(candidates: unknown): string[] {
    const values = Array.isArray(candidates) ? candidates : [];
    const unique = new Set<string>();
    for (const raw of values) {
        const normalized = normalizeValidIsbn(String(raw || ""));
        if (normalized) unique.add(normalized);
    }
    return Array.from(unique);
}

function pickPreferredIsbn(isbns: string[], queryIsbns?: Set<string>): string {
    if (queryIsbns && queryIsbns.size > 0) {
        const direct = isbns.find((isbn) => queryIsbns.has(isbn));
        if (direct) return direct;
    }
    const isbn13 = isbns.find((isbn) => isbn.length === 13);
    if (isbn13) return isbn13;
    return isbns[0] || "";
}

function hasAnyIsbnMatch(itemIsbns: string[], queryIsbns: Set<string>): boolean {
    if (queryIsbns.size === 0) return false;
    for (const isbn of itemIsbns) {
        if (queryIsbns.has(isbn)) return true;
    }
    return false;
}

function mapGoogleItemToBook(item: any, queryIsbns?: Set<string>): BookItem | null {
    const volumeInfo = item?.volumeInfo || {};
    const allIsbns = extractGoogleIsbns(volumeInfo.industryIdentifiers);

    if (queryIsbns && queryIsbns.size > 0 && !hasAnyIsbnMatch(allIsbns, queryIsbns)) {
        return null;
    }

    return {
        title: volumeInfo.title || "",
        author: volumeInfo.authors?.[0] || "Unknown",
        publisher: volumeInfo.publisher || "",
        isbn: pickPreferredIsbn(allIsbns, queryIsbns),
        allIsbns,
        translator: "",
        tags: volumeInfo.categories || [],
        summary: volumeInfo.description || "",
        publishedDate: volumeInfo.publishedDate || "",
        url: volumeInfo.infoLink || "",
        coverUrl: volumeInfo.imageLinks?.thumbnail || null,
        pageCount: volumeInfo.pageCount || undefined,
        sourceLanguageHint: volumeInfo.language || undefined,
        _provider: "google-books",
    } as BookItem;
}

function mapOpenLibraryDocToBook(doc: any, queryIsbns?: Set<string>): BookItem | null {
    const allIsbns = extractOpenLibraryIsbns(doc?.isbn || []);
    if (queryIsbns && queryIsbns.size > 0 && !hasAnyIsbnMatch(allIsbns, queryIsbns)) {
        return null;
    }

    return {
        title: doc?.title || "",
        author: doc?.author_name?.[0] || "Unknown",
        publisher: doc?.publisher?.[0] || "",
        isbn: pickPreferredIsbn(allIsbns, queryIsbns),
        allIsbns,
        translator: "",
        tags: doc?.subject?.slice(0, 5) || [],
        summary: "",
        publishedDate: doc?.first_publish_year?.toString() || "",
        url: doc?.key ? `https://openlibrary.org${doc.key}` : "",
        coverUrl: doc?.cover_i ? `https://covers.openlibrary.org/b/id/${doc.cover_i}-M.jpg` : null,
        pageCount: doc?.number_of_pages_median || doc?.number_of_pages || undefined,
        sourceLanguageHint: doc?.language?.[0] || undefined,
        _provider: "open-library",
    } as BookItem;
}

function mapOpenLibraryBibToBook(entry: any, queryIsbns?: Set<string>): BookItem | null {
    const identifiers = entry?.identifiers || {};
    const allIsbns = extractOpenLibraryIsbns([
        ...(Array.isArray(identifiers?.isbn_13) ? identifiers.isbn_13 : []),
        ...(Array.isArray(identifiers?.isbn_10) ? identifiers.isbn_10 : []),
    ]);

    if (queryIsbns && queryIsbns.size > 0 && !hasAnyIsbnMatch(allIsbns, queryIsbns)) {
        return null;
    }

    const publishers = Array.isArray(entry?.publishers)
        ? entry.publishers.map((p: any) => String(p?.name || "").trim()).filter(Boolean)
        : [];
    const authors = Array.isArray(entry?.authors)
        ? entry.authors.map((a: any) => String(a?.name || "").trim()).filter(Boolean)
        : [];

    const coverUrl = entry?.cover?.large || entry?.cover?.medium || entry?.cover?.small || null;
    const openLibraryUrl = entry?.url ? `https://openlibrary.org${entry.url}` : "";

    return {
        title: String(entry?.title || "").trim(),
        author: authors[0] || "Unknown",
        publisher: publishers[0] || "",
        isbn: pickPreferredIsbn(allIsbns, queryIsbns),
        allIsbns,
        translator: "",
        tags: [],
        summary: String(entry?.notes || "").trim(),
        publishedDate: String(entry?.publish_date || "").trim(),
        url: openLibraryUrl,
        coverUrl,
        pageCount: Number(entry?.number_of_pages) || undefined,
        sourceLanguageHint: undefined,
        _provider: "open-library-bib",
    } as BookItem;
}

function buildQueryVariants(query: string): string[] {
    const variants = new Set<string>();
    const normalized = normalizeQuery(query);
    const tokens = tokenize(query);

    variants.add(query);
    variants.add(normalized);
    variants.add(toAsciiBasic(query));
    variants.add(toAsciiBasic(normalized));

    if (tokens.length >= 3) {
        const authorGuess = `${tokens[tokens.length - 2]} ${tokens[tokens.length - 1]}`;
        const titleGuess = tokens.slice(0, -2).join(" ");

        variants.add(`${authorGuess} ${titleGuess}`);
        variants.add(`intitle:${titleGuess} inauthor:${authorGuess}`);
        variants.add(`inauthor:${authorGuess}`);
    }

    return Array.from(variants)
        .map((v) => normalizeQuery(v))
        .filter(Boolean);
}

function generateCharacterVariants(text: string): string[] {
    const variants = new Set<string>();
    variants.add(text);
    variants.add(toAsciiBasic(text));

    const map: Record<string, string> = {
        "\u00e7": "c", "\u011f": "g", "\u0131": "i", "\u00f6": "o", "\u015f": "s", "\u00fc": "u",
        "\u00c7": "C", "\u011e": "G", "\u0130": "I", "\u00d6": "O", "\u015e": "S", "\u00dc": "U",
        "Ã§": "c", "ÄŸ": "g", "Äı": "i", "Ã¶": "o", "ÅŸ": "s", "Ã¼": "u",
        "Ã‡": "C", "Äž": "G", "Ä°": "I", "Ã–": "O", "Åž": "S", "Ãœ": "U",
    };

    let asciiVariant = text;
    for (const [char, repl] of Object.entries(map)) {
        asciiVariant = asciiVariant.replace(new RegExp(char, "g"), repl);
    }
    if (asciiVariant !== text) variants.add(asciiVariant);
    return Array.from(variants).slice(0, 8);
}

function levenshteinDistance(a: string, b: string): number {
    const matrix: number[][] = [];
    for (let i = 0; i <= b.length; i += 1) matrix[i] = [i];
    for (let j = 0; j <= a.length; j += 1) matrix[0][j] = j;
    for (let i = 1; i <= b.length; i += 1) {
        for (let j = 1; j <= a.length; j += 1) {
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

function deduplicateResults(items: BookItem[]): BookItem[] {
    const seen = new Set<string>();
    const unique: BookItem[] = [];

    for (const item of items) {
        const normalizedIsbns = (item.allIsbns || [])
            .map((isbn) => normalizeValidIsbn(isbn) || "")
            .filter(Boolean)
            .sort();
        const isbnKey = normalizedIsbns.join(",");
        const fallbackKey = `${normalizeQuery(item.title)}|${normalizeQuery(item.author)}`;
        const key = isbnKey || fallbackKey;
        if (seen.has(key)) continue;
        seen.add(key);
        unique.push(item);
    }
    return unique;
}

function rankResults(query: string, results: BookItem[]): BookItem[] {
    const queryNorm = normalizeQuery(query);
    const queryTokens = tokenize(queryNorm);
    const queryIsbns = getEquivalentIsbnSet(query);

    if (queryIsbns.size > 0) {
        const scored = results.map((result) => {
            const itemIsbns = (result.allIsbns || [])
                .map((isbn) => normalizeValidIsbn(isbn) || "")
                .filter(Boolean);
            const directMatch = itemIsbns.find((isbn) => queryIsbns.has(isbn));
            const providerBonus =
                result._provider === "google-books" ? 0.08
                    : result._provider === "open-library-bib" ? 0.06
                        : 0.04;
            const langBonus = normalizeQuery(String(result.sourceLanguageHint || "")) === "tr" ? 0.02 : 0;
            const score = (directMatch ? 1 : 0) + providerBonus + langBonus;
            return { result, score };
        });

        scored.sort((a, b) => b.score - a.score);
        return scored.map((entry) => entry.result);
    }

    const scored = results.map((result) => {
        const title = result.title || "";
        const author = result.author || "";
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

async function searchGoogleBooks(query: string): Promise<BookItem[]> {
    const queryIsbns = getEquivalentIsbnSet(query);
    const isIsbnQuery = queryIsbns.size > 0;
    const variants = isIsbnQuery
        ? Array.from(queryIsbns).map((isbn) => `isbn:${isbn}`)
        : buildQueryVariants(query).flatMap(generateCharacterVariants);

    const results: BookItem[] = [];
    for (const variant of variants) {
        const apiUrl = `https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(variant)}&maxResults=${GOOGLE_MAX_RESULTS}&printType=books`;
        try {
            const response = await fetch(apiUrl);
            if (!response.ok) {
                if (response.status === 503 || response.status === 429) {
                    console.warn(`Google Books throttled/unavailable (${response.status})`);
                }
                continue;
            }
            const data = await response.json();
            const items = Array.isArray(data?.items) ? data.items : [];
            for (const item of items) {
                const mapped = mapGoogleItemToBook(item, isIsbnQuery ? queryIsbns : undefined);
                if (mapped) results.push(mapped);
            }
            if (results.length >= GOOGLE_MAX_RESULTS) break;
        } catch (error) {
            console.warn(`Google Books fetch failed for variant "${variant}":`, error);
        }
    }
    return deduplicateResults(results);
}

async function searchOpenLibraryByBibKey(queryIsbns: Set<string>): Promise<BookItem[]> {
    const results: BookItem[] = [];
    for (const isbn of queryIsbns) {
        const apiUrl = `https://openlibrary.org/api/books?bibkeys=${encodeURIComponent(`ISBN:${isbn}`)}&format=json&jscmd=data`;
        try {
            const response = await fetch(apiUrl);
            if (!response.ok) continue;
            const data = await response.json();
            const key = `ISBN:${isbn}`;
            const entry = data?.[key];
            if (!entry) continue;
            const mapped = mapOpenLibraryBibToBook(entry, queryIsbns);
            if (mapped) results.push(mapped);
        } catch (error) {
            console.warn(`OpenLibrary bib lookup failed for ${isbn}:`, error);
        }
    }
    return deduplicateResults(results);
}

async function searchOpenLibrary(query: string): Promise<BookItem[]> {
    const queryIsbns = getEquivalentIsbnSet(query);
    const isIsbnQuery = queryIsbns.size > 0;
    const variants = isIsbnQuery
        ? Array.from(queryIsbns)
        : buildQueryVariants(query).flatMap(generateCharacterVariants);
    const results: BookItem[] = [];

    if (isIsbnQuery) {
        const bibResults = await searchOpenLibraryByBibKey(queryIsbns);
        results.push(...bibResults);
    }

    for (const variant of variants) {
        const apiUrl = isIsbnQuery
            ? `https://openlibrary.org/search.json?isbn=${encodeURIComponent(variant)}&limit=${OPENLIB_MAX_RESULTS}`
            : `https://openlibrary.org/search.json?q=${encodeURIComponent(variant)}&limit=${OPENLIB_MAX_RESULTS}`;

        try {
            const response = await fetch(apiUrl);
            if (!response.ok) continue;
            const data = await response.json();
            const docs = Array.isArray(data?.docs) ? data.docs : [];
            for (const doc of docs) {
                const mapped = mapOpenLibraryDocToBook(doc, isIsbnQuery ? queryIsbns : undefined);
                if (mapped) results.push(mapped);
            }
            if (results.length >= OPENLIB_MAX_RESULTS) break;
        } catch (error) {
            console.warn(`OpenLibrary fetch failed for variant "${variant}":`, error);
        }
    }

    return deduplicateResults(results);
}

export async function searchBooks(query: string): Promise<SearchResult> {
    const trimmed = query.trim();
    if (!trimmed) return { results: [], source: "google-books", cached: false };

    const cacheKey = `search:${normalizeQuery(trimmed)}`;
    if (searchCache.has(cacheKey)) {
        return { ...searchCache.get(cacheKey)!, cached: true };
    }

    const isbnSet = getEquivalentIsbnSet(trimmed);

    const [googleResults, openLibResults] = await Promise.all([
        searchGoogleBooks(trimmed),
        searchOpenLibrary(trimmed),
    ]);

    let allResults = deduplicateResults([...googleResults, ...openLibResults]);

    if (isbnSet.size > 0) {
        allResults = allResults.filter((item) => {
            const itemIsbns = (item.allIsbns || [])
                .map((isbn) => normalizeValidIsbn(isbn) || "")
                .filter(Boolean);
            return hasAnyIsbnMatch(itemIsbns, isbnSet);
        });
    }

    const rankedResults = rankResults(trimmed, allResults).slice(0, 10);
    const source: SearchResult["source"] = rankedResults.some((r) => r._provider === "google-books")
        ? "google-books"
        : "open-library";

    const result: SearchResult = {
        results: rankedResults,
        source,
        cached: false,
    };
    searchCache.set(cacheKey, result);
    return result;
}

export function clearSearchCache(): void {
    searchCache.clear();
    queryCache.clear();
}
