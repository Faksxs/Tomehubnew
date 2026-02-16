import React, { useState, useEffect, useCallback, useRef } from "react";
import { HashRouter } from "react-router-dom";
import {
  LibraryItem,
  Highlight,
  ResourceType,
  PersonalNoteCategory,
  PersonalNoteFolder,
} from "./types";
import { QueryDocumentSnapshot, DocumentData } from "firebase/firestore";
import { BookList } from "./components/BookList";
import { BookForm } from "./components/BookForm";
import { BookDetail } from "./components/BookDetail";
import { Sidebar } from "./components/Sidebar";
import { ProfileView } from "./components/ProfileView";
import SmartSearch from "./components/SmartSearch";
import logo from './assets/logo_v7.png';
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import {
  fetchItemsForUser,
  saveItemForUser,
  deleteItemForUser,
  deleteMultipleItemsForUser,
  fetchPersonalNoteFoldersForUser,
  savePersonalNoteFolderForUser,
  updatePersonalNoteFolderForUser,
  deletePersonalNoteFolderForUser,
  movePersonalNoteForUser,
} from "./services/firestoreService";

import {
  ItemDraft,
  enrichBookWithAI,
  libraryItemToDraft,
  mergeEnrichedDraftIntoItem,
} from "./services/geminiService";
import { useBatchEnrichment } from "./hooks/useBatchEnrichment";

