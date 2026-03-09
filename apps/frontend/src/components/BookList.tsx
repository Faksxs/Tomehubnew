import React, { useMemo, useState, useEffect, useDeferredValue, useTransition, useRef } from 'react';
import { LibraryItem, ReadingStatus, ResourceType, PhysicalStatus, PersonalNoteCategory, PersonalNoteFolder } from '../types';
import { Book as BookIcon, FileText, Globe, ExternalLink, ArrowRight, PenTool, BarChart2, AlertTriangle, Library, CheckCircle, Zap, Film, Tv } from 'lucide-react';
import {
    PointerSensor,
    TouchSensor,
    useDraggable,
    useDroppable,
    useSensor,
    useSensors,
    closestCenter,
    type DragEndEvent,
    type DragStartEvent,
} from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { CATEGORIES } from './CategorySelector';
import {
    KnowledgeBaseLogo,
    HighlightsLogo,
    BooksLogo,
    ArticlesLogo,
    NotesLogo
} from './ui/FeatureLogos';
import { getPersonalNoteCategory, isPersonalNote } from '../lib/personalNotePolicy';
import { extractPersonalNoteText, hasMeaningfulPersonalNoteContent } from '../lib/personalNoteRender';
import { CenteredLoadingState } from './library/CenteredLoadingState';
import { EmptyStatePanel } from './library/EmptyStatePanel';
import { PaginationControls } from './library/PaginationControls';
import { ActiveCategoryFilterPill } from '../features/library/components/ActiveCategoryFilterPill';
import { LibraryPageHeader } from '../features/library/components/LibraryPageHeader';
import { LibraryFiltersBar } from '../features/library/components/LibraryFiltersBar';
import { StandardLibraryGrid } from '../features/library/components/StandardLibraryGrid';
import { NotesHighlightsView } from '../features/notes/components/NotesHighlightsView';
import { PersonalNotesWorkspace } from '../features/notes/components/PersonalNotesWorkspace';
import { NoteMoveUndoToast } from '../features/notes/components/NoteMoveUndoToast';
import { useUiFeedback } from '../shared/ui/feedback/useUiFeedback';
const KnowledgeDashboard = React.lazy(() => import('./dashboard/KnowledgeDashboard').then(module => ({ default: module.KnowledgeDashboard })));
type NoteSmartFilter = 'NONE' | 'FAVORITES' | 'RECENT';
const normalizeTagKey = (tag: string): string => tag.trim().toLowerCase();
const FOLDER_PAGE_SIZE = 10;
const normalizeSearchText = (value: string): string => value
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i')
    .replace(/\s+/g, ' ')
    .trim();
const includesNormalized = (source: string, term: string): boolean => {
    if (!term) return true;
    return normalizeSearchText(source).includes(term);
};

type DraggableRenderProps = {
    setNodeRef: (element: HTMLElement | null) => void;
    style: React.CSSProperties;
    isDragging: boolean;
    attributes: any;
    listeners: any;
};

type IndexedLibraryItem = {
    normalizedTitle: string;
    normalizedAuthor: string;
    normalizedIsbn: string;
    normalizedCode: string;
    normalizedPublicationYear: string;
    normalizedOriginalTitle: string;
    normalizedSummary: string;
    normalizedUrl: string;
    normalizedNotes: string;
    normalizedCategory: string;
    normalizedFolderName: string;
    normalizedTags: string[];
    normalizedTagKeys: Set<string>;
    normalizedCast: string[];
};

const DraggableWrapper: React.FC<{
    id: string;
    children: (props: DraggableRenderProps) => React.ReactNode;
}> = ({ id, children }) => {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id });
    const style = {
        transform: CSS.Transform.toString(transform),
    } as React.CSSProperties;
    return <>{children({ setNodeRef, style, isDragging, attributes, listeners })}</>;
};

const DroppableZone: React.FC<{
    id: string;
    children: (isOver: boolean) => React.ReactNode;
}> = ({ id, children }) => {
    const { setNodeRef, isOver } = useDroppable({ id });
    return <div ref={setNodeRef}>{children(isOver)}</div>;
};

interface BookListProps {
    books: LibraryItem[];
    personalNoteFolders?: PersonalNoteFolder[];
    onAddBook: () => void;
    onAddPersonalNote?: (defaults: { category: PersonalNoteCategory; folderId?: string; folderPath?: string }) => void;
    onQuickCreatePersonalNote?: (payload: { title: string; content: string; category: PersonalNoteCategory; folderId?: string; folderPath?: string }) => void;
    onCreatePersonalFolder?: (category: PersonalNoteCategory, name: string) => Promise<PersonalNoteFolder | null>;
    onRenamePersonalFolder?: (folderId: string, name: string) => Promise<boolean>;
    onDeletePersonalFolder?: (folderId: string) => Promise<boolean>;
    onMovePersonalNote?: (noteId: string, targetCategory: PersonalNoteCategory, targetFolderId?: string) => Promise<boolean>;
    onMovePersonalFolder?: (folderId: string, targetCategory: PersonalNoteCategory) => Promise<boolean>;
    onSelectBook: (book: LibraryItem) => void;
    onSelectBookWithTab?: (book: LibraryItem, tab: 'info' | 'highlights', highlightId?: string) => void; // Optional: select book with specific tab and highlight
    activeTab: ResourceType | 'NOTES' | 'DASHBOARD' | 'INSIGHTS' | 'INGEST' | 'FLOW' | 'RAG_SEARCH' | 'SMART_SEARCH' | 'PROFILE';
    mediaLibraryEnabled?: boolean;
    onMobileMenuClick: () => void;
    userId: string;
    categoryFilter?: string | null;
    onCategoryFilterChange?: (category: string | null) => void;
    onCategoryNavigate?: (category: string) => void;
    onStatusNavigate?: (status: string) => void;

    onDeleteBook: (id: string) => void;
    onDeleteMultiple?: (ids: string[]) => void;
    onToggleFavorite: (id: string) => void; // Toggle favorite status
    onToggleHighlightFavorite?: (bookId: string, highlightId: string) => void; // Toggle highlight favorite status
    currentPage: number;
    onPageChange: (page: number) => void;
    searchQuery: string;
    onSearchChange: (val: string) => void;
    statusFilter: string;
    onStatusFilterChange: (val: any) => void;
    sortOption: 'date_desc' | 'date_asc' | 'title_asc';
    onSortOptionChange: (val: any) => void;
    publisherFilter: string;
    onPublisherFilterChange: (val: string) => void;
    onTabChange?: (tab: ResourceType | 'NOTES' | 'DASHBOARD' | 'INSIGHTS' | 'INGEST' | 'FLOW' | 'RAG_SEARCH' | 'SMART_SEARCH' | 'PROFILE') => void;
}

