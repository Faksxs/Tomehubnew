import { ResourceType, LibraryItem, ContentLanguageMode, ContentLanguageResolved } from "../types";
import { getAuth } from "firebase/auth";
import { API_BASE_URL } from "./apiClient";

// Helper function to get Firebase Auth ID token
const getAuthToken = async (): Promise<string> => {
  const auth = getAuth();
  const user = auth.currentUser;

  if (!user) {
    // throw new Error('User must be logged in to use AI features');
    // Allow anonymous or fallback? No, robust auth needed.
    return ""; // Will fail at backend if token missing, typically caught by UI
  }

  return await user.getIdToken();
};

// API_BASE_URL is now imported from apiClient.ts

const normalizeLangHint = (value?: string | null): "tr" | "en" | undefined => {
  const raw = (value || "").toLowerCase().trim();
  if (raw === "tr" || raw === "turkish" || raw === "turkce" || raw === "türkçe") return "tr";
  if (raw === "en" || raw === "english" || raw === "ingilizce") return "en";
  return undefined;
};

export interface ItemDraft {
  title: string;
  author: string;
  publisher?: string; // Journal for articles
  isbn?: string;
  translator?: string;
  tags?: string[];
  summary?: string;
  publishedDate?: string;
  url?: string;
  coverUrl?: string | null;
  pageCount?: number;
  contentLanguageMode?: ContentLanguageMode;
  contentLanguageResolved?: ContentLanguageResolved;
  sourceLanguageHint?: string;
  languageDecisionReason?: string;
  languageDecisionConfidence?: number;
  force_regenerate?: boolean;
}

/* ----------------------------------------------------
 *  HELPER: LibraryItem <-> ItemDraft dönüşümleri
 * --------------------------------------------------*/
export const libraryItemToDraft = (item: LibraryItem): ItemDraft => {
  return {
    title: item.title,
    author: item.author,
    publisher: item.publisher,
    isbn: item.isbn,
    translator: item.translator,
    tags: item.tags,
    // Özet için: önce generalNotes, yoksa summary, yoksa boş string
    summary: item.summaryText || item.generalNotes || (item as any).summary || "",
    publishedDate: item.publicationYear
      ? String(item.publicationYear)
      : (item as any).publishedDate || "",
    url: item.url,
    coverUrl: item.coverUrl ?? null,
    pageCount: (item as any).pageCount || undefined,
    contentLanguageMode: item.contentLanguageMode || "AUTO",
    contentLanguageResolved: item.contentLanguageResolved,
    sourceLanguageHint: normalizeLangHint(item.sourceLanguageHint),
  };
};

export const mergeEnrichedDraftIntoItem = (
  item: LibraryItem,
  draft: ItemDraft
): LibraryItem => {
  const resolvedFromDraft = ((draft as any).content_language_resolved || draft.contentLanguageResolved || "").toString().toLowerCase();
  const normalizedResolved = resolvedFromDraft === "tr" || resolvedFromDraft === "en"
    ? (resolvedFromDraft as ContentLanguageResolved)
    : item.contentLanguageResolved;
  const decisionConfidenceRaw = Number((draft as any).language_decision_confidence ?? draft.languageDecisionConfidence ?? item.languageDecisionConfidence ?? NaN);
  const decisionConfidence = Number.isFinite(decisionConfidenceRaw) ? decisionConfidenceRaw : item.languageDecisionConfidence;

  return {
    ...item,
    // AI’den gelen summary’i generalNotes’a yaz
    summaryText:
      draft.summary && draft.summary.trim().length > 0
        ? draft.summary
        : item.summaryText,
    // Etiketler: AI’den gelen varsa onu kullan
    tags: draft.tags && draft.tags.length > 0 ? draft.tags : item.tags,
    // Diğer alanlar da zenginleşmişse güncelle
    publisher: draft.publisher || item.publisher,
    isbn: draft.isbn || item.isbn,
    author: draft.author || item.author,
    translator: draft.translator || item.translator,
    publicationYear: draft.publishedDate
      ? String(Number(draft.publishedDate) || item.publicationYear || '')
      : item.publicationYear,
    coverUrl: draft.coverUrl ?? item.coverUrl,
    pageCount: draft.pageCount || (item as any).pageCount || undefined,
    contentLanguageMode: draft.contentLanguageMode || item.contentLanguageMode || "AUTO",
    contentLanguageResolved: normalizedResolved,
    sourceLanguageHint: normalizeLangHint(draft.sourceLanguageHint || item.sourceLanguageHint),
    languageDecisionReason: ((draft as any).language_decision_reason || draft.languageDecisionReason || item.languageDecisionReason) as string | undefined,
    languageDecisionConfidence: decisionConfidence,
  } as LibraryItem;
};

