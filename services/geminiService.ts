import { ResourceType, LibraryItem } from "../types";
import { getAuth } from "firebase/auth";

// Helper function to get Firebase Auth ID token
const getAuthToken = async (): Promise<string> => {
  const auth = getAuth();
  const user = auth.currentUser;

  if (!user) {
    throw new Error('User must be logged in to use AI features');
  }

  return await user.getIdToken();
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

    const idToken = await getAuthToken();

    const response = await fetch('https://us-central1-tomehub.cloudfunctions.net/bookEnrichmentHttp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ prompt })
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    if (!data.message) return [];

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
    const prompt = `
      Analyze these book highlights and provide a concise summary of the key themes and insights:
      
      ${highlightsText.join('\n---\n')}
      
      Return ONLY the summary text.
    `;

    const idToken = await getAuthToken();

    const response = await fetch('https://us-central1-tomehub.cloudfunctions.net/bookEnrichmentHttp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ prompt })
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    return data.message || null;

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
    const prompt = `
      Generate 3-5 relevant tags for this note. Return ONLY a JSON array of strings.
      
      Note: "${noteContent}"
    `;

    const idToken = await getAuthToken();

    const response = await fetch('https://us-central1-tomehub.cloudfunctions.net/bookEnrichmentHttp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ prompt })
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    if (!data.message) return [];

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
 *  COVER IMAGE FETCHING
 *  Consolidated Logic:
 *  1) Google Books (ISBN) - Highest accuracy
 *  2) Google Books (Title + Author)
 *  3) OpenLibrary (ISBN)
 *  4) OpenLibrary (Search)
 *  5) AI Verification (Last resort)
 * --------------------------------------------------*/

// Helper to fetch from Google Books
const searchGoogleBooksCover = async (query: string): Promise<string | null> => {
  try {
    const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=${query}&maxResults=1`);

    if (!res.ok) {
      if (res.status === 503) {
        console.warn('Google Books returned 503 (Service Unavailable)');
      }
      return null;
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
  } catch (e) {
    console.warn('Google Books fetch error:', e);
  }
  return null;
};

// Helper function to try OpenLibrary cover fetch
const tryOpenLibraryCover = async (
  title: string,
  author?: string,
  isbn?: string
): Promise<string | null> => {
  try {
    // Try ISBN first if available
    if (isbn) {
      const cleanIsbn = isbn.replace(/[^0-9X]/gi, '');
      const coverUrl = `https://covers.openlibrary.org/b/isbn/${cleanIsbn}-L.jpg`;
      const response = await fetch(coverUrl, { method: 'HEAD' });
      if (response.ok) {
        console.log('✓ Cover found via OpenLibrary ISBN');
        return coverUrl;
      }
    }

    // Try search if ISBN didn't work
    const query = author ? `${title} ${author}` : title;
    const searchUrl = `https://openlibrary.org/search.json?q=${encodeURIComponent(query)}&limit=1`;
    const response = await fetch(searchUrl);

    if (response.ok) {
      const data = await response.json();
      const doc = data.docs?.[0];
      if (doc?.cover_i) {
        const coverUrl = `https://covers.openlibrary.org/b/id/${doc.cover_i}-L.jpg`;
        console.log('✓ Cover found via OpenLibrary search');
        return coverUrl;
      }
    }
  } catch (error) {
    console.warn('OpenLibrary cover fetch failed:', error);
  }

  return null;
};

// Step 3: AI-based cover verification (last resort - Backend)
const verifyCoverWithAI = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  try {
    const prompt = `
      Find a valid high-quality book cover image URL for:
      Title: ${title}
      Author: ${author}
      ISBN: ${isbn || 'N/A'}
      
      Return ONLY the URL string. If not found, return "null".
    `;

    const idToken = await getAuthToken();

    const response = await fetch('https://us-central1-tomehub.cloudfunctions.net/bookEnrichmentHttp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ prompt })
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    if (data.message && data.message !== 'null') {
      return data.message.trim();
    }
    return null;

  } catch (error) {
    console.error("AI cover verification error (Cloud Function):", error);
    return null;
  }
};