export const BookList: React.FC<BookListProps> = React.memo(({ books, personalNoteFolders = [], onAddBook, onAddPersonalNote, onQuickCreatePersonalNote, onCreatePersonalFolder, onRenamePersonalFolder, onDeletePersonalFolder, onMovePersonalNote, onMovePersonalFolder, onSelectBook, onSelectBookWithTab, activeTab, mediaLibraryEnabled = false, onMobileMenuClick, onDeleteBook, onDeleteMultiple, onToggleFavorite, onToggleHighlightFavorite, userId, categoryFilter, onCategoryFilterChange, onCategoryNavigate, onStatusNavigate, currentPage, onPageChange, searchQuery, onSearchChange, statusFilter, onStatusFilterChange, sortOption, onSortOptionChange, publisherFilter, onPublisherFilterChange, onTabChange }) => {
    const { confirm, prompt } = useUiFeedback();
    // UI State (Moved to App.tsx for persistence)
    const [isSearchPending, startSearchTransition] = useTransition();
    const deferredSearchQuery = useDeferredValue(searchQuery);
    const searchDebounceTimerRef = useRef<number | null>(null);

    // Pagination State (Moved to App.tsx) - using props instead

    const isStats = activeTab === 'DASHBOARD';
    const isNotesTab = activeTab === 'NOTES';
    const isPersonalNotes = activeTab === 'PERSONAL_NOTE';
    const isMediaTab = mediaLibraryEnabled && activeTab === 'MOVIE';
    const [noteCategoryFilter, setNoteCategoryFilter] = useState<'ALL' | PersonalNoteCategory>('ALL');
    const [noteFolderFilter, setNoteFolderFilter] = useState<'ALL' | '__ROOT__' | string>('ALL');
    const [noteSmartFilter, setNoteSmartFilter] = useState<NoteSmartFilter>('NONE');
    const [mediaTypeFilter, setMediaTypeFilter] = useState<'ALL' | 'MOVIE' | 'SERIES'>('ALL');
    const [noteTagFilter, setNoteTagFilter] = useState<string | null>(null);
    const [isTopTagsOpen, setIsTopTagsOpen] = useState(false);
    const [collapsedFolderCategories, setCollapsedFolderCategories] = useState<Record<PersonalNoteCategory, boolean>>({
        PRIVATE: true,
        DAILY: true,
        IDEAS: true,
    });
    const [visibleFolderCounts, setVisibleFolderCounts] = useState<Record<PersonalNoteCategory, number>>({
        PRIVATE: FOLDER_PAGE_SIZE,
        DAILY: FOLDER_PAGE_SIZE,
        IDEAS: FOLDER_PAGE_SIZE,
    });
    const [isPersonalPanelOpen, setIsPersonalPanelOpen] = useState(false);
    const [isQuickCaptureOpen, setIsQuickCaptureOpen] = useState(false);
    const [quickCaptureCategory, setQuickCaptureCategory] = useState<PersonalNoteCategory>('DAILY');
    const [quickNoteTitle, setQuickNoteTitle] = useState('');
    const [quickNoteBody, setQuickNoteBody] = useState('');
    const [isMobileViewport, setIsMobileViewport] = useState(() => (
        typeof window !== 'undefined' ? window.matchMedia('(max-width: 767px)').matches : false
    ));
    const [activeDraggedNoteId, setActiveDraggedNoteId] = useState<string | null>(null);
    const [activeDraggedFolderId, setActiveDraggedFolderId] = useState<string | null>(null);
    const [undoMove, setUndoMove] = useState<{ noteId: string; category: PersonalNoteCategory; folderId?: string; timeoutId: number } | null>(null);
    const [lastTap, setLastTap] = useState<{ noteId: string; time: number } | null>(null);

    useEffect(() => {
        if (!isPersonalNotes) {
            setNoteCategoryFilter('ALL');
            setNoteFolderFilter('ALL');
            setNoteSmartFilter('NONE');
            setNoteTagFilter(null);
            setIsTopTagsOpen(false);
            setCollapsedFolderCategories({ PRIVATE: true, DAILY: true, IDEAS: true });
            setVisibleFolderCounts({ PRIVATE: FOLDER_PAGE_SIZE, DAILY: FOLDER_PAGE_SIZE, IDEAS: FOLDER_PAGE_SIZE });
            setQuickCaptureCategory('DAILY');
            setIsPersonalPanelOpen(false);
        }
    }, [isPersonalNotes]);

    useEffect(() => {
        if (!isMediaTab) {
            setMediaTypeFilter('ALL');
        }
    }, [isMediaTab]);

    useEffect(() => {
        if (typeof window === 'undefined') return undefined;
        const mediaQuery = window.matchMedia('(max-width: 767px)');
        const handleChange = (event: MediaQueryListEvent | MediaQueryList) => {
            setIsMobileViewport(event.matches);
        };

        handleChange(mediaQuery);
        const listener = (event: MediaQueryListEvent) => handleChange(event);
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', listener);
            return () => mediaQuery.removeEventListener('change', listener);
        }
        mediaQuery.addListener(listener);
        return () => mediaQuery.removeListener(listener);
    }, []);

    useEffect(() => {
        if (noteTagFilter) {
            setIsTopTagsOpen(true);
        }
    }, [noteTagFilter]);

    const dndSensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 8 },
        }),
        useSensor(TouchSensor, {
            activationConstraint: { delay: 120, tolerance: 8 },
        })
    );

    const handleNoteCardClick = (note: LibraryItem) => {
        const now = Date.now();

        if (isMobileViewport && lastTap?.noteId === note.id && now - lastTap.time < 300) {
            // Double tap detected - open in edit mode
            setLastTap(null);
            setIsPersonalPanelOpen(false);
            setIsQuickCaptureOpen(false);
            if (onSelectBookWithTab) {
                onSelectBookWithTab(note, 'info');
            } else {
                onSelectBook(note);
            }
        } else {
            // Single tap - just open note preview
            setLastTap({ noteId: note.id, time: now });
            if (isMobileViewport) {
                setIsPersonalPanelOpen(false);
                setIsQuickCaptureOpen(false);
            }
            onSelectBook(note);
        }
    };

    const folderById = useMemo(() => {
        const map = new Map<string, PersonalNoteFolder>();
        personalNoteFolders.forEach((folder) => map.set(folder.id, folder));
        return map;
    }, [personalNoteFolders]);

    useEffect(() => {
        if (noteFolderFilter === 'ALL' || noteFolderFilter === '__ROOT__') return;
        const folder = folderById.get(noteFolderFilter);
        if (!folder) return;
        if (quickCaptureCategory !== folder.category) {
            setQuickCaptureCategory(folder.category);
        }
        setCollapsedFolderCategories((prev) => ({ ...prev, [folder.category]: false }));
    }, [noteFolderFilter, folderById, quickCaptureCategory]);

    const legacyFolderLookup = useMemo(() => {
        const map = new Map<string, string>();
        personalNoteFolders.forEach((folder) => {
            map.set(`${folder.category}::${folder.name.toLowerCase()}`, folder.id);
        });
        return map;
    }, [personalNoteFolders]);

    const getResolvedNoteFolderId = (note: LibraryItem): string | undefined => {
        if (!isPersonalNote(note)) return undefined;
        if (note.personalFolderId) return note.personalFolderId;
        const folderPath = (note.folderPath || '').trim();
        if (!folderPath) return undefined;
        return legacyFolderLookup.get(`${getPersonalNoteCategory(note)}::${folderPath.toLowerCase()}`);
    };

    const getResolvedNoteFolderName = (note: LibraryItem): string | undefined => {
        const folderId = getResolvedNoteFolderId(note);
        if (folderId) return folderById.get(folderId)?.name;
        return note.folderPath || undefined;
    };

    const itemSearchIndex = useMemo(() => {
        const index = new Map<string, IndexedLibraryItem>();
        books.forEach((book) => {
            const normalizedTags = (book.tags || [])
                .map((tag) => normalizeSearchText(tag))
                .filter(Boolean);
            index.set(book.id, {
                normalizedTitle: normalizeSearchText(book.title || ''),
                normalizedAuthor: normalizeSearchText(book.author || ''),
                normalizedIsbn: normalizeSearchText(book.isbn || ''),
                normalizedCode: normalizeSearchText(book.code || ''),
                normalizedPublicationYear: normalizeSearchText(book.publicationYear || ''),
                normalizedOriginalTitle: normalizeSearchText(book.originalTitle || ''),
                normalizedSummary: normalizeSearchText(book.summaryText || ''),
                normalizedUrl: normalizeSearchText(book.url || ''),
                normalizedNotes: normalizeSearchText(extractPersonalNoteText(book.generalNotes || '')),
                normalizedCategory: normalizeSearchText(isPersonalNote(book) ? getPersonalNoteCategory(book) : ''),
                normalizedFolderName: normalizeSearchText(isPersonalNote(book) ? (getResolvedNoteFolderName(book) || '') : ''),
                normalizedTags,
                normalizedTagKeys: new Set((book.tags || []).map((tag) => normalizeTagKey(tag))),
                normalizedCast: (book.castTop || []).map((name) => normalizeSearchText(name)).filter(Boolean),
            });
        });
        return index;
    }, [books, folderById, legacyFolderLookup]);

    const personalNotesData = useMemo(() => {
        const allPersonalNotes: LibraryItem[] = [];
        const nonPrivatePersonalNotes: LibraryItem[] = [];
        const favoriteNotesVisibleCount = 0;
        const noteCategoryCounts: Record<PersonalNoteCategory, number> = { PRIVATE: 0, DAILY: 0, IDEAS: 0 };
        const rootNoteCounts: Record<PersonalNoteCategory, number> = { PRIVATE: 0, DAILY: 0, IDEAS: 0 };
        const folderCounts = new Map<string, number>();
        const tagMap = new Map<string, { label: string; noteIds: Set<string> }>();
        let favoriteCount = 0;

        books.forEach((book) => {
            if (book.type !== 'PERSONAL_NOTE') return;
            allPersonalNotes.push(book);
            const category = getPersonalNoteCategory(book);
            noteCategoryCounts[category] += 1;

            const resolvedFolderId = getResolvedNoteFolderId(book);
            if (resolvedFolderId) {
                const key = normalizeTagKey(trimmed);
                if (seenInNote.has(key)) return;
                seenInNote.add(key);
                const entry = tagMap.get(key);
                if (!entry) {
                    tagMap.set(key, { label: trimmed, noteIds: new Set([book.id]) });
                    return;
                }
                entry.noteIds.add(book.id);
            });
    });

    const recentVisibleNoteIds = [...nonPrivatePersonalNotes]
        .sort((a, b) => b.addedAt - a.addedAt)
        .slice(0, 20)
        .map((note) => note.id);

    const topTagEntries = [...tagMap.entries()]
        .map(([key, value]) => ({ key, label: value.label || key, count: value.noteIds.size }))
        .sort((a, b) => (b.count - a.count) || a.label.localeCompare(b.label))
        .slice(0, 10);

    const categoryFolderMap: Record<PersonalNoteCategory, Array<{ id: string; name: string; count: number; order: number }>> = {
        PRIVATE: [],
        DAILY: [],
        IDEAS: [],
    };

    personalNoteFolders.forEach((folder) => {
        categoryFolderMap[folder.category].push({
            id: folder.id,
            name: folder.name,
            order: folder.order,
            count: folderCounts.get(folder.id) || 0,
        });
    });

    (['PRIVATE', 'DAILY', 'IDEAS'] as PersonalNoteCategory[]).forEach((category) => {
        categoryFolderMap[category].sort((a, b) => (a.order - b.order) || a.name.localeCompare(b.name));
    });

    return {
        allPersonalNotes,
        nonPrivatePersonalNotes,
        allNotesVisibleCount: nonPrivatePersonalNotes.length,
        favoriteNotesVisibleCount: favoriteCount,
        recentVisibleNoteIds,
        recentVisibleNoteIdSet: new Set(recentVisibleNoteIds),
        recentNotesVisibleCount: recentVisibleNoteIds.length,
        topTagEntries,
        noteCategoryCounts,
        categoryFolderMap,
        rootNoteCounts,
    };
}, [books, personalNoteFolders, legacyFolderLookup]);

