import { ResourceType, LibraryItem } from "../types";
import { functions } from "./firebaseClient";
import { httpsCallable } from "firebase/functions";

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
    summary: item.generalNotes || (item as any).summary || "",
    publishedDate: item.publicationYear
      ? String(item.publicationYear)
      : (item as any).publishedDate || "",
    url: item.url,
    coverUrl: item.coverUrl ?? null,
  };
};

export const mergeEnrichedDraftIntoItem = (
  item: LibraryItem,
  draft: ItemDraft
): LibraryItem => {
  return {
    ...item,
    // AI’den gelen summary’i generalNotes’a yaz
    generalNotes:
      draft.summary && draft.summary.trim().length > 0
        ? draft.summary
        : item.generalNotes,
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
  };
};

/* ----------------------------------------------------
 *  HIZLI MAKALE ARAMA: CROSSREF + ARXIV (AUTH GEREKMEZ)
 * --------------------------------------------------*/
const searchArticlesFromAPIs = async (query: string): Promise<ItemDraft[]> => {
  if (!query.trim()) return [];

  const results: ItemDraft[] = [];

  try {
    // 1. CrossRef API - Academic papers and journals (fast, no auth needed)
    const crossrefUrl = `https://api.crossref.org/works?query=${encodeURIComponent(
      query
    )}&rows=3&select=title,author,publisher,published,DOI,abstract,URL`;

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

    // 2. arXiv API - Preprints and research papers (via proxy to avoid CORS)
    const proxyUrl = import.meta.env.VITE_PROXY_URL || 'http://localhost:3001';
    const arxivUrl = `${proxyUrl}/api/arxiv?search_query=all:${encodeURIComponent(
      query
    )}&start=0&max_results=3`;

    const arxivPromise = fetch(arxivUrl)
      .then(res => res.ok ? res.text() : null)
      .then(xmlText => {
        if (!xmlText) return [];

        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, "text/xml");
        const entries = xmlDoc.querySelectorAll("entry");

        return Array.from(entries).map(entry => {
          const title = entry.querySelector("title")?.textContent?.trim() || "";
          const authors = Array.from(entry.querySelectorAll("author name")).map(
            a => a.textContent?.trim() || ""
          );
          const summary = entry.querySelector("summary")?.textContent?.trim() || "";
          const published = entry.querySelector("published")?.textContent?.split("T")[0] || "";
          const link = entry.querySelector("id")?.textContent?.trim() || "";

          return {
            title,
            author: authors[0] || "Unknown",
            publisher: "arXiv",
            isbn: "",
            translator: "",
            tags: ["preprint", "arxiv"],
            summary,
            publishedDate: published,
            url: link,
            coverUrl: null,
          } as ItemDraft;
        });
      })
      .catch(() => []);

    // Execute both API calls in parallel for speed
    const [crossrefResults, arxivResults] = await Promise.all([
      crossrefPromise,
      arxivPromise,
    ]);

    // Combine results, prioritizing CrossRef (more reliable for published papers)
    results.push(...crossrefResults, ...arxivResults);

    // Limit to 5 total results
    return results.slice(0, 5);
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

  // 2) Hızlı yol: ARTICLE için önce CrossRef + arXiv
  if (type === "ARTICLE") {
    const fastResults = await searchArticlesFromAPIs(trimmed);
    if (fastResults.length > 0) {
      console.log("✓ Results from CrossRef/arXiv (fast)");
      return fastResults;
    }
  }

  // 3) Fallback: Gemini ile arama (Backend üzerinden)
  try {
    const bookEnrichment = httpsCallable(functions, 'bookEnrichment');

    // Construct prompt for search
    const prompt = `
      I need to find book or article recommendations based on this query: "${trimmed}".
      Type: ${type}
      
      Please return a JSON array of items. Each item should have:
      - title
      - author
      - publisher
      - isbn (if book)
      - summary (brief)
      - publishedDate (year)
      - url (if website/article)
      
      Return ONLY valid JSON. No markdown formatting.
    `;

    const result = await bookEnrichment({ prompt });
    const data = result.data as any;

    if (!data.success || !data.message) return [];

    // Parse JSON from the text response
    let parsedItems = [];
    try {
      const cleanJson = data.message.replace(/```json|```/g, '').trim();
      parsedItems = JSON.parse(cleanJson);
    } catch (e) {
      console.error("Failed to parse AI search results:", e);
      return [];
    }

    return Array.isArray(parsedItems) ? parsedItems.map((item: any) => ({
      ...item,
      coverUrl: null,
    })) as ItemDraft[] : [];

  } catch (error) {
    console.error("Error searching with Gemini (Cloud Function):", error);
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
    const bookEnrichment = httpsCallable(functions, 'bookEnrichment');

    const prompt = `
      Analyze these book highlights and provide a concise summary of the key themes and insights:
      
      ${highlightsText.join('\n---\n')}
      
      Return ONLY the summary text.
    `;

    const result = await bookEnrichment({ prompt });
    const data = result.data as any;

    return data.success ? data.message : null;

  } catch (error) {
    console.error("Gemini error (Cloud Function):", error);
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
    const bookEnrichment = httpsCallable(functions, 'bookEnrichment');

    const prompt = `
      Generate 3-5 relevant tags for this note. Return ONLY a JSON array of strings.
      
      Note: "${noteContent}"
    `;

    const result = await bookEnrichment({ prompt });
    const data = result.data as any;

    if (!data.success || !data.message) return [];

    try {
      const cleanJson = data.message.replace(/```json|```/g, '').trim();
      return JSON.parse(cleanJson);
    } catch (e) {
      console.error("Failed to parse tags:", e);
      return [];
    }

  } catch (error) {
    console.error("Gemini tag generation error (Cloud Function):", error);
    return [];
  }
};