/* ----------------------------------------------------
 *  HIZLI MAKALE ARAMA: CROSSREF (AUTH GEREKMEZ)
 * --------------------------------------------------*/
const searchArticlesFromAPIs = async (query: string): Promise<ItemDraft[]> => {
  if (!query.trim()) return [];

  const results: ItemDraft[] = [];

  try {
    // 1. CrossRef API - Academic papers and journals (fast, no auth needed)
    const crossrefUrl = `https://api.crossref.org/works?query=${encodeURIComponent(
      query
    )}&rows=5&select=title,author,publisher,published,DOI,abstract,URL`;

    const crossrefPromise = fetch(crossrefUrl)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.message?.items) {
          return data.message.items.map((item: any) => ({
            title: Array.isArray(item.title) ? item.title[0] : item.title || "",
            author: item.author?.[0]?.family
              ? `${item.author[0].given || ""} ${item.author[0].family}`.trim()
              : item.author?.[0]?.name || "Unknown",
            publisher: item.publisher || item["container-title"]?.[0] || "",
            isbn: "",
            translator: "",
            tags: item.subject || [],
            summary: item.abstract || `DOI: ${item.DOI || ""}`,
            publishedDate: item.published?.["date-parts"]?.[0]?.[0]?.toString() || "",
            url: item.URL || (item.DOI ? `https://doi.org/${item.DOI}` : ""),
            coverUrl: null,
          } as ItemDraft));
        }
        return [];
      })
      .catch(() => []);

    // Execute API call
    const crossrefResults = await crossrefPromise;
    results.push(...crossrefResults);

    return results;
  } catch (error) {
    console.error("Article search error:", error);
    return [];
  }
};

/* ----------------------------------------------------
 *  ANA ARAMA FONKSİYONU
 *  - BOOK için önce Google Books
 *  - Sonra gerekirse Gemini fallback (Backend üzerinden)
 *  - ARTICLE / WEBSITE için direkt Gemini (Backend üzerinden)
 * --------------------------------------------------*/
export const searchResourcesAI = async (
  query: string,
  type: ResourceType
): Promise<ItemDraft[]> => {
  const trimmed = query.trim();
  if (!trimmed) return [];

  // 1) Hızlı yol: BOOK için optimized bookSearchService kullan
  if (type === "BOOK") {
    const { searchBooks } = await import('./bookSearchService');
    const result = await searchBooks(trimmed);
    if (result.results.length > 0) {
      console.log(`✓ Results from bookSearchService (${result.source}, cached: ${result.cached})`);
      return result.results;
    }
  }

  // 2) Hızlı yol: ARTICLE için önce CrossRef
  if (type === "ARTICLE") {
    const fastResults = await searchArticlesFromAPIs(trimmed);
    if (fastResults.length > 0) {
      console.log("✓ Results from CrossRef (fast)");
      return fastResults;
    }
  }

  // 3) Fallback: Gemini ile arama (Backend üzerinden)
  try {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/ai/search-resources`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ query: trimmed, type: type })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Search failed');
    }

    const data = await response.json();
    // Backend returns { results: ItemDraft[] }
    return data.results.map((item: any) => ({
      ...item,
      coverUrl: null,
      sourceLanguageHint: normalizeLangHint(item.sourceLanguageHint || item.source_language_hint),
      contentLanguageResolved: normalizeLangHint(item.contentLanguageResolved || item.content_language_resolved),
    })) as ItemDraft[];

  } catch (error) {
    console.error("Error searching with Gemini (Backend):", error);
    return [];
  }
};

/* ----------------------------------------------------
 *  HIGHLIGHT ANALİZİ (Backend)
 * --------------------------------------------------*/
export const analyzeHighlightsAI = async (
  highlightsText: string[]
): Promise<string | null> => {
  if (highlightsText.length === 0) return null;

  try {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/ai/analyze-highlights`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ highlights: highlightsText })
    });

    if (!response.ok) return null;

    const data = await response.json();
    return data.summary || null;

  } catch (error) {
    console.error("Gemini error (Backend):", error);
    return null;
  }
};