// --- PAGE SIZE CONFIGURATION ---
const itemsPerPage = useMemo(() => {
    switch (activeTab) {
        case 'BOOK': return 24;
        case 'MOVIE': return 24;
        case 'ARTICLE': return 24;
        case 'PERSONAL_NOTE': return 30;
        case 'NOTES': return 50;
        default: return 24;
    }
}, [activeTab]);

// --- PERFORMANCE OPTIMIZATION: DEBOUNCING ---
// Updates the actual search query 300ms after the user STOPS typing.
// This prevents the heavy filtering logic from running on every keystroke.
const [localInput, setLocalInput] = useState(searchQuery);
const showSearchLoading = localInput !== searchQuery || isSearchPending;

useEffect(() => {
    if (searchDebounceTimerRef.current !== null) {
        window.clearTimeout(searchDebounceTimerRef.current);
        searchDebounceTimerRef.current = null;
    }

    if (localInput === searchQuery) return;

    const nextQuery = localInput;
    searchDebounceTimerRef.current = window.setTimeout(() => {
        searchDebounceTimerRef.current = null;
        startSearchTransition(() => {
            onSearchChange(nextQuery);
            onPageChange(1); // Reset pagination on new search
        });
    }, 300);

    return () => {
        if (searchDebounceTimerRef.current !== null) {
            window.clearTimeout(searchDebounceTimerRef.current);
            searchDebounceTimerRef.current = null;
        }
    };
}, [localInput, searchQuery, onSearchChange, onPageChange, startSearchTransition]);