/* ----------------------------------------------------
 *  COVER IMAGE FETCHING (senin mevcut zincirin)
 *  1) OpenLibrary (ISBN)
 *  2) Google Books
 *  3) Gemini ile son çare doğrulama (Backend)
 * --------------------------------------------------*/

// Step 1: Try to fetch cover from OpenLibrary using ISBN
const fetchCoverFromOpenLibrary = async (
  isbn: string
): Promise<string | null> => {
  if (!isbn) return null;

  try {
    const coverUrl = `https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg`;
    const response = await fetch(coverUrl, { method: "HEAD" });
    if (response.ok) return coverUrl;
    return null;
  } catch (error) {
    console.error("OpenLibrary cover fetch error:", error);
    return null;
  }
};

// Step 2: Try to fetch cover from Google Books API
const fetchCoverFromGoogleBooks = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  if (!title) return null;

  try {
    let query = `intitle:${encodeURIComponent(title)}`;
    if (author) query += `+inauthor:${encodeURIComponent(author)}`;
    if (isbn) query += `+isbn:${encodeURIComponent(isbn)}`;

    const apiUrl = `https://www.googleapis.com/books/v1/volumes?q=${query}&maxResults=1`;
    const response = await fetch(apiUrl);
    if (!response.ok) return null;

    const data = await response.json();
    if (!data.items || !data.items.length) return null;

    const volumeInfo = data.items[0].volumeInfo || {};
    const links = volumeInfo.imageLinks || {};

    return (
      links.extraLarge ||
      links.large ||
      links.medium ||
      links.thumbnail ||
      null
    );
  } catch (error) {
    console.error("Google Books cover fetch error:", error);
    return null;
  }
};

// Step 3: AI-based cover verification (last resort - Backend)
const verifyCoverWithAI = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  try {
    const bookEnrichment = httpsCallable(functions, 'bookEnrichment');

    const prompt = `
      Find a valid high-quality book cover image URL for:
      Title: ${title}
      Author: ${author}
      ISBN: ${isbn || 'N/A'}
      
      Return ONLY the URL string. If not found, return "null".
    `;

    const result = await bookEnrichment({ prompt });
    const data = result.data as any;

    if (data.success && data.message && data.message !== 'null') {
      return data.message.trim();
    }
    return null;

  } catch (error) {
    console.error("AI cover verification error (Cloud Function):", error);
    return null;
  }
};

/**
 * Dışarıdan kullanacağın ana fonksiyon:
 * 1) ISBN → OpenLibrary
 * 2) Google Books
 * 3) AI doğrulama
 */
export const fetchBookCover = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  if (isbn) {
    const openLib = await fetchCoverFromOpenLibrary(isbn);
    if (openLib) {
      console.log("✓ Cover found via OpenLibrary");
      return openLib;
    }
  }

  const gBooks = await fetchCoverFromGoogleBooks(title, author, isbn);
  if (gBooks) {
    console.log("✓ Cover found via Google Books API");
    return gBooks;
  }

  const aiCover = await verifyCoverWithAI(title, author, isbn);
  if (aiCover) {
    console.log("✓ Cover found via AI verification");
    return aiCover;
  }

  console.log("✗ No verified cover found");
  return null;
};

// Export these for App.tsx usage if needed
export const enrichBookWithAI = async (item: ItemDraft): Promise<ItemDraft> => {
  if (!needsBookEnrichment(item)) return item; // Keep the check

  try {
    const bookEnrichment = httpsCallable(functions, 'bookEnrichment');

    const prompt = `
      Enrich this book data with missing details (summary, tags, publisher, publication year).
      
      Current Data:
      ${JSON.stringify(item)}
      
      Return the COMPLETE updated JSON object. 
      - Ensure 'summary' is detailed (at least 3 sentences).
      - Ensure 'tags' has at least 3 relevant genres/topics.
      - Do NOT change the title or author if they look correct.
      
      Return ONLY valid JSON. No markdown.
    `;

    const result = await bookEnrichment({ prompt });
    const data = result.data as any;

    if (!data.success || !data.message) return item;

    try {
      const cleanJson = data.message.replace(/```json|```/g, '').trim();
      const enrichedItem = JSON.parse(cleanJson);
      return { ...item, ...enrichedItem };
    } catch (e) {
      console.error("Failed to parse enriched book JSON:", e);
      return item;
    }

  } catch (e) {
    console.error("Enrich error (Cloud Function):", e);
    return item;
  }
};

export const needsBookEnrichment = (item: ItemDraft): boolean => {
  const needsSummary = !item.summary || item.summary.trim().length < 40;
  const needsTags = !item.tags || item.tags.length < 2;
  return needsSummary || needsTags;
};