/* ----------------------------------------------------
 *  NOT İÇİN TAG ÜRETİMİ (Backend)
 * --------------------------------------------------*/
export const generateTagsForNote = async (
  noteContent: string
): Promise<string[]> => {
  if (!noteContent) return [];

  try {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/ai/generate-tags`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ note_content: noteContent })
    });

    if (!response.ok) return [];

    const data = await response.json();
    return data.tags || [];

  } catch (error) {
    console.error("Gemini tag generation error (Backend):", error);
    return [];
  }
};

/* ----------------------------------------------------
 *  COVER IMAGE FETCHING
 *  Consolidated Logic:
 *  1) Google Books (ISBN) - Highest accuracy
 *  2) Google Books (Title + Author)
 *  3) OpenLibrary (ISBN)
 *  4) OpenLibrary (Search)
 *  5) AI Verification (Last resort)
 * --------------------------------------------------*/

// Helper to fetch from Google Books
// Now throws instead of returning null to work with Promise.any
const searchGoogleBooksCover = async (query: string, signal?: AbortSignal): Promise<string> => {
  const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=${query}&maxResults=1`, { signal });

  if (!res.ok) {
    throw new Error(`Google Books Error: ${res.status}`);
  }

  const data = await res.json();
  const item = data.items?.[0];
  const links = item?.volumeInfo?.imageLinks;
  if (links?.thumbnail || links?.smallThumbnail) {
    let url = links.thumbnail || links.smallThumbnail;
    // Force HTTPS and remove curling effect
    url = url.replace(/^http:\/\//i, 'https://').replace('&edge=curl', '');
    return url;
  }
  throw new Error("No cover in Google Books result");
};

// Helper function to try OpenLibrary cover fetch
const tryOpenLibraryCover = async (
  title: string,
  author?: string,
  isbn?: string,
  signal?: AbortSignal
): Promise<string> => {
  // Try ISBN first if available
  if (isbn) {
    const cleanIsbn = isbn.replace(/[^0-9X]/gi, '');
    const coverUrl = `https://covers.openlibrary.org/b/isbn/${cleanIsbn}-L.jpg`;
    // HEAD request to check checking existence
    const response = await fetch(coverUrl, { method: 'HEAD', signal });
    if (response.ok) {
      console.log('✓ Cover found via OpenLibrary ISBN');
      return coverUrl;
    }
  }

  // Try search if ISBN didn't work (or skipped)
  // Skip broad search if we are in parallel mode to reduce noise? 
  // No, let's race it.
  const query = author ? `${title} ${author}` : title;
  const searchUrl = `https://openlibrary.org/search.json?q=${encodeURIComponent(query)}&limit=1`;
  const response = await fetch(searchUrl, { signal });

  if (response.ok) {
    const data = await response.json();
    const doc = data.docs?.[0];
    if (doc?.cover_i) {
      const coverUrl = `https://covers.openlibrary.org/b/id/${doc.cover_i}-L.jpg`;
      console.log('✓ Cover found via OpenLibrary search');
      return coverUrl;
    }
  }

  throw new Error("No cover found in OpenLibrary");
};

// Step 3: AI-based cover verification (last resort - Backend)
const verifyCoverWithAI = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  try {
    const idToken = await getAuthToken();

    // Set a timeout for AI logic as it can be slow
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s timeout for AI

    const response = await fetch(`${API_BASE_URL}/api/ai/verify-cover`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ title, author, isbn }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) return null;
    const data = await response.json();

    // Backend returns { url: "..." } or null
    return data.url || null;

  } catch (error) {
    if ((error as Error).name === 'AbortError') {
      console.warn("AI Cover Verification timed out");
    } else {
      console.error("AI cover verification error (Backend):", error);
    }
    return null;
  }
};

/**
 * Main Cover Fetch Function (Parallel Race)
 */