// Keep local input in sync if searchQuery is reset from parent (e.g. tab change)
useEffect(() => {
    setLocalInput(searchQuery);
}, [searchQuery]);

// Pagination reset on tab change is handled in App.tsx

// Filters are now controlled by props, reset is handled in App.tsx handleTabChange

// --- FILTER & ENRICH LOGIC ---
const filteredBooks = useMemo(() => {
    if (isNotesTab || isStats) return [];

    const term = normalizeSearchText(deferredSearchQuery);
    const normalizedCategoryFilter = categoryFilter ? normalizeSearchText(categoryFilter) : '';
    const normalizedPublisherFilter = publisherFilter ? normalizeSearchText(publisherFilter) : '';
    const recentNoteIdsForFilter = (isPersonalNotes && noteSmartFilter === 'RECENT')
        ? personalNotesData.recentVisibleNoteIdSet
        : null;

    const result = books.filter(book => {
        const indexed = itemSearchIndex.get(book.id);
        if (!indexed) return false;
        const matchesTabType = isMediaTab
            ? (book.type === 'MOVIE' || book.type === 'SERIES')
            : (book.type === activeTab);
        if (!matchesTabType) return false;
        if (isMediaTab && mediaTypeFilter !== 'ALL' && book.type !== mediaTypeFilter) {
            return false;
        }
        if (isPersonalNotes) {
            const noteCategory = getPersonalNoteCategory(book);
            if (noteCategoryFilter === 'ALL' && noteCategory === 'PRIVATE') {
                return false;
            }
            if (noteCategoryFilter !== 'ALL' && noteCategory !== noteCategoryFilter) {
                return false;
            }
            if (noteFolderFilter !== 'ALL') {
                const resolvedFolderId = getResolvedNoteFolderId(book);
                if (noteFolderFilter === '__ROOT__') {
                    if (resolvedFolderId) return false;
                } else if (resolvedFolderId !== noteFolderFilter) {
                    return false;
                }
            }
            if (noteSmartFilter === 'FAVORITES' && !book.isFavorite) {
                return false;
            }
            if (noteSmartFilter === 'RECENT' && !recentNoteIdsForFilter?.has(book.id)) {
                return false;
            }
            if (noteTagFilter && !indexed.normalizedTagKeys.has(noteTagFilter)) {
                return false;
            }
        }
        if (normalizedCategoryFilter) {
            const hasCategory = indexed.normalizedTags.some((tag) => tag === normalizedCategoryFilter);
            if (!hasCategory) return false;
        }
        // 2. Status Filter (Fastest check first)
        let matchesStatus = true;
        if (statusFilter !== 'ALL') {
            if (statusFilter === 'HIGHLIGHTS') {
                // Filter for items with highlights
                matchesStatus = book.highlights && book.highlights.length > 0;
            } else if (statusFilter === 'FAVORITES') {
                // Filter for favorited items
                matchesStatus = book.isFavorite === true;
            } else if (['To Read', 'Reading', 'Finished'].includes(statusFilter)) {
                matchesStatus = book.readingStatus === statusFilter;
            } else {
                if (activeTab === 'BOOK') {
                    matchesStatus = book.status === statusFilter;
                } else {
                    matchesStatus = false;
                }
            }
        }
        if (!matchesStatus) return false;

        // 3. Publisher Filter
        if (publisherFilter && activeTab === 'ARTICLE') {
            if (!normalizeSearchText(book.publisher || '').includes(normalizedPublisherFilter)) {
                return false;
            }
        }

        // 4. Search Term (Slowest check, do last)
        if (!term) return true;

        // Check indexed fields (Title, Author, ISBN) first
        if (indexed.normalizedTitle.includes(term)) return true;
        if (indexed.normalizedAuthor.includes(term)) return true;

        // Type specific efficient checks
        if (activeTab === 'BOOK') {
            if (indexed.normalizedIsbn.includes(term)) return true;
            if (indexed.normalizedCode.includes(term)) return true;
            // Books tab should stay strict: do not match by notes/tags.
            return false;
        }

        if (isMediaTab) {
            if (indexed.normalizedPublicationYear.includes(term)) return true;
            if (indexed.normalizedOriginalTitle.includes(term)) return true;
            if (indexed.normalizedSummary.includes(term)) return true;
            if (indexed.normalizedCast.some((name) => name.includes(term))) return true;
            if (indexed.normalizedUrl.includes(term)) return true;
        }

        // Deep search (Notes, Tags) - only if primary fields failed
        if (indexed.normalizedTags.some((tag) => tag.includes(term))) return true;
        if (indexed.normalizedNotes.includes(term)) return true;

        if (isPersonalNote(book)) {
            if (indexed.normalizedCategory.includes(term)) return true;
            if (indexed.normalizedFolderName.includes(term)) return true;
        }

        return false;
    });

    // Apply Sorting
    return result.sort((a, b) => {
        if (sortOption === 'title_asc') {
            return a.title.localeCompare(b.title);
        } else if (sortOption === 'date_asc') {
            // Oldest first
            return a.addedAt - b.addedAt;
        }
        // Default: Date Added (Newest first)
        return b.addedAt - a.addedAt;
    });

}, [activeTab, books, categoryFilter, deferredSearchQuery, isMediaTab, isNotesTab, isPersonalNotes, isStats, itemSearchIndex, mediaTypeFilter, noteCategoryFilter, noteFolderFilter, noteSmartFilter, noteTagFilter, personalNotesData.recentVisibleNoteIdSet, publisherFilter, sortOption, statusFilter]);

