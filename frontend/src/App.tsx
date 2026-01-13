import React, { useState, useEffect, useCallback } from "react";
import { HashRouter } from "react-router-dom";
import {
  LibraryItem,
  Highlight,
  ResourceType,
} from "./types";
import { QueryDocumentSnapshot, DocumentData } from "firebase/firestore";
import { BookList } from "./components/BookList";
import { BookForm } from "./components/BookForm";
import { BookDetail } from "./components/BookDetail";
import { Sidebar } from "./components/Sidebar";
import { ProfileView } from "./components/ProfileView";
import SmartSearch from "./components/SmartSearch";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import {
  fetchItemsForUser,
  saveItemForUser,
  deleteItemForUser,
  deleteMultipleItemsForUser,
} from "./services/firestoreService";

import {
  ItemDraft,
  enrichBookWithAI,
  libraryItemToDraft,
  mergeEnrichedDraftIntoItem,
} from "./services/geminiService";
import { useBatchEnrichment } from "./hooks/useBatchEnrichment";

import { RAGSearch } from "./components/RAGSearch";

// ----------------- LAYOUT (ANA UYGULAMA) -----------------


interface LayoutProps {
  userId: string;
  userEmail: string | null | undefined;
  onLogout: () => void;
}

const Layout: React.FC<LayoutProps> = ({ userId, userEmail, onLogout }) => {
  const [books, setBooks] = useState<LibraryItem[]>([]);
  const [view, setView] = useState<"list" | "detail">("list");
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingBookId, setEditingBookId] = useState<string | null>(null);
  const [openToHighlights, setOpenToHighlights] = useState(false);
  const [selectedHighlightId, setSelectedHighlightId] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<
    ResourceType | "NOTES" | "DASHBOARD" | "PROFILE" | "RAG_SEARCH" | "SMART_SEARCH"
  >("DASHBOARD");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [lastDoc, setLastDoc] = useState<QueryDocumentSnapshot<DocumentData> | null>(null);
  const [hasMore, setHasMore] = useState(true);

  useEffect(() => {
    let active = true;

    async function loadItems() {
      if (!userId) {
        setItemsLoading(false);
        return;
      }

      try {
        const { items, lastDoc: newLastDoc } = await fetchItemsForUser(userId);
        if (active) {
          setBooks(items);
          setLastDoc(newLastDoc);
          setHasMore(!!newLastDoc);
        }
      } catch (e) {
        console.error("Failed to load items:", e);
      } finally {
        if (active) {
          setItemsLoading(false);
        }
      }
    }

    loadItems();

    return () => {
      active = false;
    };
  }, [userId]);

  const handleAddBook = useCallback(
    async (itemData: Omit<LibraryItem, "id" | "highlights"> & { id?: string }) => {
      // 1) Yeni item'i oluştur (AI dokunmadan önceki ham hali)
      const newItem: LibraryItem = {
        ...itemData,
        id: itemData.id || Date.now().toString(),
        addedAt: itemData.addedAt || Date.now(),
        highlights: [],
      };

      // 2) Önce UI'da göster (kullanıcı beklemesin)
      setBooks((prev) => [newItem, ...prev]);
      setIsFormOpen(false);

      // 3) Ham halini Firestore'a kaydet (veri kaybolmasın)
      try {
        await saveItemForUser(userId, newItem);
      } catch (err) {
        console.error("Failed to save item to Firestore:", err);
      }

      // 4) Arka planda AI enrichment (UI'yı bloklamadan)
      // SKIP AI enrichment for Personal Notes - preserve user's original content
      if (itemData.type !== 'PERSONAL_NOTE') {
        (async () => {
          try {
            // LibraryItem -> ItemDraft dönüşümü (senin helper'ın)
            const draft = libraryItemToDraft(newItem);

            // Vercel backend üzerinden Gemini çağrısı
            const enrichedDraft = await enrichBookWithAI(draft);

            // ItemDraft -> LibraryItem'e geri merge et (senin helper'ın)
            const enrichedItem = mergeEnrichedDraftIntoItem(
              newItem,
              enrichedDraft
            );

            // Eğer hiçbir anlamlı değişiklik yoksa boşuna state güncellemeyelim
            const hasChanged =
              enrichedItem.generalNotes !== newItem.generalNotes ||
              JSON.stringify(enrichedItem.tags) !==
              JSON.stringify(newItem.tags);

            if (!hasChanged) return;

            // 5) State'i güncelle (listedeki item'i enriched sürümle değiştir)
            setBooks((prev) =>
              prev.map((b) => (b.id === newItem.id ? enrichedItem : b))
            );

            // 6) Firestore'u da enriched sürümle güncelle
            try {
              await saveItemForUser(userId, enrichedItem);
            } catch (err) {
              console.error(
                "Failed to save enriched item to Firestore:",
                err
              );
            }
          } catch (err) {
            console.error("Background enrichment failed:", err);
          }
        })();
      }
    },
    [userId]
  );

  const handleUpdateBook = useCallback(async (
    itemData: Omit<LibraryItem, "id" | "highlights">
  ) => {
    if (!editingBookId) return;

    let updatedItem: LibraryItem | null = null;

    setBooks((prev) =>
      prev.map((b) => {
        if (b.id === editingBookId) {
          updatedItem = { ...b, ...itemData };
          return updatedItem;
        }
        return b;
      })
    );

    setIsFormOpen(false);
    setEditingBookId(null);

    if (updatedItem) {
      try {
        await saveItemForUser(userId, updatedItem);
      } catch (err) {
        console.error("Failed to update item in Firestore:", err);
      }
    }
  }, [editingBookId, userId]);

  const handleDeleteBook = useCallback(async (id: string) => {
    if (!window.confirm("Are you sure you want to delete this item?")) return;

    setBooks((prev) => prev.filter((b) => b.id !== id));

    if (selectedBookId === id) {
      setSelectedBookId(null);
      setView("list");
    }

    try {
      await deleteItemForUser(userId, id);
    } catch (err) {
      console.error("Failed to delete item from Firestore:", err);
    }
  }, [selectedBookId, userId]);

  const handleBulkDelete = useCallback(async (ids: string[]) => {
    if (!window.confirm(`Are you sure you want to delete ${ids.length} items?`)) return;

    setBooks((prev) => prev.filter((b) => !ids.includes(b.id)));

    if (selectedBookId && ids.includes(selectedBookId)) {
      setSelectedBookId(null);
      setView("list");
    }

    try {
      await deleteMultipleItemsForUser(userId, ids);
    } catch (err) {
      console.error("Failed to delete items from Firestore:", err);
    }
  }, [selectedBookId, userId]);

  const handleUpdateHighlights = useCallback(async (highlights: Highlight[]) => {
    if (!selectedBookId) return;

    let updatedItem: LibraryItem | null = null;

    setBooks((prev) =>
      prev.map((b) => {
        if (b.id === selectedBookId) {
          updatedItem = { ...b, highlights };
          return updatedItem;
        }
        return b;
      })
    );

    if (updatedItem) {
      try {
        await saveItemForUser(userId, updatedItem);
      } catch (err) {
        console.error("Failed to update highlights in Firestore:", err);
      }
    }
  }
    , [selectedBookId, userId]);

  const handleToggleFavorite = useCallback(async (id: string) => {
    // 1. Find and update the item
    const bookIndex = books.findIndex(b => b.id === id);
    if (bookIndex === -1) return;

    const book = books[bookIndex];
    const updatedBook = { ...book, isFavorite: !book.isFavorite };

    // 2. Update Local State
    setBooks(prev => {
      const newBooks = [...prev];
      newBooks[bookIndex] = updatedBook;
      return newBooks;
    });

    // 3. Update Firestore
    try {
      await saveItemForUser(userId, updatedBook);
    } catch (err) {
      console.error("Failed to update favorite status in Firestore:", err);
      // Optional: Revert state on failure
    }
  }, [books, userId]);

  const handleToggleHighlightFavorite = useCallback(async (bookId: string, highlightId: string) => {
    // 1. Find and update the item
    const bookIndex = books.findIndex(b => b.id === bookId);
    if (bookIndex === -1) return;

    const book = books[bookIndex];
    const updatedHighlights = book.highlights.map(h => {
      if (h.id === highlightId) {
        return { ...h, isFavorite: !h.isFavorite };
      }
      return h;
    });

    const updatedBook = { ...book, highlights: updatedHighlights };

    // 2. Update Local State
    setBooks(prev => {
      const newBooks = [...prev];
      newBooks[bookIndex] = updatedBook;
      return newBooks;
    });

    // 3. Update Firestore
    try {
      await saveItemForUser(userId, updatedBook);
    } catch (err) {
      console.error("Failed to update highlight favorite status in Firestore:", err);
    }
  }, [books, userId]);

  const handleUpdateBookForEnrichment = useCallback((updatedBook: LibraryItem) => {
    setBooks(prev => prev.map(b => b.id === updatedBook.id ? updatedBook : b));
  }, []);

  const {
    isEnriching,
    stats: enrichmentStats,
    startEnrichment,
    stopEnrichment
  } = useBatchEnrichment(userId, handleUpdateBookForEnrichment);

  const selectedBook = books.find((b) => b.id === selectedBookId);
  const editingBook = books.find((b) => b.id === editingBookId);

  const handleTabChange = useCallback((newTab: ResourceType | "NOTES" | "DASHBOARD" | "PROFILE" | "RAG_SEARCH" | "SMART_SEARCH") => {
    setActiveTab(newTab);
    setView("list");
    setSelectedBookId(null);
  }, []);

  const handleLoadMore = useCallback(async () => {
    if (!lastDoc) return;
    try {
      const { items, lastDoc: newLastDoc } = await fetchItemsForUser(userId, 1000, lastDoc);
      setBooks((prev) => [...prev, ...items]);
      setLastDoc(newLastDoc);
      setHasMore(!!newLastDoc);
    } catch (e) {
      console.error("Error loading more items:", e);
    }
  }, [userId, lastDoc]);

  if (itemsLoading && books.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500">
        Loading your library from cloud...
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-950 overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full w-full relative overflow-y-auto transition-all duration-300">
        {activeTab === "PROFILE" ? (
          <ProfileView
            email={userEmail}
            userId={userId}
            onLogout={onLogout}
            onBack={() => handleTabChange("DASHBOARD")}
            books={books}
            onStartEnrichment={startEnrichment}
            onStopEnrichment={stopEnrichment}
            isEnriching={isEnriching}
            enrichmentStats={enrichmentStats}
          />
        ) : activeTab === "SMART_SEARCH" ? (
          <SmartSearch userId={userId} onBack={() => handleTabChange("DASHBOARD")} />
        ) : activeTab === "RAG_SEARCH" ? (
          <RAGSearch userId={userId} userEmail={userEmail} />
        ) : view === "list" ? (
          <BookList
            books={books}
            activeTab={activeTab}
            onSelectBook={(book) => {
              setSelectedBookId(book.id);
              setOpenToHighlights(false); // Default to info tab
              setView("detail");
            }}
            onSelectBookWithTab={(book, tab, highlightId) => {
              setSelectedBookId(book.id);
              setOpenToHighlights(tab === 'highlights'); // Open to highlights tab if specified
              setSelectedHighlightId(highlightId || null); // Store highlight ID to auto-edit
              setView("detail");
            }}
            onAddBook={() => {
              setEditingBookId(null);
              setIsFormOpen(true);
            }}
            onMobileMenuClick={() => setIsSidebarOpen(true)}
            onDeleteBook={handleDeleteBook}
            onDeleteMultiple={handleBulkDelete}
            onToggleFavorite={handleToggleFavorite}
            onToggleHighlightFavorite={handleToggleHighlightFavorite}
            onLoadMore={handleLoadMore}
            hasMore={hasMore}
          />
        ) : (
          selectedBook && (
            <BookDetail
              book={selectedBook}
              initialTab={openToHighlights ? 'highlights' : 'info'}
              autoEditHighlightId={selectedHighlightId || undefined}
              onBack={() => {
                setSelectedBookId(null);
                setOpenToHighlights(false); // Reset state
                setSelectedHighlightId(null); // Reset highlight ID
                setView("list");
              }}
              onEdit={() => {
                setEditingBookId(selectedBook.id);
                setIsFormOpen(true);
              }}
              onDelete={() => handleDeleteBook(selectedBook.id)}
              onUpdateHighlights={handleUpdateHighlights}
            />
          )
        )}
      </main>

      {isFormOpen && (
        <BookForm
          initialType={
            editingBook
              ? editingBook.type
              : activeTab === "NOTES" || activeTab === "DASHBOARD" || activeTab === "PROFILE"
                ? "BOOK"
                : activeTab
          }
          initialData={editingBook}
          onSave={editingBookId ? handleUpdateBook : handleAddBook}
          onCancel={() => {
            setIsFormOpen(false);
            setEditingBookId(null);
          }}
        />
      )}
    </div>
  );
};

// ----------------- AUTH'A GÖRE UYGULAMA -----------------

const AppContent: React.FC = () => {
  const { user, loading, loginWithGoogle, logout } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Loading...
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 transition-colors duration-300">
        <div className="bg-white dark:bg-slate-900 shadow-lg rounded-2xl px-8 py-10 flex flex-col items-center gap-4 border border-slate-100 dark:border-slate-800">
          <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-2">TomeHub</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 text-center max-w-xs">
            Sign in with your Google account to access your library across all
            devices.
          </p>
          <button
            onClick={loginWithGoogle}
            className="mt-2 bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg text-sm font-medium shadow-md transition-colors"
          >
            Continue with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <HashRouter>
      <Layout userId={user.uid} userEmail={user.email} onLogout={logout} />
    </HashRouter>
  );
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <ThemeProvider>
        <AppContent />
      </ThemeProvider>
    </AuthProvider>
  );
};

export default App;