export const fetchBookCover = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  const cleanIsbn = isbn ? isbn.replace(/[^0-9X]/gi, '') : '';
  const controller = new AbortController();
  const signal = controller.signal;

  const promises: Promise<string>[] = [];

  // 1. Google Books by ISBN
  if (cleanIsbn) {
    promises.push(searchGoogleBooksCover(`isbn:${cleanIsbn}`, signal));
  }

  // 2. Google Books by Title + Author
  if (title && author) {
    const query = `intitle:${encodeURIComponent(title)}+inauthor:${encodeURIComponent(author)}`;
    promises.push(searchGoogleBooksCover(query, signal));
  }

  // 3. OpenLibrary (ISBN + Search combined in logic)
  promises.push(tryOpenLibraryCover(title, author, cleanIsbn, signal));

  // 4. Broad Google Search (Title only) - Low priority but included in race
  if (title && !author) {
    promises.push(searchGoogleBooksCover(`intitle:${encodeURIComponent(title)}`, signal));
  }

  try {
    // Race them! First success wins.
    const result = await Promise.any(promises);

    // Cancel the losers to save bandwidth
    controller.abort();

    return result;

  } catch (err) {
    // All specific providers failed
    console.warn("Fast cover fetch failed (all sources). Falling back to AI...");

    // Fallback: AI Verification
    const aiCover = await verifyCoverWithAI(title, author, isbn);
    if (aiCover) {
      console.log("✓ Cover found via AI verification");
      return aiCover;
    }
  }

  console.log("✗ No verified cover found");
  return null;
};

// Export these for App.tsx usage if needed
export const enrichBookWithAI = async (
  item: ItemDraft,
  options?: { forceRegenerate?: boolean }
): Promise<ItemDraft> => {
  const shouldRun = options?.forceRegenerate || needsBookEnrichment(item);
  if (!shouldRun) return item;

  try {
    const idToken = await getAuthToken();
    const payload = {
      ...item,
      content_language_mode: item.contentLanguageMode || "AUTO",
      source_language_hint: item.sourceLanguageHint || undefined,
      force_regenerate: !!options?.forceRegenerate,
    };

    const response = await fetch(`${API_BASE_URL}/api/ai/enrich-book`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Enrichment failed with status ${response.status}: ${errorText}`);
      return item;
    }

    const enrichedData = await response.json();
    return enrichedData;

  } catch (e) {
    console.error("Enrich error (Backend):", e);
    return item;
  }
};

export const needsBookEnrichment = (item: ItemDraft): boolean => {
  const needsSummary = !item.summary || item.summary.trim().length < 40;
  const needsTags = !item.tags || item.tags.length < 2;
  const mode = (item.contentLanguageMode || "AUTO").toUpperCase();
  const resolved = (item.contentLanguageResolved || "").toLowerCase();
  const needsLanguageNormalization =
    (mode === "TR" && resolved !== "tr") ||
    (mode === "EN" && resolved !== "en") ||
    (!!item.sourceLanguageHint && !resolved);
  return needsSummary || needsTags || needsLanguageNormalization;
};

export const enrichBooksBatch = async (items: ItemDraft[]): Promise<ItemDraft[]> => {
  if (items.length === 0) return [];

  try {
    // Uses SSE endpoint to process items in parallel/stream
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/ai/enrich-batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ books: items })
    });

    if (!response.ok || !response.body) {
      console.error("Batch response failed");
      return items;
    }

    // Read SSE Stream (NDJSON)
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const enrichedResults: ItemDraft[] = [];
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;

      // Process complete lines
      const lines = buffer.split("\n");
      // Keep the last part which might be incomplete
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          try {
            const item = JSON.parse(line);
            enrichedResults.push(item);
          } catch (e) {
            console.error("Error parsing NDJSON line:", e);
          }
        }
      }
    }

    // Process any remaining buffer
    if (buffer.trim()) {
      try {
        const item = JSON.parse(buffer);
        enrichedResults.push(item);
      } catch (e) {
        console.error("Error parsing final buffer:", e);
      }
    }

    // Merge logic: ensure we return the full list in order?
    // The Streaming response yields items in order.
    // Simpler: just return what we got.
    return enrichedResults.length > 0 ? enrichedResults : items;

  } catch (e) {
    console.error("Batch enrich error (Backend):", e);
    return items;
  }
};