const {
    allPersonalNotes,
    allNotesVisibleCount,
    favoriteNotesVisibleCount,
    recentVisibleNoteIds,
    recentNotesVisibleCount,
    topTagEntries,
    noteCategoryCounts,
    categoryFolderMap,
    rootNoteCounts,
} = personalNotesData;

useEffect(() => {
    if (noteFolderFilter === 'ALL' || noteFolderFilter === '__ROOT__') return;
    const folderCategory = (['PRIVATE', 'DAILY', 'IDEAS'] as PersonalNoteCategory[]).find((category) =>
        categoryFolderMap[category].some((folder) => folder.id === noteFolderFilter)
    );
    if (!folderCategory) return;
    const selectedIndex = categoryFolderMap[folderCategory].findIndex((folder) => folder.id === noteFolderFilter);
    if (selectedIndex < 0) return;
    setVisibleFolderCounts((prev) => {
        const needed = selectedIndex + 1;
        if (prev[folderCategory] >= needed) return prev;
        return { ...prev, [folderCategory]: needed };
    });
}, [noteFolderFilter, categoryFolderMap]);

const flattenedHighlights = useMemo(
    () => books.flatMap((book) => book.highlights.map((highlight) => ({ ...highlight, source: book }))),
    [books]
);

// --- AGGREGATE HIGHLIGHTS ---
const filteredHighlights = useMemo(() => {
    if (!isNotesTab) return [];

    const term = normalizeSearchText(deferredSearchQuery);

    return flattenedHighlights
        .filter(item => {
            // 1. Status Filter
            if (statusFilter === 'FAVORITES') {
                if (!item.isFavorite) return false;
            }

            if (!term) return true;
            return includesNormalized(item.text || '', term) ||
                includesNormalized(item.comment || '', term) ||
                includesNormalized(item.source.title || '', term) ||
                includesNormalized(item.source.author || '', term) ||
                !!(item.tags && item.tags.some(t => includesNormalized(t, term)));
        })
        .sort((a, b) => b.createdAt - a.createdAt);
}, [deferredSearchQuery, flattenedHighlights, isNotesTab, statusFilter]);

// --- STATS CALCULATION ---
const stats = useMemo(() => {
    if (isNotesTab) {
        return {
            total: filteredHighlights.length,
            reading: 0,
            toRead: 0
        };
    }
    let reading = 0;
    let toRead = 0;
    filteredBooks.forEach((book) => {
        if (book.readingStatus === 'Reading') reading += 1;
        if (book.readingStatus === 'To Read') toRead += 1;
    });
    return {
        total: filteredBooks.length,
        reading,
        toRead
    };
}, [isNotesTab, filteredHighlights.length, filteredBooks]);

const getTabLabel = (type: ResourceType | 'NOTES' | 'DASHBOARD' | 'INSIGHTS' | 'INGEST' | 'FLOW' | 'RAG_SEARCH' | 'SMART_SEARCH' | 'PROFILE') => {
    switch (type) {
        case 'BOOK': return 'Books';
        case 'MOVIE': return 'Cinema';
        case 'SERIES': return 'Series';
        case 'ARTICLE': return 'Articles';
        case 'PERSONAL_NOTE': return 'Personal Notes';
        case 'NOTES': return 'All Notes';
        case 'DASHBOARD': return 'Dashboard';
        case 'INSIGHTS': return 'Insights';
        case 'INGEST': return 'Ingest';
        case 'FLOW': return 'Flux';
        case 'RAG_SEARCH': return 'LogosChat';
        case 'SMART_SEARCH': return 'Smart Search';
        case 'PROFILE': return 'Profile';
    }
};

const getSearchPlaceholder = () => {
    if (isNotesTab) return "Search quotes...";
    if (activeTab === 'PERSONAL_NOTE') return "Search notes...";
    if (isMediaTab) return "Search title, director, cast...";
    if (activeTab === 'ARTICLE') return "Search title, author...";
    return "Search title, author, ISBN...";
};

const categoryLabel = (category: PersonalNoteCategory) => {
    switch (category) {
        case 'PRIVATE': return 'Private';
        case 'DAILY': return 'Daily';
        case 'IDEAS': return 'Ideas';
        default: return category;
    }
};

const handleCreateFolder = async (category: PersonalNoteCategory) => {
    const folderName = await prompt({
        title: `${categoryLabel(category)} klasor adi`,
        description: 'Yeni klasor adi gir.',
        placeholder: 'Klasor adi',
        confirmLabel: 'Olustur',
        cancelLabel: 'Vazgec',
        validate: (value) => value ? null : 'Klasor adi bos olamaz.',
    });
    if (!folderName) return;
    const created = await onCreatePersonalFolder?.(category, folderName);
    if (!created) return;
    setNoteSmartFilter('NONE');
    setNoteTagFilter(null);
    setNoteCategoryFilter(category);
    setNoteFolderFilter(created.id);
    onPageChange(1);
};

const handleRenameFolder = async (folderId: string, currentName: string) => {
    const nextName = await prompt({
        title: 'Yeni klasor adi',
        description: 'Klasor icin guncel adi gir.',
        placeholder: 'Klasor adi',
        defaultValue: currentName,
        confirmLabel: 'Kaydet',
        cancelLabel: 'Vazgec',
        validate: (value) => value ? null : 'Klasor adi bos olamaz.',
    });
    if (!nextName || nextName === currentName) return;
    await onRenamePersonalFolder?.(folderId, nextName);
};

const handleDeleteFolder = async (folderId: string) => {
    const ok = await confirm({
        title: 'Bu klasor silinsin mi?',
        description: 'Icindeki notlar kategori kokune tasinacak.',
        confirmLabel: 'Sil',
        cancelLabel: 'Vazgec',
        tone: 'danger',
    });
    if (!ok) return;
    const deleted = await onDeletePersonalFolder?.(folderId);
    if (!deleted) return;
    if (noteFolderFilter === folderId) {
        setNoteSmartFilter('NONE');
        setNoteTagFilter(null);
        setNoteFolderFilter('__ROOT__');
    }
};

const scheduleUndoMove = (noteId: string, category: PersonalNoteCategory, folderId?: string) => {
    if (undoMove) {
        window.clearTimeout(undoMove.timeoutId);
    }
    const timeoutId = window.setTimeout(() => {
        setUndoMove(null);
    }, 5000);
    setUndoMove({ noteId, category, folderId, timeoutId });
};