import { RAGSearch } from "./components/RAGSearch";
import { FlowContainer } from "./components/FlowContainer";
import { prewarmFlowStartSession } from "./services/flowService";
import { addTextItem, syncHighlights, syncPersonalNote, purgeResourceContent } from "./services/backendApiService";
import { getPersonalNoteBackendType, getPersonalNoteCategory, isPersonalNote } from "./lib/personalNotePolicy";
import { extractPersonalNoteText } from "./lib/personalNoteRender";

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
    ResourceType | "NOTES" | "DASHBOARD" | "PROFILE" | "RAG_SEARCH" | "SMART_SEARCH" | "FLOW"
  >("DASHBOARD");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [lastDoc, setLastDoc] = useState<QueryDocumentSnapshot<DocumentData> | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [listSearch, setListSearch] = useState('');
  const [listStatusFilter, setListStatusFilter] = useState<string>('ALL');
  const [listSortOption, setListSortOption] = useState<'date_desc' | 'date_asc' | 'title_asc'>('date_desc');
  const [listPublisherFilter, setListPublisherFilter] = useState('');
  const [personalNoteDraftDefaults, setPersonalNoteDraftDefaults] = useState<{ personalNoteCategory?: PersonalNoteCategory; personalFolderId?: string; folderPath?: string }>({});
  const [personalNoteFolders, setPersonalNoteFolders] = useState<PersonalNoteFolder[]>([]);
  const [didRunLegacyFolderMigration, setDidRunLegacyFolderMigration] = useState(false);
  const flowPrewarmStartedRef = useRef(false);


  useEffect(() => {
    let active = true;

    async function loadItems() {
      if (!userId) {
        setItemsLoading(false);
        return;
      }

      try {
        const [{ items, lastDoc: newLastDoc }, folders] = await Promise.all([
          fetchItemsForUser(userId),
          fetchPersonalNoteFoldersForUser(userId),
        ]);
        if (active) {
          setBooks(items);
          setPersonalNoteFolders(folders);
          setLastDoc(newLastDoc);
          setHasMore(!!newLastDoc);
          setDidRunLegacyFolderMigration(false);
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

  useEffect(() => {
    if (!userId || flowPrewarmStartedRef.current) return;

    // Avoid background prewarm calls during local dev unless explicitly enabled.
    // This prevents noisy connection reset errors when the backend is not running.
    const allowDevPrewarm = import.meta.env.VITE_FLOW_PREWARM === "true";
    if (import.meta.env.DEV && !allowDevPrewarm) return;

    flowPrewarmStartedRef.current = true;

    let cancelled = false;
    let timeoutId: number | null = null;
    let idleId: number | null = null;

    const runPrewarm = () => {
      if (cancelled) return;
      void prewarmFlowStartSession({
        firebase_uid: userId,
        anchor_type: "topic",
        anchor_id: "General Discovery",
        mode: "FOCUS",
        horizon_value: 0.25,
        resource_type: "ALL_NOTES",
      }).catch((err) => {
        console.warn("Flow prewarm failed (non-critical):", err);
      });
    };

    if (typeof window !== "undefined" && typeof (window as any).requestIdleCallback === "function") {
      idleId = (window as any).requestIdleCallback(() => runPrewarm(), { timeout: 2500 });
    } else {
      timeoutId = window.setTimeout(runPrewarm, 1200);
    }

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      if (idleId !== null && typeof window !== "undefined" && typeof (window as any).cancelIdleCallback === "function") {
        (window as any).cancelIdleCallback(idleId);
      }
    };
  }, [userId]);

  const syncPersonalNoteToBackend = useCallback(async (note: LibraryItem, deleteOnly: boolean = false) => {
    if (!isPersonalNote(note)) return;
    try {
      await syncPersonalNote(userId, note.id, {
        title: note.title,
        author: note.author,
        content: extractPersonalNoteText(note.generalNotes || ""),
        tags: note.tags || [],
        category: getPersonalNoteCategory(note),
        delete_only: deleteOnly,
      });
    } catch (err) {
      console.error("Failed to sync personal note to AI Backend:", err);
    }
  }, [userId]);

  const buildFolderPath = useCallback((folderId?: string) => {
    if (!folderId) return undefined;
    const folder = personalNoteFolders.find((f) => f.id === folderId);
    return folder?.name;
  }, [personalNoteFolders]);

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
      setPersonalNoteDraftDefaults({});

      // 3) Ham halini Firestore'a kaydet (veri kaybolmasın)
      try {
        await saveItemForUser(userId, newItem);
      } catch (err) {
        console.error("Failed to save item to Firestore:", err);
      }

      // 4) Sync to Oracle Backend (Layer 3 Search)
      // We do this immediately so the item is searchable
      (async () => {
        try {
          if (isPersonalNote(newItem)) {
            await syncPersonalNoteToBackend(newItem, false);
            return;
          }

          const textParts = [];
          textParts.push(`Title: ${newItem.title}`);
          textParts.push(`Author: ${newItem.author}`);
          if (isPersonalNote(newItem) && newItem.personalNoteCategory) {
            textParts.push(`Category: ${newItem.personalNoteCategory}`);
          }
          if (isPersonalNote(newItem) && newItem.folderPath) {
            textParts.push(`SubFile: ${newItem.folderPath}`);
          }
          if (newItem.publisher) textParts.push(`Publisher: ${newItem.publisher}`);
          if (newItem.tags && newItem.tags.length > 0) textParts.push(`Tags: ${newItem.tags.join(', ')}`);
          if (newItem.generalNotes) textParts.push(`\nContent/Notes:\n${newItem.generalNotes}`);

          const fullText = textParts.join('\n');

          // Only sync if there is some meaningful content
          if (fullText.length > 20) {
            await addTextItem(
              fullText,
              newItem.title,
              newItem.author,
              isPersonalNote(newItem) ? getPersonalNoteBackendType(newItem) : newItem.type,
              userId,
              {
                book_id: newItem.id,
                tags: newItem.tags || [],
              }
            );
            console.log("Synced new item to AI Backend:", newItem.title);
          }
        } catch (err) {
          console.error("Failed to sync item to AI Backend (:5000):", err);
          // Non-blocking for UI
        }
      })();

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
    [syncPersonalNoteToBackend, userId]
  );

  const handleOpenPersonalNoteForm = useCallback((defaults?: { category?: PersonalNoteCategory; folderId?: string; folderPath?: string }) => {
    setPersonalNoteDraftDefaults({
      personalNoteCategory: defaults?.category || 'DAILY',
      personalFolderId: defaults?.folderId,
      folderPath: defaults?.folderPath || buildFolderPath(defaults?.folderId),
    });
    setEditingBookId(null);
    setIsFormOpen(true);
  }, [buildFolderPath]);

  const handleQuickCreatePersonalNote = useCallback((payload: { title: string; content: string; category: PersonalNoteCategory; folderId?: string; folderPath?: string }) => {
    handleAddBook({
      type: 'PERSONAL_NOTE',
      title: payload.title,
      author: 'Self',
      status: 'On Shelf',
      readingStatus: 'Finished',
      tags: [],
      generalNotes: payload.content,
      addedAt: Date.now(),
      personalNoteCategory: payload.category,
      personalFolderId: payload.folderId,
      folderPath: payload.folderPath || buildFolderPath(payload.folderId),
    });
  }, [buildFolderPath, handleAddBook]);

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
      if (isPersonalNote(updatedItem)) {
        syncPersonalNoteToBackend(updatedItem, false);
      }
    }
  }, [editingBookId, syncPersonalNoteToBackend, userId]);

  const handleDeleteBook = useCallback(async (id: string) => {
    if (!window.confirm("Are you sure you want to delete this item?")) return;
    const deletedItem = books.find((b) => b.id === id);

    setBooks((prev) => prev.filter((b) => b.id !== id));

    if (selectedBookId === id) {
      setSelectedBookId(null);
      setView("list");
    }

    let firestoreDeleteSucceeded = false;
    try {
      await deleteItemForUser(userId, id);
      firestoreDeleteSucceeded = true;
    } catch (err) {
      console.error("Failed to delete item from Firestore:", err);
    }

    if (!firestoreDeleteSucceeded || !deletedItem) {
      return;
    }

    try {
      await purgeResourceContent(userId, deletedItem.id);
    } catch (err) {
      console.error("Failed to purge item from AI Backend:", err);
    }
  }, [books, selectedBookId, userId]);

  const handleBulkDelete = useCallback(async (ids: string[]) => {
    if (!window.confirm(`Are you sure you want to delete ${ids.length} items?`)) return;
    const deletedItems = books.filter((b) => ids.includes(b.id));

    setBooks((prev) => prev.filter((b) => !ids.includes(b.id)));

    if (selectedBookId && ids.includes(selectedBookId)) {
      setSelectedBookId(null);
      setView("list");
    }

    let firestoreDeleteSucceeded = false;
    try {
      await deleteMultipleItemsForUser(userId, ids);
      firestoreDeleteSucceeded = true;
    } catch (err) {
      console.error("Failed to delete items from Firestore:", err);
    }

    if (!firestoreDeleteSucceeded || deletedItems.length === 0) {
      return;
    }

    const purgeResults = await Promise.allSettled(
      deletedItems.map((item) => purgeResourceContent(userId, item.id))
    );

    purgeResults.forEach((result, index) => {
      if (result.status === "rejected") {
        console.error(`Failed to purge item ${deletedItems[index].id} from AI Backend:`, result.reason);
      }
    });
  }, [books, selectedBookId, userId]);

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

      // Sync highlights/insights to Oracle (replace existing for this book)
      (async () => {
        try {
          await syncHighlights(
            userId,
            updatedItem.id,
            updatedItem.title,
            updatedItem.author,
            updatedItem.highlights || []
          );
        } catch (err) {
          console.error("Failed to sync highlights to AI Backend:", err);
        }
      })();
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


  const selectedBookRaw = books.find((b) => b.id === selectedBookId);
  const selectedBook = selectedBookRaw || undefined;

  const editingBook = books.find((b) => b.id === editingBookId);

  const handleTabChange = useCallback((newTab: ResourceType | "NOTES" | "DASHBOARD" | "PROFILE" | "RAG_SEARCH" | "SMART_SEARCH" | "FLOW") => {
    setActiveTab(newTab);
    setView("list");
    setSelectedBookId(null);
    setCurrentPage(1);
    setListSearch('');
    setListStatusFilter('ALL');
    setListPublisherFilter('');
    if (newTab !== "BOOK") {
      setActiveCategoryFilter(null);
    }
  }, []);

  const handleNavigateToBooksWithCategory = useCallback((category: string) => {
    setActiveCategoryFilter(category);
    setListStatusFilter('ALL');
    setActiveTab("BOOK");
    setView("list");
    setSelectedBookId(null);
    setCurrentPage(1);
    setListSearch('');
    setListPublisherFilter('');
    setOpenToHighlights(false);
    setSelectedHighlightId(null);
  }, []);

  const handleNavigateToBooksWithStatus = useCallback((status: string) => {
    setListStatusFilter(status);
    setActiveCategoryFilter(null);
    setActiveTab("BOOK");
    setView("list");
    setSelectedBookId(null);
    setCurrentPage(1);
    setListSearch('');
    setListPublisherFilter('');
    setOpenToHighlights(false);
    setSelectedHighlightId(null);
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

  const makeFolderId = () => `folder-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  const handleCreatePersonalFolder = useCallback(async (
    category: PersonalNoteCategory,
    name: string
  ): Promise<PersonalNoteFolder | null> => {
    const trimmedName = name.trim();
    if (!trimmedName) return null;
    const now = Date.now();
    const nextOrder = personalNoteFolders
      .filter((f) => f.category === category)
      .reduce((max, f) => Math.max(max, f.order), 0) + 1;
    const folder: PersonalNoteFolder = {
      id: makeFolderId(),
      category,
      name: trimmedName,
      order: nextOrder,
      createdAt: now,
      updatedAt: now,
    };

    setPersonalNoteFolders((prev) => [...prev, folder]);
    try {
      await savePersonalNoteFolderForUser(userId, folder);
      return folder;
    } catch (err) {
      console.error("Failed to create personal note folder:", err);
      setPersonalNoteFolders((prev) => prev.filter((f) => f.id !== folder.id));
      return null;
    }
  }, [personalNoteFolders, userId]);

  const handleRenamePersonalFolder = useCallback(async (
    folderId: string,
    name: string
  ): Promise<boolean> => {
    const trimmed = name.trim();
    if (!trimmed) return false;
    const prev = personalNoteFolders;
    const now = Date.now();
    setPersonalNoteFolders((folders) => folders.map((f) => f.id === folderId ? { ...f, name: trimmed, updatedAt: now } : f));
    try {
      await updatePersonalNoteFolderForUser(userId, folderId, { name: trimmed, updatedAt: now });
      setBooks((items) => items.map((item) => {
        if (!isPersonalNote(item)) return item;
        if (item.personalFolderId !== folderId) return item;
        return { ...item, folderPath: trimmed };
      }));
      return true;
    } catch (err) {
      console.error("Failed to rename personal note folder:", err);
      setPersonalNoteFolders(prev);
      return false;
    }
  }, [personalNoteFolders, userId]);

  const handleDeletePersonalFolder = useCallback(async (
    folderId: string
  ): Promise<boolean> => {
    const folder = personalNoteFolders.find((f) => f.id === folderId);
    if (!folder) return false;
    const prevFolders = personalNoteFolders;
    const prevBooks = books;
    const affectedNotes = books.filter((item) => isPersonalNote(item) && item.personalFolderId === folderId);

    setPersonalNoteFolders((folders) => folders.filter((f) => f.id !== folderId));
    setBooks((items) => items.map((item) => {
      if (!isPersonalNote(item) || item.personalFolderId !== folderId) return item;
      return { ...item, personalFolderId: undefined, folderPath: undefined };
    }));

    try {
      await Promise.all([
        ...affectedNotes.map((note) => movePersonalNoteForUser(userId, note.id, getPersonalNoteCategory(note), undefined, undefined)),
        deletePersonalNoteFolderForUser(userId, folderId),
      ]);
      return true;
    } catch (err) {
      console.error("Failed to delete personal note folder:", err);
      setPersonalNoteFolders(prevFolders);
      setBooks(prevBooks);
      return false;
    }
  }, [books, personalNoteFolders, userId]);

  const handleMovePersonalFolder = useCallback(async (
    folderId: string,
    targetCategory: PersonalNoteCategory
  ): Promise<boolean> => {
    const folder = personalNoteFolders.find((f) => f.id === folderId);
    if (!folder) return false;
    if (folder.category === targetCategory) return true;

    const prevFolders = personalNoteFolders;
    const prevBooks = books;
    const now = Date.now();
    const nextOrder = personalNoteFolders
      .filter((f) => f.category === targetCategory && f.id !== folderId)
      .reduce((max, f) => Math.max(max, f.order), 0) + 1;
    const affectedNotes = books.filter((item) => isPersonalNote(item) && item.personalFolderId === folderId);

    setPersonalNoteFolders((folders) => folders.map((f) => {
      if (f.id !== folderId) return f;
      return { ...f, category: targetCategory, order: nextOrder, updatedAt: now };
    }));

    setBooks((items) => items.map((item) => {
      if (!isPersonalNote(item) || item.personalFolderId !== folderId) return item;
      return {
        ...item,
        personalNoteCategory: targetCategory,
        personalFolderId: folderId,
        folderPath: folder.name,
      };
    }));

    try {
      await Promise.all([
        updatePersonalNoteFolderForUser(userId, folderId, {
          category: targetCategory,
          order: nextOrder,
          updatedAt: now,
        }),
        ...affectedNotes.map((note) =>
          movePersonalNoteForUser(userId, note.id, targetCategory, folderId, folder.name)
        ),
      ]);

      await Promise.all(affectedNotes.map((note) =>
        syncPersonalNoteToBackend({
          ...note,
          personalNoteCategory: targetCategory,
          personalFolderId: folderId,
          folderPath: folder.name,
        }, false)
      ));

      return true;
    } catch (err) {
      console.error("Failed to move personal note folder:", err);
      setPersonalNoteFolders(prevFolders);
      setBooks(prevBooks);
      return false;
    }
  }, [books, personalNoteFolders, syncPersonalNoteToBackend, userId]);

  const handleMovePersonalNote = useCallback(async (
    noteId: string,
    targetCategory: PersonalNoteCategory,
    targetFolderId?: string
  ): Promise<boolean> => {
    const note = books.find((item) => item.id === noteId);
    if (!note || !isPersonalNote(note)) return false;
    const targetFolder = targetFolderId ? personalNoteFolders.find((f) => f.id === targetFolderId) : undefined;
    const nextFolderId = targetFolder?.id;
    const nextFolderPath = targetFolder?.name;
    const currentCategory = getPersonalNoteCategory(note);
    const currentFolderId = note.personalFolderId;
    const currentFolderPath = note.folderPath;

    if (currentCategory === targetCategory && (currentFolderId || undefined) === (nextFolderId || undefined)) {
      return true;
    }

    setBooks((items) => items.map((item) => {
      if (item.id !== noteId || !isPersonalNote(item)) return item;
      return {
        ...item,
        personalNoteCategory: targetCategory,
        personalFolderId: nextFolderId,
        folderPath: nextFolderPath,
      };
    }));

    try {
      await movePersonalNoteForUser(userId, noteId, targetCategory, nextFolderId, nextFolderPath);
      await syncPersonalNoteToBackend({
        ...note,
        personalNoteCategory: targetCategory,
        personalFolderId: nextFolderId,
        folderPath: nextFolderPath,
      }, false);
      return true;
    } catch (err) {
      console.error("Failed to move personal note:", err);
      setBooks((items) => items.map((item) => {
        if (item.id !== noteId || !isPersonalNote(item)) return item;
        return {
          ...item,
          personalNoteCategory: currentCategory,
          personalFolderId: currentFolderId,
          folderPath: currentFolderPath,
        };
      }));
      return false;
    }
  }, [books, personalNoteFolders, syncPersonalNoteToBackend, userId]);

  useEffect(() => {
    if (itemsLoading || didRunLegacyFolderMigration) return;

    const legacyNotes = books.filter((item) =>
      isPersonalNote(item) &&
      !!item.folderPath &&
      !item.personalFolderId
    );
    if (legacyNotes.length === 0) {
      setDidRunLegacyFolderMigration(true);
      return;
    }

    let cancelled = false;
    const runMigration = async () => {
      const existingByKey = new Map<string, PersonalNoteFolder>();
      personalNoteFolders.forEach((folder) => {
        const key = `${folder.category}::${folder.name.toLowerCase()}`;
        existingByKey.set(key, folder);
      });

      const newFolders: PersonalNoteFolder[] = [];
      const noteUpdates: Array<{ noteId: string; category: PersonalNoteCategory; folderId: string; folderPath: string }> = [];

      legacyNotes.forEach((note) => {
        const category = getPersonalNoteCategory(note);
        const folderName = (note.folderPath || "").trim();
        if (!folderName) return;
        const key = `${category}::${folderName.toLowerCase()}`;
        let folder = existingByKey.get(key);
        if (!folder) {
          const now = Date.now();
          const nextOrder = Math.max(
            ...personalNoteFolders
              .filter((f) => f.category === category)
              .map((f) => f.order),
            ...newFolders
              .filter((f) => f.category === category)
              .map((f) => f.order),
            0
          ) + 1;
          folder = {
            id: makeFolderId(),
            category,
            name: folderName,
            order: nextOrder,
            createdAt: now,
            updatedAt: now,
          };
          newFolders.push(folder);
          existingByKey.set(key, folder);
        }
        noteUpdates.push({ noteId: note.id, category, folderId: folder.id, folderPath: folder.name });
      });

      if (cancelled) return;
      if (newFolders.length > 0) {
        setPersonalNoteFolders((prev) => [...prev, ...newFolders]);
      }
      if (noteUpdates.length > 0) {
        setBooks((prev) => prev.map((item) => {
          const update = noteUpdates.find((u) => u.noteId === item.id);
          if (!update || !isPersonalNote(item)) return item;
          return {
            ...item,
            personalNoteCategory: update.category,
            personalFolderId: update.folderId,
            folderPath: update.folderPath,
          };
        }));
      }

      try {
        await Promise.all([
          ...newFolders.map((folder) => savePersonalNoteFolderForUser(userId, folder)),
          ...noteUpdates.map((update) => movePersonalNoteForUser(userId, update.noteId, update.category, update.folderId, update.folderPath)),
        ]);
      } catch (err) {
        console.error("Legacy personal note folder migration failed:", err);
      } finally {
        if (!cancelled) setDidRunLegacyFolderMigration(true);
      }
    };

    runMigration();
    return () => {
      cancelled = true;
    };
  }, [books, didRunLegacyFolderMigration, itemsLoading, personalNoteFolders, userId]);

  if (itemsLoading && books.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500">
        Loading your library from cloud...
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#F7F8FB] dark:bg-[#0b0e14] overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main Content Shell (Warm Gray + Noise) */}
      <main className="flex-1 flex flex-col h-full w-full relative overflow-y-auto transition-all duration-300 bg-[#F7F8FB] dark:bg-[#0b0e14] noise-bg
">
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
          <SmartSearch userId={userId} onBack={() => handleTabChange("DASHBOARD")} books={books} />
        ) : activeTab === "RAG_SEARCH" ? (
          <RAGSearch userId={userId} userEmail={userEmail} onBack={() => handleTabChange("DASHBOARD")} books={books} />
        ) : activeTab === "FLOW" ? (
          <FlowContainer
            firebaseUid={userId}
            anchorType="topic"
            anchorId="General Discovery" // Default anchor if user just clicks sidebar
            onClose={() => handleTabChange("DASHBOARD")}
          />
        ) : view === "list" ? (
          <BookList
            books={books}
            activeTab={activeTab}
            userId={userId}
            categoryFilter={activeCategoryFilter}
            onCategoryFilterChange={setActiveCategoryFilter}
            onCategoryNavigate={handleNavigateToBooksWithCategory}
            onStatusNavigate={handleNavigateToBooksWithStatus}
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
              setPersonalNoteDraftDefaults({});
              setEditingBookId(null);
              setIsFormOpen(true);
            }}
            personalNoteFolders={personalNoteFolders}
            onCreatePersonalFolder={handleCreatePersonalFolder}
            onRenamePersonalFolder={handleRenamePersonalFolder}
            onDeletePersonalFolder={handleDeletePersonalFolder}
            onMovePersonalFolder={handleMovePersonalFolder}
            onMovePersonalNote={handleMovePersonalNote}
            onAddPersonalNote={({ category, folderId, folderPath }) => {
              handleOpenPersonalNoteForm({ category, folderId, folderPath });
            }}
            onQuickCreatePersonalNote={handleQuickCreatePersonalNote}
            onMobileMenuClick={() => setIsSidebarOpen(true)}
            onDeleteBook={handleDeleteBook}
            onDeleteMultiple={handleBulkDelete}
            onToggleFavorite={handleToggleFavorite}
            onToggleHighlightFavorite={handleToggleHighlightFavorite}
            onLoadMore={handleLoadMore}
            hasMore={hasMore}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
            searchQuery={listSearch}
            onSearchChange={setListSearch}
            statusFilter={listStatusFilter}
            onStatusFilterChange={setListStatusFilter}
            sortOption={listSortOption as any}
            onSortOptionChange={setListSortOption as any}
            publisherFilter={listPublisherFilter}
            onPublisherFilterChange={setListPublisherFilter}
            onTabChange={handleTabChange}
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
              onBookUpdated={handleUpdateBookForEnrichment}
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
          noteDefaults={!editingBook && (activeTab === "PERSONAL_NOTE")
            ? personalNoteDraftDefaults
            : undefined}
          onSave={editingBookId ? handleUpdateBook : handleAddBook}
          onCancel={() => {
            setIsFormOpen(false);
            setEditingBookId(null);
            setPersonalNoteDraftDefaults({});
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
      <div className="min-h-screen flex items-center justify-center bg-[#F7F8FB] dark:bg-[#0b0e14] transition-colors duration-300
">
        <div className="bg-white dark:bg-slate-900 shadow-lg rounded-2xl px-8 py-10 flex flex-col items-center gap-4 border border-slate-100 dark:border-slate-800">
          <div className="flex flex-col items-center gap-6 mb-12">
            <img
              src={logo}
              alt="TomeHub Icon"
              className="h-[156px] w-auto object-contain brightness-110 drop-shadow-xl"
            />
            <h1 className="text-[39px] font-bold text-slate-900 dark:text-white tracking-tighter">TomeHub</h1>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400 text-center max-w-xs">
            Sign in with your Google account to access your library across all
            devices.
          </p>
          <button
            onClick={loginWithGoogle}
            className="mt-2 bg-[#262D40]/40 hover:bg-[#262D40]/55 text-white px-5 py-2 rounded-lg text-sm font-medium shadow-md transition-colors"
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