/**
 * Main Cover Fetch Function
 */
export const fetchBookCover = async (
  title: string,
  author: string,
  isbn?: string
): Promise<string | null> => {
  const cleanIsbn = isbn ? isbn.replace(/[^0-9X]/gi, '') : '';

  // 1. Google Books by ISBN
  if (cleanIsbn) {
    const url = await searchGoogleBooksCover(`isbn:${cleanIsbn}`);
    if (url) return url;
  }

  // 2. Google Books by Title + Author
  if (title && author) {
    const query = `intitle:${encodeURIComponent(title)}+inauthor:${encodeURIComponent(author)}`;
    const url = await searchGoogleBooksCover(query);
    if (url) return url;
  }

  // 3. Google Books by Title only (Broad)
  if (title) {
    const url = await searchGoogleBooksCover(`intitle:${encodeURIComponent(title)}`);
    if (url) return url;
  }

  // 4. OpenLibrary (ISBN & Search)
  const olUrl = await tryOpenLibraryCover(title, author, cleanIsbn);
  if (olUrl) return olUrl;

  // 5. AI Verification (Last Resort)
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
    const prompt = `
      Enrich this book data with missing details (summary, tags, publisher, publication year).
      
      Current Data:
      ${JSON.stringify(item)}
      
      CRITICAL LANGUAGE INSTRUCTION:
      1. DETECT the language of the book title and author.
      2. IF the book is clearly English, generate 'summary' and 'tags' in ENGLISH.
      3. IF the book is Turkish OR the language is unclear/ambiguous, generate 'summary' and 'tags' in TURKISH (Default).
      
      Return the COMPLETE updated JSON object. 
      - Ensure 'summary' is detailed (at least 3 sentences).
      - Ensure 'tags' has at least 3 relevant genres/topics.
      - Do NOT change the title or author if they look correct.
      
      Return ONLY valid JSON. No markdown.
    `;

    const idToken = await getAuthToken();

    const response = await fetch('https://us-central1-tomehub.cloudfunctions.net/bookEnrichmentHttp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ prompt })
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    if (!data.message) return item;

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

export const enrichBooksBatch = async (items: ItemDraft[]): Promise<ItemDraft[]> => {
  if (items.length === 0) return [];

  try {
    const prompt = `
      Enrich this LIST of books with missing details (summary, tags, publisher, publication year).
      
      Input Data:
      ${JSON.stringify(items)}
      
      CRITICAL LANGUAGE INSTRUCTION (Apply to EACH book individually):
      1. DETECT the language of the book title and author.
      2. IF the book is clearly English, generate 'summary' and 'tags' in ENGLISH.
      3. IF the book is Turkish OR the language is unclear/ambiguous, generate 'summary' and 'tags' in TURKISH (Default).
      
      Return a JSON ARRAY of objects. Each object must correspond to the input list in the same order.
      - Ensure 'summary' is detailed (at least 3 sentences).
      - Ensure 'tags' has at least 3 relevant genres/topics.
      - Do NOT change the title or author if they look correct.
      - Include the original 'title' in the output for verification.
      
      Return ONLY valid JSON array. No markdown.
    `;

    const idToken = await getAuthToken();

    const response = await fetch('https://us-central1-tomehub.cloudfunctions.net/bookEnrichmentHttp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ prompt })
    });

    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Unknown error');
    }

    if (!data.message) return items;

    try {
      const cleanJson = data.message.replace(/```json|```/g, '').trim();
      const enrichedList = JSON.parse(cleanJson);

      if (!Array.isArray(enrichedList)) {
        console.error("Batch enrich returned non-array:", enrichedList);
        return items;
      }

      // Merge results back into original items
      // We try to match by index, but fallback to title matching if possible
      return items.map((original, index) => {
        const enriched = enrichedList[index] || enrichedList.find((e: any) => e.title === original.title);
        if (enriched) {
          return { ...original, ...enriched };
        }
        return original;
      });

    } catch (e) {
      console.error("Failed to parse batch enriched JSON:", e);
      return items;
    }

  } catch (e) {
    console.error("Batch enrich error (Cloud Function):", e);
    return items;
  }
};