const performMove = async (
    noteId: string,
    targetCategory: PersonalNoteCategory,
    targetFolderId?: string,
    withUndo: boolean = true
) => {
    const note = allPersonalNotes.find((n) => n.id === noteId);
    if (!note) return;
    const prevCategory = getPersonalNoteCategory(note);
    const prevFolderId = getResolvedNoteFolderId(note);
    const moved = await onMovePersonalNote?.(noteId, targetCategory, targetFolderId);
    if (moved && withUndo) {
        scheduleUndoMove(noteId, prevCategory, prevFolderId);
    }
};

const resolveDropCategory = (overId: string): PersonalNoteCategory | undefined => {
    if (overId.startsWith('cat-root:')) {
        return overId.replace('cat-root:', '') as PersonalNoteCategory;
    }
    if (overId.startsWith('cat-group:')) {
        return overId.replace('cat-group:', '') as PersonalNoteCategory;
    }
    if (overId.startsWith('folder:')) {
        const folderId = overId.replace('folder:', '');
        return folderById.get(folderId)?.category;
    }
    return undefined;
};

const performFolderMove = async (
    folderId: string,
    targetCategory: PersonalNoteCategory
) => {
    const folder = folderById.get(folderId);
    if (!folder || folder.category === targetCategory) return;
    const moved = await onMovePersonalFolder?.(folderId, targetCategory);
    if (moved && noteFolderFilter === folderId) {
        setNoteCategoryFilter(targetCategory);
        onPageChange(1);
    }
};

const handleDragStart = (event: DragStartEvent) => {
    const activeId = String(event.active.id);
    if (activeId.startsWith('note:')) {
        setActiveDraggedNoteId(activeId.replace('note:', ''));
        setActiveDraggedFolderId(null);
        return;
    }
    if (activeId.startsWith('folder-item:')) {
        setActiveDraggedFolderId(activeId.replace('folder-item:', ''));
        setActiveDraggedNoteId(null);
    }
};

const handleDragCancel = () => {
    setActiveDraggedNoteId(null);
    setActiveDraggedFolderId(null);
};

const handleDragEnd = async (event: DragEndEvent) => {
    setActiveDraggedNoteId(null);
    setActiveDraggedFolderId(null);
    const activeId = String(event.active.id || '');
    const overId = String(event.over?.id || '');
    if (!overId) return;

    if (activeId.startsWith('note:')) {
        const noteId = activeId.replace('note:', '');
        const targetCategory = resolveDropCategory(overId);
        if (!targetCategory) return;
        const targetFolderId = overId.startsWith('folder:') ? overId.replace('folder:', '') : undefined;
        await performMove(noteId, targetCategory, targetFolderId, true);
        return;
    }

    if (activeId.startsWith('folder-item:')) {
        const folderId = activeId.replace('folder-item:', '');
        const targetCategory = resolveDropCategory(overId);
        if (!targetCategory) return;
        await performFolderMove(folderId, targetCategory);
    }
};

const handleQuickCapture = () => {
    const content = quickNoteBody;
    if (!hasMeaningfulPersonalNoteContent(content)) return;
    const folderId = noteFolderFilter === 'ALL' || noteFolderFilter === '__ROOT__' ? undefined : noteFolderFilter;
    const folderCategory = folderId ? folderById.get(folderId)?.category : undefined;
    const category: PersonalNoteCategory = folderCategory || quickCaptureCategory;
    const folderPath = folderId ? folderById.get(folderId)?.name : undefined;
    onQuickCreatePersonalNote?.({
        title: quickNoteTitle.trim() || 'Quick Note',
        content,
        category,
        folderId,
        folderPath,
    });
    setQuickNoteTitle('');
    setQuickNoteBody('');
};

// --- RENDER LOGIC: PAGINATION ---
const totalItems = isNotesTab ? filteredHighlights.length : filteredBooks.length;
const totalPages = Math.ceil(totalItems / itemsPerPage);
const libraryCardDarkBg = (activeTab === 'ARTICLE') ? 'dark:bg-slate-800' : 'dark:bg-slate-900';

const displayedBooks = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredBooks.slice(start, start + itemsPerPage);
}, [filteredBooks, currentPage, itemsPerPage]);

const displayedHighlights = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredHighlights.slice(start, start + itemsPerPage);
}, [filteredHighlights, currentPage, itemsPerPage]);

const activeDraggedNote = useMemo(() => {
    if (!activeDraggedNoteId) return null;
    return allPersonalNotes.find((note) => note.id === activeDraggedNoteId) || null;
}, [allPersonalNotes, activeDraggedNoteId]);

const activeDraggedFolder = useMemo(() => {
    if (!activeDraggedFolderId) return null;
    return folderById.get(activeDraggedFolderId) || null;
}, [folderById, activeDraggedFolderId]);

const resetPersonalNotesSelection = () => {
    setNoteSmartFilter('NONE');
    setNoteTagFilter(null);
    setNoteCategoryFilter('ALL');
    setNoteFolderFilter('ALL');
    onPageChange(1);
};

const selectFavoritePersonalNotes = () => {
    setNoteSmartFilter('FAVORITES');
    setNoteTagFilter(null);
    setNoteCategoryFilter('ALL');
    setNoteFolderFilter('ALL');
    onPageChange(1);
};

const selectRecentPersonalNotes = () => {
    setNoteSmartFilter('RECENT');
    setNoteTagFilter(null);
    setNoteCategoryFilter('ALL');
    setNoteFolderFilter('ALL');
    onPageChange(1);
};

const clearPersonalNoteTagFilter = () => {
    setNoteTagFilter(null);
    onPageChange(1);
};

const selectPersonalNoteTag = (tagKey: string) => {
    setNoteTagFilter(tagKey);
    onPageChange(1);
};

const selectPersonalNoteCategory = (category: PersonalNoteCategory) => {
    setNoteSmartFilter('NONE');
    setNoteTagFilter(null);
    setNoteCategoryFilter(category);
    setNoteFolderFilter('ALL');
    onPageChange(1);
};

const selectUnfiledPersonalNotes = (category: PersonalNoteCategory) => {
    setNoteSmartFilter('NONE');
    setNoteTagFilter(null);
    setNoteCategoryFilter(category);
    setNoteFolderFilter('__ROOT__');
    onPageChange(1);
};

const togglePersonalFolderCollapse = (category: PersonalNoteCategory) => {
    setCollapsedFolderCategories((prev) => ({ ...prev, [category]: !prev[category] }));
};

const loadMorePersonalFolders = (category: PersonalNoteCategory) => {
    setVisibleFolderCounts((prev) => ({
        ...prev,
        [category]: prev[category] + FOLDER_PAGE_SIZE,
    }));
};

