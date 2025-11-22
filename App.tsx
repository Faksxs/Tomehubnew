import React, { useState, useEffect, useCallback } from "react";
import { HashRouter } from "react-router-dom";
import {
  LibraryItem,
  Highlight,
  ResourceType,
} from "./types";
import { QueryDocumentSnapshot, DocumentData } from "firebase/firestore"; // Add imports
import { BookList } from "./components/BookList";
import { BookForm } from "./components/BookForm";
import { BookDetail } from "./components/BookDetail";
import { Sidebar } from "./components/Sidebar";
import { ProfileView } from "./components/ProfileView";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import {
  fetchItemsForUser,
  saveItemForUser,
  deleteItemForUser,
} from "./services/firestoreService";

import {
  ItemDraft,
  enrichBookWithAI,
  libraryItemToDraft,
  mergeEnrichedDraftIntoItem,
} from "./services/geminiService";




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

  const [activeTab, setActiveTab] = useState<
    ResourceType | "NOTES" | "DASHBOARD" | "PROFILE"
  >("DASHBOARD");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [lastDoc, setLastDoc] = useState<QueryDocumentSnapshot<DocumentData> | null>(null);
  const [hasMore, setHasMore] = useState(true);

  // Firestore'dan ilk yükleme (cloud → state)
  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setItemsLoading(true);
      try {
        const { items, lastDoc: newLastDoc } = await fetchItemsForUser(userId, 1000);
        if (!cancelled) {
          setBooks(items);
          setLastDoc(newLastDoc);
          setHasMore(!!newLastDoc);
        }
      } catch (e) {
        console.error("Error loading items from Firestore:", e);
      } finally {
        if (!cancelled) {
          setItemsLoading(false);
        }
      }
    };

    if (userId) {
      load();
    }

    return () => {
      cancelled = true;
    };
  }, [userId]);

  const handleAddBook = useCallback(
    async (itemData: Omit<LibraryItem, "id" | "highlights">) => {
      // 1) Yeni item'i oluştur (AI dokunmadan önceki ham hali)
      const newItem: LibraryItem = {
        ...itemData,
        id: Date.now().toString(),
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
  }, [selectedBookId, userId]);

  const selectedBook = books.find((b) => b.id === selectedBookId);
  const editingBook = books.find((b) => b.id === editingBookId);

  const handleTabChange = useCallback((newTab: ResourceType | "NOTES" | "DASHBOARD" | "PROFILE") => {
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

  // İlk yüklemede boşsa basit bir loading ekranı
  if (itemsLoading && books.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500">
        Loading your library from cloud...
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 font-sans overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      <main className="flex-1 overflow-y-auto h-full w-full">
        {activeTab === "PROFILE" ? (
          <ProfileView
            email={userEmail}
            onLogout={onLogout}
            onBack={() => handleTabChange("DASHBOARD")}
          />
        ) : view === "list" ? (
          <BookList
            books={books}
            activeTab={activeTab}
            onSelectBook={(book) => {
              setSelectedBookId(book.id);
              setView("detail");
            }}
            onAddBook={() => {
              setEditingBookId(null);
              setIsFormOpen(true);
            }}
            onMobileMenuClick={() => setIsSidebarOpen(true)}
            onDeleteBook={handleDeleteBook} // 🔥 BookList kartındaki delete butonu buraya bağlı
            onLoadMore={handleLoadMore}
            hasMore={hasMore}
          />
        ) : (
          selectedBook && (
            <BookDetail
              book={selectedBook}
              onBack={() => {
                setSelectedBookId(null);
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
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="bg-white shadow-lg rounded-2xl px-8 py-10 flex flex-col items-center gap-4">
          <h1 className="text-xl font-bold text-slate-900 mb-2">TomeHub</h1>
          <p className="text-sm text-slate-600 text-center max-w-xs">
            Sign in with your Google account to access your library across all
            devices.
          </p>
          <button
            onClick={loginWithGoogle}
            className="mt-2 bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg text-sm font-medium shadow-md"
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
      <AppContent />
    </AuthProvider>
  );
};

export default App;