const selectPersonalFolder = (category: PersonalNoteCategory, folderId: string) => {
    setNoteSmartFilter('NONE');
    setNoteTagFilter(null);
    setNoteCategoryFilter(category);
    setNoteFolderFilter(folderId);
    onPageChange(1);
};

const togglePersonalPanel = () => {
    setIsPersonalPanelOpen((prev) => {
        const next = !prev;
        if (isMobileViewport && next) {
            setIsQuickCaptureOpen(false);
        }
        return next;
    });
};

const toggleQuickCapture = () => {
    setIsQuickCaptureOpen((prev) => {
        const next = !prev;
        if (isMobileViewport && next) {
            setIsPersonalPanelOpen(false);
        }
        return next;
    });
};

const handleHighlightSelect = (highlight: (typeof displayedHighlights)[number]) => {
    if (onSelectBookWithTab) {
        onSelectBookWithTab(highlight.source, 'highlights', highlight.id);
    } else {
        onSelectBook(highlight.source);
    }
};

const renderContent = () => {
    if (isStats) {
        return (
            <React.Suspense fallback={
                <CenteredLoadingState />
            }>
                <KnowledgeDashboard
                    items={books}
                    userId={userId}
                    onCategorySelect={(cat) => onCategoryNavigate?.(cat)}
                    onStatusSelect={(status) => onStatusNavigate?.(status)}
                    onNavigateToTab={(tab) => onTabChange?.(tab as any)}
                    onNavigateToTabWithStatus={(tab, status) => {
                        // Dashboard navigation needs to land on the tab *and* apply status after App tab-change resets filters.
                        onCategoryFilterChange(null);
                        onTabChange?.(tab as any);
                        onStatusFilterChange(status);
                    }}
                    onMobileMenuClick={onMobileMenuClick}
                />
            </React.Suspense>
        );
    }

    // Loading State for Search (Debounce visual)
    if (showSearchLoading) {
        return <CenteredLoadingState label="Searching library..." />;
    }

    if (isNotesTab) {
        return (
            <NotesHighlightsView
                highlights={displayedHighlights}
                searchQuery={searchQuery}
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={onPageChange}
                onSelectHighlight={handleHighlightSelect}
                onToggleHighlightFavorite={onToggleHighlightFavorite}
            />
        );
    }

    // PERSONAL NOTES & LIBRARY GRID
    if (displayedBooks.length === 0 && !isPersonalNotes) {
        const emptyIcon = activeTab === 'BOOK'
            ? <BookIcon size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />
            : activeTab === 'MOVIE'
                ? <Film size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />
                : activeTab === 'ARTICLE'
                    ? <FileText size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />
                    : (activeTab as any) === 'PERSONAL_NOTE'
                        ? <PenTool size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />
                        : <Globe size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />;
        return (
            <EmptyStatePanel
                icon={emptyIcon}
                title={`No ${getTabLabel(activeTab).toLowerCase()} found`}
                message={searchQuery ? "Try a different search term." : "Adjust filters or add a new item."}
            />
        );
    }

    return (
        <div className="pb-10 md:pb-20">
            {isPersonalNotes ? (
                <PersonalNotesWorkspace
                    dndSensors={dndSensors}
                    collisionDetection={closestCenter}
                    onDragStart={handleDragStart}
                    onDragCancel={handleDragCancel}
                    onDragEnd={handleDragEnd}
                    isPersonalPanelOpen={isPersonalPanelOpen}
                    onTogglePersonalPanel={togglePersonalPanel}
                    onClosePersonalPanel={() => setIsPersonalPanelOpen(false)}
                    allNotesVisibleCount={allNotesVisibleCount}
                    favoriteNotesVisibleCount={favoriteNotesVisibleCount}
                    recentNotesVisibleCount={recentNotesVisibleCount}
                    noteCategoryFilter={noteCategoryFilter}
                    noteFolderFilter={noteFolderFilter}
                    noteSmartFilter={noteSmartFilter}
                    noteTagFilter={noteTagFilter}
                    isTopTagsOpen={isTopTagsOpen}
                    onToggleTopTags={() => setIsTopTagsOpen((prev) => !prev)}
                    topTagEntries={topTagEntries}
                    noteCategoryCounts={noteCategoryCounts}
                    rootNoteCounts={rootNoteCounts}
                    categoryFolderMap={categoryFolderMap}
                    collapsedFolderCategories={collapsedFolderCategories}
                    visibleFolderCounts={visibleFolderCounts}
                    onSelectAllNotes={resetPersonalNotesSelection}
                    onSelectFavorites={selectFavoritePersonalNotes}
                    onSelectRecent={selectRecentPersonalNotes}
                    onClearTagFilter={clearPersonalNoteTagFilter}
                    onSelectTag={selectPersonalNoteTag}
                    onSelectCategory={selectPersonalNoteCategory}
                    onCreateFolder={handleCreateFolder}
                    onSelectUnfiled={selectUnfiledPersonalNotes}
                    onToggleCategoryCollapse={togglePersonalFolderCollapse}
                    onLoadMoreFolders={loadMorePersonalFolders}
                    onSelectFolder={selectPersonalFolder}
                    onRenameFolder={handleRenameFolder}
                    onDeleteFolder={handleDeleteFolder}
                    categoryLabel={categoryLabel}
                    DroppableZone={DroppableZone}
                    DraggableWrapper={DraggableWrapper}
                    isQuickCaptureOpen={isQuickCaptureOpen}
                    onToggleQuickCapture={toggleQuickCapture}
                    quickCaptureCategory={quickCaptureCategory}
                    onQuickCaptureCategoryChange={setQuickCaptureCategory}
                    selectedFolderName={folderById.get(noteFolderFilter)?.name || noteFolderFilter}
                    showSelectedFolder={noteSmartFilter === 'NONE' && noteFolderFilter !== 'ALL' && noteFolderFilter !== '__ROOT__'}
                    quickNoteTitle={quickNoteTitle}
                    onQuickNoteTitleChange={setQuickNoteTitle}
                    quickNoteBody={quickNoteBody}
                    onQuickNoteBodyChange={setQuickNoteBody}
                    onSaveQuickNote={handleQuickCapture}
                    canSaveQuickNote={hasMeaningfulPersonalNoteContent(quickNoteBody)}
                    displayedBooks={displayedBooks}
                    activeDraggedNoteId={activeDraggedNoteId}
                    onNoteClick={handleNoteCardClick}
                    onToggleFavorite={onToggleFavorite}
                    onDeleteNote={onDeleteBook}
                    getResolvedNoteFolderName={getResolvedNoteFolderName}
                    activeDraggedNote={activeDraggedNote}
                    activeDraggedFolder={activeDraggedFolder}
                />
            ) : (
                <div className="px-3 md:px-0">
                    <StandardLibraryGrid
                        books={displayedBooks}
                        activeTab={activeTab}
                        isMediaTab={isMediaTab}
                        libraryCardDarkBg={libraryCardDarkBg}
                        onSelectBook={onSelectBook}
                        onToggleFavorite={onToggleFavorite}
                        onDeleteBook={onDeleteBook}
                        getCoverUrlForGrid={getCoverUrlForGrid}
                    />
                </div>
            )}

            {/* Pagination Controls */}
            <PaginationControls
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={onPageChange}
            />
        </div>
    );
};

const getTabLogo = (tab: ResourceType | 'NOTES' | 'DASHBOARD' | 'INSIGHTS' | 'INGEST' | 'FLOW' | 'RAG_SEARCH' | 'SMART_SEARCH' | 'PROFILE') => {
    switch (tab) {
        case 'DASHBOARD': return KnowledgeBaseLogo;
        case 'NOTES': return HighlightsLogo;
        case 'BOOK': return BooksLogo;
        case 'MOVIE': return BooksLogo;
        case 'ARTICLE': return ArticlesLogo;
        case 'PERSONAL_NOTE': return NotesLogo;
        default: return Library;
    }
};

const TabLogo = getTabLogo(activeTab);
const headerSubtitle = isNotesTab
    ? `${stats.total} Highlights`
    : (isPersonalNotes
        ? `${stats.total} Notes`
        : `${stats.total} Items • ${stats.reading} ${isMediaTab ? 'Watching' : 'Reading'}`);
const primaryActionLabel = activeTab === 'ARTICLE'
    ? 'Add Article'
    : (activeTab === 'PERSONAL_NOTE' ? 'Add Note' : (isMediaTab ? 'Add Media' : 'Add Book'));
const handlePrimaryAction = () => {
    if (isPersonalNotes && onAddPersonalNote) {
        const category: PersonalNoteCategory = noteCategoryFilter === 'ALL' || noteCategoryFilter === 'PRIVATE' ? noteCategoryFilter === 'PRIVATE' ? 'PRIVATE' : 'DAILY' : noteCategoryFilter;
        const folderId = noteFolderFilter === 'ALL' || noteFolderFilter === '__ROOT__'
            ? undefined
            : noteFolderFilter;
        onAddPersonalNote({ category, folderId, folderPath: folderId ? folderById.get(folderId)?.name : undefined });
        return;
    }
    onAddBook();
};
const isFavoritesActive = statusFilter === 'FAVORITES';
const toggleFavoritesFilter = () => onStatusFilterChange(isFavoritesActive ? 'ALL' : 'FAVORITES');

return (
    <div className="max-w-6xl w-full mx-auto pb-24 pt-2 md:p-8 lg:p-10 animate-in fade-in duration-500">
        {/* Compact Header for Mobile (Hide in Dashboard) */}
        {!isStats && (
            <div className="px-3 md:px-0">
                <LibraryPageHeader
                    title={getTabLabel(activeTab)}
                    subtitle={headerSubtitle}
                    Icon={TabLogo}
                    primaryActionLabel={primaryActionLabel}
                    onPrimaryAction={handlePrimaryAction}
                    onMobileMenuClick={onMobileMenuClick}
                />
            </div>
        )}
        {/* Mobile Menu Trigger for Dashboard (Only button, no text) */}
        {/* Mobile Menu Trigger for Dashboard removed - moved inside Dashboard for alignment */}

        {/* Compact Filters for Mobile (Hide in Stats view) */}
        {!isStats && (
            <div className="px-3 md:px-0">
                <LibraryFiltersBar
                    searchPlaceholder={getSearchPlaceholder()}
                    localInput={localInput}
                    onLocalInputChange={setLocalInput}
                    showSearchLoading={showSearchLoading}
                    showFavoritesToggle={isNotesTab || isPersonalNotes}
                    isFavoritesActive={isFavoritesActive}
                    onToggleFavorites={toggleFavoritesFilter}
                    showStandardFilters={!isNotesTab && !isPersonalNotes}
                    statusFilter={statusFilter}
                    onStatusChange={onStatusFilterChange}
                    sortOption={sortOption}
                    onSortChange={onSortOptionChange}
                    showCategoryFilter={activeTab === 'BOOK'}
                    categoryFilter={categoryFilter}
                    categoryOptions={CATEGORIES}
                    onCategoryChange={onCategoryFilterChange}
                    showPublisherFilter={activeTab === 'ARTICLE'}
                    publisherFilter={publisherFilter}
                    onPublisherFilterChange={onPublisherFilterChange}
                    showMediaTypeFilter={isMediaTab}
                    mediaTypeFilter={mediaTypeFilter}
                    onMediaTypeFilterChange={setMediaTypeFilter}
                    isMediaTab={isMediaTab}
                    onPageReset={() => onPageChange(1)}
                />
            </div>
        )}

        {/* Active Category Filter Pill */}
        {activeTab === 'BOOK' && !isStats && categoryFilter && (
            <ActiveCategoryFilterPill
                category={categoryFilter}
                onClear={() => onCategoryFilterChange?.(null)}
            />
        )}

        {/* Content Views */}
        {renderContent()}

        {isPersonalNotes && undoMove && (
            <NoteMoveUndoToast
                onUndo={() => {
                    window.clearTimeout(undoMove.timeoutId);
                    const target = undoMove;
                    setUndoMove(null);
                    performMove(target.noteId, target.category, target.folderId, false);
                }}
            />
        )}
    </div>
);
});
const getCoverUrlForGrid = (coverUrl: string): string => {
    const raw = String(coverUrl || "").trim();
    if (!raw) return raw;

    // OpenLibrary `-L` images are large; the grid cards are small, so prefer `-M` to reduce bytes/latency.
    // Keep querystring intact (e.g. `?default=false`).
    const openLibrarySized = raw.replace(/-L(\.(?:jpe?g|png|webp))(\?.*)?$/i, "-M$1$2");

    // TMDb posters default to w500; the grid cards are small, so prefer w342 to reduce bytes/latency.
    return openLibrarySized.replace(
        /(https?:\/\/image\.tmdb\.org\/t\/p\/)(original|w\d+)(\/)/i,
        "$1w342$3"
    );
};
