import React, { useMemo, useState, useEffect } from 'react';
import { LibraryItem, ReadingStatus, ResourceType, PhysicalStatus, PersonalNoteCategory, PersonalNoteFolder } from '../types';
import { Search, Plus, Book as BookIcon, Filter, FileText, Globe, ExternalLink, StickyNote, Quote, ArrowRight, PenTool, BarChart2, AlertTriangle, Library, ArrowUpDown, Calendar, Clock3, Hash, Menu, Trash2, ChevronDown, ChevronLeft, ChevronRight, Loader2, Star, CheckCircle, Zap, X, Folder, ListFilter, GripVertical, Pencil, FolderPlus } from 'lucide-react';
import {
    DndContext,
    DragOverlay,
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
import { restrictToWindowEdges } from '@dnd-kit/modifiers';
import { CATEGORIES } from './CategorySelector';
import {
    KnowledgeBaseLogo,
    HighlightsLogo,
    BooksLogo,
    ArticlesLogo,
    WebsitesLogo,
    NotesLogo
} from './ui/FeatureLogos';
import { isInsightType } from '../lib/highlightType';
import { getPersonalNoteCategory, isPersonalNote } from '../lib/personalNotePolicy';
import { extractPersonalNoteText, hasMeaningfulPersonalNoteContent } from '../lib/personalNoteRender';
import { PersonalNoteEditor } from './PersonalNoteEditor';
const KnowledgeDashboard = React.lazy(() => import('./dashboard/KnowledgeDashboard').then(module => ({ default: module.KnowledgeDashboard })));
type NoteSmartFilter = 'NONE' | 'FAVORITES' | 'RECENT';
const normalizeTagKey = (tag: string): string => tag.trim().toLowerCase();
const FOLDER_PAGE_SIZE = 10;

type DraggableRenderProps = {
    setNodeRef: (element: HTMLElement | null) => void;
    style: React.CSSProperties;
    isDragging: boolean;
    attributes: Record<string, unknown>;
    listeners: Record<string, unknown>;
};

const DraggableWrapper: React.FC<{
    id: string;
    children: (props: DraggableRenderProps) => React.ReactNode;
}> = ({ id, children }) => {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useDraggable({ id });
    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    } as React.CSSProperties;
    return <>{children({ setNodeRef, style, isDragging, attributes: attributes as Record<string, unknown>, listeners: listeners as Record<string, unknown> })}</>;
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
    activeTab: ResourceType | 'NOTES' | 'DASHBOARD';
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
    onTabChange?: (tab: ResourceType | 'NOTES' | 'DASHBOARD') => void;
}

export const BookList: React.FC<BookListProps> = React.memo(({ books, personalNoteFolders = [], onAddBook, onAddPersonalNote, onQuickCreatePersonalNote, onCreatePersonalFolder, onRenamePersonalFolder, onDeletePersonalFolder, onMovePersonalNote, onMovePersonalFolder, onSelectBook, onSelectBookWithTab, activeTab, onMobileMenuClick, onDeleteBook, onDeleteMultiple, onToggleFavorite, onToggleHighlightFavorite, userId, categoryFilter, onCategoryFilterChange, onCategoryNavigate, onStatusNavigate, currentPage, onPageChange, searchQuery, onSearchChange, statusFilter, onStatusFilterChange, sortOption, onSortOptionChange, publisherFilter, onPublisherFilterChange, onTabChange }) => {
    // UI State (Moved to App.tsx for persistence)
    const [isTyping, setIsTyping] = useState(false); // Visual feedback

    // Pagination State (Moved to App.tsx) - using props instead

    const statusColors = {
        'To Read': 'bg-[#94A3B8]/15 text-[#94A3B8] border border-[#94A3B8]/40',
        'Reading': 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/40',
        'Finished': 'bg-[#22C55E]/15 text-[#22C55E] border border-[#22C55E]/40',
    };

    const isStats = activeTab === 'DASHBOARD';
    const isNotesTab = activeTab === 'NOTES';
    const isPersonalNotes = activeTab === 'PERSONAL_NOTE';
    const [noteCategoryFilter, setNoteCategoryFilter] = useState<'ALL' | PersonalNoteCategory>('ALL');
    const [noteFolderFilter, setNoteFolderFilter] = useState<'ALL' | '__ROOT__' | string>('ALL');
    const [noteSmartFilter, setNoteSmartFilter] = useState<NoteSmartFilter>('NONE');
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
    const [quickCaptureCategory, setQuickCaptureCategory] = useState<PersonalNoteCategory>('DAILY');
    const [quickNoteTitle, setQuickNoteTitle] = useState('');
    const [quickNoteBody, setQuickNoteBody] = useState('');
    const [activeDraggedNoteId, setActiveDraggedNoteId] = useState<string | null>(null);
    const [activeDraggedFolderId, setActiveDraggedFolderId] = useState<string | null>(null);
    const [undoMove, setUndoMove] = useState<{ noteId: string; category: PersonalNoteCategory; folderId?: string; timeoutId: number } | null>(null);

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

    // --- PAGE SIZE CONFIGURATION ---
    const itemsPerPage = useMemo(() => {
        switch (activeTab) {
            case 'BOOK': return 24;
            case 'ARTICLE': return 24;
            case 'WEBSITE': return 24;
            case 'PERSONAL_NOTE': return 30;
            case 'NOTES': return 50;
            default: return 24;
        }
    }, [activeTab]);

    // --- PERFORMANCE OPTIMIZATION: DEBOUNCING ---
    // Updates the actual search query 300ms after the user STOPS typing.
    // This prevents the heavy filtering logic from running on every keystroke.
    const [localInput, setLocalInput] = useState(searchQuery);

    useEffect(() => {
        if (localInput !== searchQuery) {
            setIsTyping(true);
            const timer = setTimeout(() => {
                onSearchChange(localInput);
                onPageChange(1); // Reset pagination on new search
                setIsTyping(false);
            }, 300);

            return () => clearTimeout(timer);
        }
    }, [localInput, searchQuery, onSearchChange, onPageChange]);

    // Keep local input in sync if searchQuery is reset from parent (e.g. tab change)
    useEffect(() => {
        setLocalInput(searchQuery);
    }, [searchQuery]);

    // Pagination reset on tab change is handled in App.tsx

    // Filters are now controlled by props, reset is handled in App.tsx handleTabChange

    // --- FILTER & ENRICH LOGIC ---
    const filteredBooks = useMemo(() => {
        if (isNotesTab || isStats) return [];

        const term = searchQuery.toLowerCase().trim();
        const recentNoteIdsForFilter = (isPersonalNotes && noteSmartFilter === 'RECENT')
            ? new Set(
                books
                    .filter((item) => item.type === 'PERSONAL_NOTE' && getPersonalNoteCategory(item) !== 'PRIVATE')
                    .sort((a, b) => b.addedAt - a.addedAt)
                    .slice(0, 20)
                    .map((item) => item.id)
            )
            : null;

        const result = books.filter(book => {
            if (book.type !== activeTab) return false;
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
                if (noteTagFilter) {
                    const normalizedTags = new Set((book.tags || []).map((tag) => normalizeTagKey(tag)));
                    if (!normalizedTags.has(noteTagFilter)) {
                        return false;
                    }
                }
            }
            if (categoryFilter) {
                const target = categoryFilter.toLowerCase();
                const hasCategory = (book.tags || []).some(tag => tag.toLowerCase() === target);
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
            if (publisherFilter && activeTab !== 'BOOK') {
                if (!book.publisher?.toLowerCase().includes(publisherFilter.toLowerCase())) {
                    return false;
                }
            }

            // 4. Search Term (Slowest check, do last)
            if (!term) return true;

            // Check indexed fields (Title, Author, ISBN) first
            const titleMatch = book.title.toLowerCase().includes(term);
            if (titleMatch) return true;

            const authorMatch = book.author.toLowerCase().includes(term);
            if (authorMatch) return true;

            // Type specific efficient checks
            if (activeTab === 'BOOK') {
                if (book.isbn && book.isbn.includes(term)) return true;
                if (book.code && book.code.toLowerCase().includes(term)) return true;
            }

            // Deep search (Notes, Tags) - only if primary fields failed
            const tagsMatch = book.tags.some(tag => tag.toLowerCase().includes(term));
            if (tagsMatch) return true;

            const notesMatch = extractPersonalNoteText(book.generalNotes || '').toLowerCase().includes(term);
            if (notesMatch) return true;

            if (isPersonalNote(book)) {
                const categoryMatch = getPersonalNoteCategory(book).toLowerCase().includes(term);
                if (categoryMatch) return true;
                const folderMatch = (getResolvedNoteFolderName(book) || '').toLowerCase().includes(term);
                if (folderMatch) return true;
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

    }, [books, searchQuery, statusFilter, publisherFilter, sortOption, activeTab, isNotesTab, isStats, categoryFilter, isPersonalNotes, noteCategoryFilter, noteFolderFilter, noteSmartFilter, noteTagFilter, folderById, legacyFolderLookup]);

    const allPersonalNotes = useMemo(
        () => books.filter((book) => book.type === 'PERSONAL_NOTE'),
        [books]
    );

    const nonPrivatePersonalNotes = useMemo(
        () => allPersonalNotes.filter((note) => getPersonalNoteCategory(note) !== 'PRIVATE'),
        [allPersonalNotes]
    );

    const allNotesVisibleCount = nonPrivatePersonalNotes.length;

    const favoriteNotesVisibleCount = useMemo(
        () => nonPrivatePersonalNotes.filter((note) => note.isFavorite).length,
        [nonPrivatePersonalNotes]
    );

    const recentVisibleNoteIds = useMemo(
        () => [...nonPrivatePersonalNotes]
            .sort((a, b) => b.addedAt - a.addedAt)
            .slice(0, 20)
            .map((note) => note.id),
        [nonPrivatePersonalNotes]
    );

    const recentNotesVisibleCount = recentVisibleNoteIds.length;
    const topTagEntries = useMemo(() => {
        const tagMap = new Map<string, { label: string; noteIds: Set<string> }>();
        nonPrivatePersonalNotes.forEach((note) => {
            const seenInNote = new Set<string>();
            (note.tags || []).forEach((rawTag) => {
                const trimmed = rawTag.trim();
                if (!trimmed) return;
                const key = normalizeTagKey(trimmed);
                if (seenInNote.has(key)) return;
                seenInNote.add(key);
                const entry = tagMap.get(key);
                if (!entry) {
                    tagMap.set(key, { label: trimmed, noteIds: new Set([note.id]) });
                    return;
                }
                entry.noteIds.add(note.id);
            });
        });

        return [...tagMap.entries()]
            .map(([key, value]) => ({ key, label: value.label || key, count: value.noteIds.size }))
            .sort((a, b) => (b.count - a.count) || a.label.localeCompare(b.label))
            .slice(0, 10);
    }, [nonPrivatePersonalNotes]);

    const noteCategoryCounts = useMemo(() => {
        const counts: Record<PersonalNoteCategory, number> = { PRIVATE: 0, DAILY: 0, IDEAS: 0 };
        allPersonalNotes.forEach((note) => {
            counts[getPersonalNoteCategory(note)] += 1;
        });
        return counts;
    }, [allPersonalNotes]);

    const categoryFolderMap = useMemo(() => {
        const result: Record<PersonalNoteCategory, Array<{ id: string; name: string; count: number; order: number }>> = {
            PRIVATE: [],
            DAILY: [],
            IDEAS: [],
        };
        personalNoteFolders.forEach((folder) => {
            result[folder.category].push({
                id: folder.id,
                name: folder.name,
                order: folder.order,
                count: allPersonalNotes.filter((note) => getResolvedNoteFolderId(note) === folder.id).length,
            });
        });
        (['PRIVATE', 'DAILY', 'IDEAS'] as PersonalNoteCategory[]).forEach((category) => {
            result[category].sort((a, b) => (a.order - b.order) || a.name.localeCompare(b.name));
        });
        return result;
    }, [allPersonalNotes, personalNoteFolders, legacyFolderLookup]);

    const rootNoteCounts = useMemo(() => {
        const counts: Record<PersonalNoteCategory, number> = { PRIVATE: 0, DAILY: 0, IDEAS: 0 };
        allPersonalNotes.forEach((note) => {
            const category = getPersonalNoteCategory(note);
            if (!getResolvedNoteFolderId(note)) {
                counts[category] += 1;
            }
        });
        return counts;
    }, [allPersonalNotes, legacyFolderLookup]);

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

    // --- AGGREGATE HIGHLIGHTS ---
    const filteredHighlights = useMemo(() => {
        if (!isNotesTab) return [];

        const term = searchQuery.toLowerCase();

        return books
            .flatMap(book => book.highlights.map(h => ({ ...h, source: book })))
            .filter(item => {
                // 1. Status Filter
                if (statusFilter === 'FAVORITES') {
                    if (!item.isFavorite) return false;
                }

                if (!term) return true;
                return item.text.toLowerCase().includes(term) ||
                    (item.comment && item.comment.toLowerCase().includes(term)) ||
                    item.source.title.toLowerCase().includes(term) ||
                    item.source.author.toLowerCase().includes(term) ||
                    (item.tags && item.tags.some(t => t.toLowerCase().includes(term)));
            })
            .sort((a, b) => b.createdAt - a.createdAt);
    }, [books, isNotesTab, searchQuery, statusFilter]);

    // --- STATS CALCULATION ---
    const stats = useMemo(() => {
        if (isNotesTab) {
            return {
                total: filteredHighlights.length,
                reading: 0,
                toRead: 0
            };
        }
        return {
            total: filteredBooks.length,
            reading: filteredBooks.filter(b => b.readingStatus === 'Reading').length,
            toRead: filteredBooks.filter(b => b.readingStatus === 'To Read').length
        };
    }, [isNotesTab, filteredHighlights.length, filteredBooks]);

    const getTabLabel = (type: ResourceType | 'NOTES' | 'DASHBOARD') => {
        switch (type) {
            case 'BOOK': return 'Books';
            case 'ARTICLE': return 'Articles';
            case 'WEBSITE': return 'Websites';
            case 'PERSONAL_NOTE': return 'Personal Notes';
            case 'NOTES': return 'All Notes';
            case 'DASHBOARD': return 'Dashboard';
        }
    };

    const getSearchPlaceholder = () => {
        if (isNotesTab) return "Search quotes...";
        if (activeTab === 'PERSONAL_NOTE') return "Search notes...";
        if (activeTab === 'ARTICLE') return "Search title, author...";
        if (activeTab === 'WEBSITE') return "Search site, URL...";
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
        const raw = window.prompt(`${categoryLabel(category)} klasor adi:`);
        const folderName = raw?.trim();
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
        const raw = window.prompt('Yeni klasor adi:', currentName);
        const nextName = raw?.trim();
        if (!nextName || nextName === currentName) return;
        await onRenamePersonalFolder?.(folderId, nextName);
    };

    const handleDeleteFolder = async (folderId: string) => {
        const ok = window.confirm('Bu klasor silinsin mi? Icindeki notlar kategori kokune tasinacak.');
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
    const libraryCardDarkBg = (activeTab === 'ARTICLE' || activeTab === 'WEBSITE') ? 'dark:bg-slate-800' : 'dark:bg-slate-900';

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



    // --- PAGINATION CONTROLS ---
    const renderPagination = () => {
        if (totalPages <= 1) return null;

        const getPageNumbers = () => {
            const pages = [];
            const maxVisiblePages = 5;

            if (totalPages <= maxVisiblePages) {
                for (let i = 1; i <= totalPages; i++) pages.push(i);
            } else {
                if (currentPage <= 3) {
                    pages.push(1, 2, 3, 4, '...', totalPages);
                } else if (currentPage >= totalPages - 2) {
                    pages.push(1, '...', totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
                } else {
                    pages.push(1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages);
                }
            }
            return pages;
        };

        return (
            <div className="flex justify-center items-center gap-2 mt-8 md:mt-12 select-none">
                <button
                    onClick={() => onPageChange(Math.max(currentPage - 1, 1))}
                    disabled={currentPage === 1}
                    className="p-2 rounded-lg border border-[#E6EAF2] dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 hover:text-[#262D40] dark:hover:text-[#262D40]/82 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    <ChevronLeft size={20} />
                </button>

                <div className="flex items-center gap-1">
                    {getPageNumbers().map((page, idx) => (
                        <React.Fragment key={idx}>
                            {page === '...' ? (
                                <span className="px-2 text-slate-400">...</span>
                            ) : (
                                <button
                                    onClick={() => onPageChange(page as number)}
                                    className={`w-8 h-8 md:w-10 md:h-10 rounded-lg text-sm font-medium transition-colors ${currentPage === page
                                        ? 'bg-[#262D40]/40 text-white shadow-md shadow-[#262D40]/12 dark:shadow-none'
                                        : 'text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 hover:text-[#262D40] dark:hover:text-[#262D40]/82'
                                        }`}
                                >
                                    {page}
                                </button>
                            )}
                        </React.Fragment>
                    ))}
                </div>

                <button
                    onClick={() => onPageChange(Math.min(currentPage + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    className="p-2 rounded-lg border border-[#E6EAF2] dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 hover:text-[#262D40] dark:hover:text-[#262D40]/82 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    <ChevronRight size={20} />
                </button>
            </div>
        );
    };

    const renderContent = () => {
        if (isStats) {
            return (
                <React.Suspense fallback={
                    <div className="flex justify-center items-center py-20">
                        <Loader2 size={32} className="animate-spin text-[#262D40]/90" />
                    </div>
                }>
                    <KnowledgeDashboard
                        items={books}
                        onCategorySelect={(cat) => onCategoryNavigate?.(cat)}
                        onStatusSelect={(status) => onStatusNavigate?.(status)}
                        onNavigateToTab={(tab) => onTabChange?.(tab as any)}
                    />
                </React.Suspense>
            );
        }

        // Loading State for Search (Debounce visual)
        if (isTyping) {
            return (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400 animate-in fade-in duration-200">
                    <Loader2 size={32} className="animate-spin text-[#262D40]/90 mb-4" />
                    <p>Searching library...</p>
                </div>
            );
        }

        if (isNotesTab) {
            if (displayedHighlights.length === 0) {
                return (
                    <div className="text-center py-12 md:py-20 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                        <div className="bg-[#F3F5FA] dark:bg-slate-800 w-12 h-12 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4">
                            <StickyNote size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />
                        </div>
                        <h3 className="text-base md:text-lg font-medium text-slate-900 dark:text-white">No highlights found</h3>
                        <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm max-w-xs mx-auto mt-2">
                            {searchQuery ? "Try a different search term." : "Highlights added to books appear here."}
                        </p>
                    </div>
                );
            }

            return (
                <div className="pb-20">
                    <div className="columns-2 lg:columns-3 gap-3 md:gap-6 space-y-3 md:space-y-6">
                        {displayedHighlights.map((highlight, idx) => {
                            const isNote = isInsightType(highlight.type);
                            return (
                                <div
                                    key={`${highlight.id}-${idx}`}
                                    onClick={() => {
                                        if (onSelectBookWithTab) {
                                            onSelectBookWithTab(highlight.source, 'highlights', highlight.id);
                                        } else {
                                            onSelectBook(highlight.source);
                                        }
                                    }}
                                    className={`break-inside-avoid p-3 md:p-6 rounded-xl border hover:shadow-md transition-all group cursor-pointer relative flex flex-col ${isNote
                                        ? 'bg-white dark:bg-slate-800 border-[#E6EAF2] dark:border-slate-700 hover:border-[#262D40]/12 dark:hover:border-[#262D40]/30'
                                        : 'bg-white dark:bg-slate-800 border-[#E6EAF2] dark:border-slate-700 hover:border-[#262D40]/12 dark:hover:border-[#262D40]/30'
                                        }`}
                                >
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            if (onToggleHighlightFavorite) {
                                                onToggleHighlightFavorite(highlight.source.id, highlight.id);
                                            }
                                        }}
                                        className={`absolute top-2 right-2 p-1.5 rounded-full transition-all shadow-sm z-10 ${highlight.isFavorite
                                            ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-500 dark:text-orange-400 opacity-100'
                                            : 'bg-white/80 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500 hover:text-orange-500 dark:hover:text-orange-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                            }`}
                                        title={highlight.isFavorite ? "Remove from Favorites" : "Add to Favorites"}
                                    >
                                        <Star size={14} fill={highlight.isFavorite ? "currentColor" : "none"} />
                                    </button>
                                    <div className="mb-2 md:mb-3">
                                        {isNote ? (
                                            <StickyNote className="text-[#CC561E] fill-[#CC561E]/10 w-4 h-4 md:w-6 md:h-6" />
                                        ) : highlight.source?.type === 'ARTICLE' ? (
                                            <ArticlesLogo size={18} className="text-[#262D40]/85 md:w-6 md:h-6" />
                                        ) : highlight.source?.type === 'WEBSITE' ? (
                                            <WebsitesLogo size={18} className="text-[#262D40]/85 md:w-6 md:h-6" />
                                        ) : (
                                            <Quote className="text-[#262D40]/82 fill-[#262D40]/85 w-4 h-4 md:w-6 md:h-6" />
                                        )}
                                    </div>
                                    <p className={`text-xs md:text-base leading-relaxed mb-2 md:mb-4 whitespace-pre-wrap line-clamp-[8] md:line-clamp-none font-lora ${isNote ? 'text-slate-700 dark:text-slate-300' : 'text-slate-900 dark:text-slate-200'}`}>
                                        {highlight.text}
                                    </p>

                                    {highlight.tags && highlight.tags.length > 0 && (
                                        <div className="flex flex-wrap gap-1 mb-2 md:mb-3">
                                            {highlight.tags.map((tag, i) => (
                                                <span key={i} className="px-1.5 md:px-2 py-0.5 md:py-1 bg-[#F3F5FA] dark:bg-slate-700/50 border border-[#E6EAF2] dark:border-white/10 rounded text-[10px] md:text-xs text-slate-500 dark:text-slate-400 flex items-center gap-0.5">
                                                    <Hash size={10} className="md:w-3 md:h-3" /> {tag}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    <div className={`pt-2 md:pt-4 mt-auto flex items-center justify-between border-t ${isNote ? 'border-[#E6EAF2]' : 'border-[#262D40]/50'}`}>
                                        <div className="flex-1 min-w-0">
                                            <h4 className="text-xs md:text-sm font-bold text-slate-900 dark:text-white truncate">{highlight.source.title}</h4>
                                            <div className="flex items-center gap-1 md:gap-2 text-[10px] md:text-xs text-slate-500 dark:text-slate-400">
                                                <span className="truncate max-w-[50%]">{highlight.source.author}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {renderPagination()}
                </div>
            );
        }

        // PERSONAL NOTES & LIBRARY GRID
        if (displayedBooks.length === 0 && !isPersonalNotes) {
            return (
                <div className="text-center py-12 md:py-20 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                    <div className="bg-[#F3F5FA] dark:bg-slate-800 w-12 h-12 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4">
                        {activeTab === 'BOOK' ? <BookIcon size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" /> :
                            activeTab === 'ARTICLE' ? <FileText size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" /> :
                                activeTab === 'PERSONAL_NOTE' ? <PenTool size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" /> :
                                    <Globe size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />}
                    </div>
                    <h3 className="text-base md:text-lg font-medium text-slate-900 dark:text-white">No {getTabLabel(activeTab).toLowerCase()} found</h3>
                    <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm max-w-xs mx-auto mt-2">
                        {searchQuery ? "Try a different search term." : "Adjust filters or add a new item."}
                    </p>
                </div>
            );
        }

        return (
            <div className="pb-20">
                {isPersonalNotes ? (
                    <DndContext
                        sensors={dndSensors}
                        collisionDetection={closestCenter}
                        modifiers={[restrictToWindowEdges]}
                        onDragStart={handleDragStart}
                        onDragCancel={handleDragCancel}
                        onDragEnd={handleDragEnd}
                    >
                        <div className="grid grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)] gap-4 md:gap-6">
                        <aside className={`bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-xl p-3 md:p-4 h-fit ${isPersonalPanelOpen ? 'block' : 'hidden lg:block'}`}>
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500 flex items-center gap-2">
                                    <ListFilter size={14} />
                                    Note Space
                                </h3>
                                <button
                                    onClick={() => setIsPersonalPanelOpen(false)}
                                    className="lg:hidden text-slate-400 hover:text-slate-700"
                                >
                                    <X size={16} />
                                </button>
                            </div>

                            <div className="space-y-2">
                                <button
                                    onClick={() => {
                                        setNoteSmartFilter('NONE');
                                        setNoteTagFilter(null);
                                        setNoteCategoryFilter('ALL');
                                        setNoteFolderFilter('ALL');
                                        onPageChange(1);
                                    }}
                                    className={`w-full text-left px-2.5 py-2 rounded-lg text-sm transition-colors ${noteCategoryFilter === 'ALL' && noteFolderFilter === 'ALL' && noteSmartFilter === 'NONE' && !noteTagFilter ? 'bg-[#262D40]/20 text-[#262D40] dark:text-white font-semibold' : 'hover:bg-[#F3F5FA] dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300'}`}
                                >
                                    All Notes ({allNotesVisibleCount})
                                </button>
                                <div className="rounded-lg border border-[#E6EAF2] dark:border-slate-800 p-2">
                                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-1">Smart Folders</p>
                                    <button
                                        onClick={() => {
                                            setNoteSmartFilter('FAVORITES');
                                            setNoteTagFilter(null);
                                            setNoteCategoryFilter('ALL');
                                            setNoteFolderFilter('ALL');
                                            onPageChange(1);
                                        }}
                                        className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors flex items-center justify-between ${noteSmartFilter === 'FAVORITES' ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                                    >
                                        <span className="inline-flex items-center gap-1.5">
                                            <Star size={12} />
                                            Favorites
                                        </span>
                                        <span className="text-[10px] opacity-70">{favoriteNotesVisibleCount}</span>
                                    </button>
                                    <button
                                        onClick={() => {
                                            setNoteSmartFilter('RECENT');
                                            setNoteTagFilter(null);
                                            setNoteCategoryFilter('ALL');
                                            setNoteFolderFilter('ALL');
                                            onPageChange(1);
                                        }}
                                        className={`mt-1 w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors flex items-center justify-between ${noteSmartFilter === 'RECENT' ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                                    >
                                        <span className="inline-flex items-center gap-1.5">
                                            <Clock3 size={12} />
                                            Recent Notes
                                        </span>
                                        <span className="text-[10px] opacity-70">{recentNotesVisibleCount}</span>
                                    </button>
                                    <div className="mt-2 border-t border-[#E6EAF2] dark:border-slate-800 pt-2">
                                        <div className="flex items-center justify-between mb-1">
                                            <button
                                                onClick={() => setIsTopTagsOpen((prev) => !prev)}
                                                className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 inline-flex items-center gap-1 hover:text-slate-700 dark:hover:text-slate-300"
                                            >
                                                <ChevronDown size={11} className={`transition-transform ${isTopTagsOpen ? 'rotate-180' : ''}`} />
                                                Top Tags
                                            </button>
                                            {noteTagFilter && (
                                                <button
                                                    onClick={() => {
                                                        setNoteTagFilter(null);
                                                        onPageChange(1);
                                                    }}
                                                    className="text-[10px] text-[#CC561E] hover:underline"
                                                >
                                                    Clear tag filter
                                                </button>
                                            )}
                                        </div>
                                        {isTopTagsOpen && (
                                            topTagEntries.length === 0 ? (
                                                <p className="text-[11px] text-slate-400 px-1 py-1">No tags yet</p>
                                            ) : (
                                                <div className="space-y-1">
                                                    {topTagEntries.map((tag) => (
                                                        <button
                                                            key={tag.key}
                                                            onClick={() => {
                                                                setNoteTagFilter(tag.key);
                                                                onPageChange(1);
                                                            }}
                                                            className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors flex items-center justify-between ${noteTagFilter === tag.key ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                                                        >
                                                            <span className="truncate">#{tag.label}</span>
                                                            <span className="text-[10px] opacity-70">{tag.count}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            )
                                        )}
                                    </div>
                                </div>
                                {(['PRIVATE', 'DAILY', 'IDEAS'] as PersonalNoteCategory[]).map((category) => (
                                    <DroppableZone key={category} id={`cat-group:${category}`}>
                                        {(isOverCategory) => (
                                            <div className={`rounded-lg border p-2 ${isOverCategory ? 'border-[#CC561E]/40 bg-[#CC561E]/5' : 'border-[#E6EAF2] dark:border-slate-800'}`}>
                                        <div className="flex items-center justify-between mb-1">
                                            <button
                                                onClick={() => {
                                                    setNoteSmartFilter('NONE');
                                                    setNoteTagFilter(null);
                                                    setNoteCategoryFilter(category);
                                                    setNoteFolderFilter('ALL');
                                                    onPageChange(1);
                                                }}
                                                className={`text-xs font-semibold uppercase tracking-wide ${noteCategoryFilter === category && noteFolderFilter === 'ALL' && noteSmartFilter === 'NONE' && !noteTagFilter ? 'text-[#CC561E]' : 'text-slate-600 dark:text-slate-300'}`}
                                            >
                                                {categoryLabel(category)} ({noteCategoryCounts[category]})
                                            </button>
                                            <button
                                                onClick={() => handleCreateFolder(category)}
                                                className="text-[11px] text-[#CC561E] hover:underline inline-flex items-center gap-1"
                                            >
                                                <FolderPlus size={11} />
                                                Folder
                                            </button>
                                        </div>
                                        <DroppableZone id={`cat-root:${category}`}>
                                            {(isOver) => (
                                                <button
                                                    onClick={() => {
                                                        setNoteSmartFilter('NONE');
                                                        setNoteTagFilter(null);
                                                        setNoteCategoryFilter(category);
                                                        setNoteFolderFilter('__ROOT__');
                                                        onPageChange(1);
                                                    }}
                                                    className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors ${isOver ? 'bg-[#CC561E]/15 border border-[#CC561E]/30' : 'border border-transparent'} ${noteCategoryFilter === category && noteFolderFilter === '__ROOT__' && noteSmartFilter === 'NONE' && !noteTagFilter ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                                                >
                                                    Unfiled ({rootNoteCounts[category]})
                                                </button>
                                            )}
                                        </DroppableZone>
                                        <div className="mt-1">
                                            <button
                                                onClick={() => setCollapsedFolderCategories((prev) => ({ ...prev, [category]: !prev[category] }))}
                                                className="w-full text-left px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 inline-flex items-center gap-1"
                                            >
                                                <ChevronDown size={11} className={`transition-transform ${collapsedFolderCategories[category] ? '' : 'rotate-180'}`} />
                                                Folders ({categoryFolderMap[category].length})
                                            </button>
                                            {!collapsedFolderCategories[category] && (
                                                <div className="mt-1 space-y-1">
                                                    {categoryFolderMap[category].length === 0 ? (
                                                        <p className="text-[11px] text-slate-400 px-1 py-1">No folders yet</p>
                                                    ) : (
                                                        categoryFolderMap[category].slice(0, visibleFolderCounts[category]).map((folder) => (
                                                            <DroppableZone key={folder.id} id={`folder:${folder.id}`}>
                                                                {(isOver) => (
                                                                    <DraggableWrapper id={`folder-item:${folder.id}`}>
                                                                        {({ setNodeRef, style, isDragging, attributes, listeners }) => (
                                                                            <div
                                                                                ref={setNodeRef}
                                                                                style={isDragging ? undefined : style}
                                                                                className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm flex items-center gap-2 ${isOver ? 'bg-[#CC561E]/15 border border-[#CC561E]/30' : 'border border-transparent'} ${noteCategoryFilter === category && noteFolderFilter === folder.id && noteSmartFilter === 'NONE' && !noteTagFilter ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'} ${isDragging ? 'opacity-60 ring-2 ring-[#CC561E]/40' : ''}`}
                                                                            >
                                                                                <button
                                                                                    {...(attributes as any)}
                                                                                    {...(listeners as any)}
                                                                                    onClick={(e) => e.stopPropagation()}
                                                                                    className="p-1 rounded text-slate-400 hover:text-slate-700 cursor-grab active:cursor-grabbing"
                                                                                    title="Move folder"
                                                                                >
                                                                                    <GripVertical size={12} />
                                                                                </button>
                                                                                <button
                                                                                    onClick={() => {
                                                                                        setNoteSmartFilter('NONE');
                                                                                        setNoteTagFilter(null);
                                                                                        setNoteCategoryFilter(category);
                                                                                        setNoteFolderFilter(folder.id);
                                                                                        onPageChange(1);
                                                                                    }}
                                                                                    className="flex items-center gap-2 flex-1 min-w-0"
                                                                                >
                                                                                    <Folder size={12} />
                                                                                    <span className="truncate">{folder.name}</span>
                                                                                </button>
                                                                                <span className="text-[10px] opacity-70">{folder.count}</span>
                                                                                <button
                                                                                    onClick={() => handleRenameFolder(folder.id, folder.name)}
                                                                                    className="text-slate-400 hover:text-slate-700"
                                                                                    title="Rename folder"
                                                                                >
                                                                                    <Pencil size={12} />
                                                                                </button>
                                                                                <button
                                                                                    onClick={() => handleDeleteFolder(folder.id)}
                                                                                    className="text-slate-400 hover:text-red-500"
                                                                                    title="Delete folder"
                                                                                >
                                                                                    <Trash2 size={12} />
                                                                                </button>
                                                                            </div>
                                                                        )}
                                                                    </DraggableWrapper>
                                                                )}
                                                            </DroppableZone>
                                                        ))
                                                    )}
                                                    {categoryFolderMap[category].length > visibleFolderCounts[category] && (
                                                        <button
                                                            onClick={() =>
                                                                setVisibleFolderCounts((prev) => ({
                                                                    ...prev,
                                                                    [category]: prev[category] + FOLDER_PAGE_SIZE,
                                                                }))
                                                            }
                                                            className="w-full text-left px-2 py-1.5 rounded-md text-[11px] font-semibold text-[#CC561E] hover:bg-[#CC561E]/10"
                                                        >
                                                            Load more ({categoryFolderMap[category].length - visibleFolderCounts[category]} left)
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                        )}
                                    </DroppableZone>
                                ))}
                            </div>

                        </aside>

                        <div className="space-y-3">
                            <div className="lg:hidden">
                                <button
                                    onClick={() => setIsPersonalPanelOpen((prev) => !prev)}
                                    className="px-3 py-2 text-sm bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-lg flex items-center gap-2"
                                >
                                    <ListFilter size={14} />
                                    Note Navigator
                                </button>
                            </div>

                            <div className="bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-2xl p-4 md:p-5">
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <h4 className="text-sm md:text-base font-semibold uppercase tracking-[0.12em] text-slate-500">
                                        Quick Capture
                                    </h4>
                                    <div className="flex items-center gap-2">
                                        <select
                                            value={quickCaptureCategory}
                                            onChange={(e) => setQuickCaptureCategory(e.target.value as PersonalNoteCategory)}
                                            className="text-[11px] border border-[#E6EAF2] dark:border-slate-700 rounded-md px-2 py-1 bg-white dark:bg-slate-950 text-slate-500"
                                        >
                                            <option value="DAILY">Daily</option>
                                            <option value="PRIVATE">Private</option>
                                            <option value="IDEAS">Ideas</option>
                                        </select>
                                        {noteSmartFilter === 'NONE' && noteFolderFilter !== 'ALL' && noteFolderFilter !== '__ROOT__' && (
                                            <span className="text-[11px] text-slate-400">
                                                / {folderById.get(noteFolderFilter)?.name || noteFolderFilter}
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <input
                                    value={quickNoteTitle}
                                    onChange={(e) => setQuickNoteTitle(e.target.value)}
                                    placeholder="Note title (optional)"
                                    className="w-full mb-3 border border-[#E6EAF2] dark:border-slate-700 rounded-xl px-4 py-3 text-sm md:text-base bg-white dark:bg-slate-950"
                                />
                                <PersonalNoteEditor
                                    value={quickNoteBody}
                                    onChange={setQuickNoteBody}
                                    autoFocus={isPersonalNotes}
                                    placeholder="Start writing immediately..."
                                    minHeight={242}
                                />
                                <div className="mt-3 flex justify-end">
                                    <button
                                        onClick={handleQuickCapture}
                                        disabled={!hasMeaningfulPersonalNoteContent(quickNoteBody)}
                                        className="px-4 py-2 rounded-lg bg-[#262D40] text-white text-sm md:text-base disabled:opacity-40"
                                    >
                                        Save Quick Note
                                    </button>
                                </div>
                            </div>

                            {displayedBooks.length === 0 ? (
                                <div className="text-center py-10 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                                    <PenTool size={26} className="mx-auto mb-2 text-slate-300" />
                                    <h3 className="text-base font-medium text-slate-900 dark:text-white">No notes matched this filter</h3>
                                    <p className="text-xs md:text-sm text-slate-500 mt-1">Change category/folder filter or create a new note.</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 md:gap-4">
                                    {displayedBooks.map(note => {
                                        const notePreview = extractPersonalNoteText(note.generalNotes || '');
                                        return (
                                        <DraggableWrapper key={note.id} id={`note:${note.id}`}>
                                            {({ setNodeRef, style, isDragging, attributes, listeners }) => (
                                                <div
                                                    ref={setNodeRef}
                                                    style={isDragging ? undefined : style}
                                                    onClick={() => onSelectBook(note)}
                                                    className={`bg-white dark:bg-slate-800 p-3 md:p-5 rounded-xl border border-[#E6EAF2] dark:border-slate-800 hover:border-[#262D40]/20 dark:hover:border-[#262D40]/30 hover:shadow-md transition-all cursor-pointer flex flex-col group relative ${isDragging || activeDraggedNoteId === note.id ? 'opacity-60 ring-2 ring-[#CC561E]/40' : ''}`}
                                                >
                                                    <div className="absolute top-2 left-2 z-10">
                                                        <button
                                                            {...(attributes as any)}
                                                            {...(listeners as any)}
                                                            onClick={(e) => e.stopPropagation()}
                                                            className="p-1.5 rounded-full bg-white/85 dark:bg-slate-800/85 text-slate-400 hover:text-slate-700 shadow-sm"
                                                            title="Drag note"
                                                        >
                                                            <GripVertical size={13} />
                                                        </button>
                                                    </div>
                                            <div className="absolute top-2 right-2 flex gap-1 z-10">
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); onToggleFavorite(note.id); }}
                                                    className={`p-1.5 rounded-full transition-all shadow-sm ${note.isFavorite
                                                        ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-500 dark:text-orange-400 opacity-100'
                                                        : 'bg-white/80 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500 hover:text-orange-500 dark:hover:text-orange-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                                        }`}
                                                    title={note.isFavorite ? "Remove from Favorites" : "Add to Favorites"}
                                                >
                                                    <Star size={14} fill={note.isFavorite ? "currentColor" : "none"} />
                                                </button>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); onDeleteBook(note.id); }}
                                                    className="p-1.5 bg-white/80 dark:bg-slate-800/80 hover:bg-[#F3F5FA] dark:hover:bg-slate-700 text-slate-400 dark:text-slate-500 hover:text-slate-900 dark:hover:text-white rounded-full transition-all opacity-0 group-hover:opacity-100 focus:opacity-100 shadow-sm"
                                                    title="Delete Note"
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>

                                            <h3 className="font-bold text-sm md:text-base text-slate-900 dark:text-white mb-2 leading-tight pl-8 pr-8">{note.title}</h3>
                                            <div className="text-slate-600 dark:text-slate-300 text-xs md:text-sm whitespace-pre-wrap leading-relaxed max-h-[180px] overflow-hidden relative font-lora mb-3">
                                                {notePreview || <span className="italic text-slate-400 dark:text-slate-500">Empty</span>}
                                                {notePreview.length > 140 && (
                                                    <div className="absolute bottom-0 inset-x-0 h-8 bg-gradient-to-t from-white dark:from-slate-900 to-transparent" />
                                                )}
                                            </div>

                                            <div className="mt-auto pt-2 flex flex-wrap gap-1.5 border-t border-slate-100 dark:border-slate-800 items-center">
                                                <span className="px-2 py-0.5 bg-[#CC561E]/10 text-[#CC561E] text-[10px] md:text-xs rounded border border-[#CC561E]/20 font-semibold">
                                                    {getPersonalNoteCategory(note)}
                                                </span>
                                                {getResolvedNoteFolderName(note) && (
                                                    <span className="px-2 py-0.5 bg-[#F3F5FA] dark:bg-slate-800 text-slate-500 dark:text-slate-400 text-[10px] md:text-xs rounded border border-[#E6EAF2] dark:border-slate-700 truncate max-w-[150px]">
                                                        {getResolvedNoteFolderName(note)}
                                                    </span>
                                                )}
                                                <span className="ml-auto text-[10px] md:text-xs text-slate-400 flex items-center gap-1">
                                                    <Calendar size={10} className="md:w-3 md:h-3" />
                                                    {new Date(note.addedAt).toLocaleDateString()}
                                                </span>
                                            </div>
                                                </div>
                                            )}
                                        </DraggableWrapper>
                                    )})}
                                </div>
                            )}
                        </div>
                        </div>
                        <DragOverlay modifiers={[restrictToWindowEdges]}>
                            {activeDraggedNote ? (
                                <div className="w-[320px] max-w-[80vw] bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#CC561E]/35 shadow-xl cursor-grabbing">
                                    <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{activeDraggedNote.title}</p>
                                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-300 truncate">{categoryLabel(getPersonalNoteCategory(activeDraggedNote))}</p>
                                </div>
                            ) : activeDraggedFolder ? (
                                <div className="w-[220px] max-w-[70vw] bg-white dark:bg-slate-900 px-3 py-2 rounded-lg border border-[#CC561E]/35 shadow-xl cursor-grabbing flex items-center gap-2">
                                    <Folder size={13} className="text-slate-500" />
                                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{activeDraggedFolder.name}</span>
                                </div>
                            ) : null}
                        </DragOverlay>
                    </DndContext>
                ) : (
                    // Standard Grid (Books/Articles/Websites)
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-6">
                        {displayedBooks.map((book) => (
                            <div
                                key={book.id}
                                onClick={() => onSelectBook(book)}
                                className={`bg-white ${libraryCardDarkBg} rounded-xl border border-[#E6EAF2] dark:border-slate-800 overflow-hidden hover:shadow-lg hover:-translate-y-1 transition-all cursor-pointer group flex flex-col h-full relative`}
                            >
                                {/* Compact Cover / Icon Container */}
                                <div className="h-24 md:h-40 bg-[#F3F5FA] dark:bg-slate-800 relative flex items-end justify-between overflow-hidden group-hover:opacity-95 transition-opacity">

                                    {/* Action Buttons Overlay */}
                                    <div className="absolute top-2 right-2 z-40 flex gap-1">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onToggleFavorite(book.id);
                                            }}
                                            className={`p-1.5 rounded-full shadow-sm backdrop-blur-sm border border-[#E6EAF2] dark:border-slate-800 transition-all ${book.isFavorite
                                                ? 'bg-amber-100/90 dark:bg-amber-900/80 text-amber-500 dark:text-amber-400 opacity-100'
                                                : 'bg-white/90 dark:bg-slate-900/90 text-slate-400 dark:text-slate-500 hover:text-amber-500 dark:hover:text-amber-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                                }`}
                                            title={book.isFavorite ? "Remove from Favorites" : "Add to Favorites"}
                                        >
                                            <Star size={14} className="md:w-4 md:h-4" fill={book.isFavorite ? "currentColor" : "none"} />
                                        </button>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onDeleteBook(book.id);
                                            }}
                                            className="p-1.5 bg-white/90 dark:bg-slate-900/90 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-900 dark:hover:text-white rounded-full shadow-sm backdrop-blur-sm border border-[#E6EAF2] dark:border-slate-800 transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                                            title="Delete Item"
                                        >
                                            <Trash2 size={14} className="md:w-4 md:h-4" />
                                        </button>

                                        {/* Ingested Status Badge */}
                                        {book.isIngested && (
                                            <div
                                                className="p-1.5 bg-[#262D40]/90 dark:bg-[#262D40]/90 text-white rounded-full shadow-sm backdrop-blur-sm border border-[#262D40]/50 dark:border-[#262D40]/50 transition-all z-40"
                                                title="Added to AI Library"
                                            >
                                                <CheckCircle size={14} className="md:w-4 md:h-4" fill="currentColor" />
                                            </div>
                                        )}
                                    </div>

                                    {/* Fallback Icon with Bespoke Glow */}
                                    <div className="absolute inset-0 flex items-center justify-center bg-[#F3F5FA] dark:bg-slate-800 transition-colors group-hover:bg-[#EDF1F8] dark:group-hover:bg-slate-700">
                                        <div className="relative">
                                            <div className="absolute inset-0 bg-[#262D40]/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                                            <div className="relative p-4 rounded-full">
                                                {book.type === 'BOOK' ? <BooksLogo size={48} className="text-[#262D40] dark:text-white/80 drop-shadow-[0_0_8px_rgba(38,45,64,0.35)]" /> :
                                                    book.type === 'ARTICLE' ? <ArticlesLogo size={48} className="text-[#262D40] dark:text-white/80 drop-shadow-[0_0_8px_rgba(38,45,64,0.35)]" /> :
                                                        <WebsitesLogo size={48} className="text-[#262D40] dark:text-white/80 drop-shadow-[0_0_8px_rgba(38,45,64,0.35)]" />}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Cover Image with Lazy Loading */}
                                    {book.type === 'BOOK' && book.coverUrl && (
                                        <>
                                            <img
                                                src={book.coverUrl}
                                                alt={book.title}
                                                loading="lazy"
                                                className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105 z-10"
                                                onError={(e) => {
                                                    e.currentTarget.style.display = 'none';
                                                    const gradient = e.currentTarget.nextElementSibling;
                                                    if (gradient) gradient.classList.add('hidden');
                                                }}
                                            />
                                            <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 via-slate-900/20 to-transparent z-20 pointer-events-none" />
                                        </>
                                    )}

                                    {book.type !== 'BOOK' && (
                                        <div className="absolute inset-0 bg-gradient-to-t from-slate-900/60 via-transparent to-transparent z-20 pointer-events-none" />
                                    )}

                                    {/* Status Badges */}
                                    <div className="relative z-30 p-2 md:p-4 w-full flex justify-between items-end">
                                        <div className={`text-[9px] md:text-xs font-bold px-1.5 py-0.5 md:px-2 md:py-1 rounded shadow-sm backdrop-blur-md ${(book.type === 'BOOK' && book.coverUrl) || book.type !== 'BOOK' ? 'bg-white/90 dark:bg-slate-900/90 text-slate-900 dark:text-white border border-white/50 dark:border-slate-700' : statusColors[book.readingStatus]
                                            }`}>
                                            {book.readingStatus}
                                        </div>

                                        <div className="flex gap-0.5 md:gap-1">
                                            {book.type === 'BOOK' && book.status === 'Lent Out' && (
                                                <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-[#F59E0B] text-white flex items-center justify-center shadow-sm border border-white/20" title="Lent Out">
                                                    <AlertTriangle size={10} className="md:w-3 md:h-3" />
                                                </div>
                                            )}
                                            {book.type === 'BOOK' && book.status === 'Lost' && (
                                                <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-[#F43F5E] text-white flex items-center justify-center shadow-sm border border-white/20" title="Lost">
                                                    <AlertTriangle size={10} className="md:w-3 md:h-3" />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Card Body */}
                                <div className="p-3 md:p-5 flex-1 flex flex-col">
                                    <h3 className="font-bold text-sm md:text-lg text-slate-900 dark:text-white leading-tight mb-0.5 md:mb-1 line-clamp-2 group-hover:text-[#262D40] dark:group-hover:text-[#262D40] transition-colors">
                                        {book.title}
                                    </h3>
                                    <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm mb-2 md:mb-4 line-clamp-1">{book.author}</p>

                                    <div className="mt-auto pt-2 md:pt-4 border-t border-slate-50 dark:border-slate-800 flex justify-between items-center text-[10px] md:text-xs text-slate-400 dark:text-slate-500">
                                        <span className="truncate max-w-[70%]">
                                            {book.type === 'BOOK' ? (book.publisher || '') :
                                                book.type === 'ARTICLE' ? (book.publisher || 'Journal') :
                                                    (() => {
                                                        try {
                                                            return book.url ? new URL(book.url).hostname : 'Web';
                                                        } catch {
                                                            return 'Web';
                                                        }
                                                    })()}
                                        </span>
                                        {book.type === 'ARTICLE' && book.publicationYear && (
                                            <span className="bg-[#F3F5FA] dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500 dark:text-slate-400 font-mono">
                                                {book.publicationYear}
                                            </span>
                                        )}
                                        {book.type === 'WEBSITE' && book.url && (
                                            <a href={book.url} target="_blank" rel="noreferrer" className="text-[#262D40]/70 hover:text-[#262D40]" onClick={(e) => e.stopPropagation()}>
                                                <ExternalLink size={12} className="md:w-3.5 md:h-3.5" />
                                            </a>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Pagination Controls */}
                {renderPagination()}
            </div>
        );
    };

    const getTabLogo = (tab: ResourceType | 'NOTES' | 'DASHBOARD') => {
        switch (tab) {
            case 'DASHBOARD': return KnowledgeBaseLogo;
            case 'NOTES': return HighlightsLogo;
            case 'BOOK': return BooksLogo;
            case 'ARTICLE': return ArticlesLogo;
            case 'WEBSITE': return WebsitesLogo;
            case 'PERSONAL_NOTE': return NotesLogo;
            default: return Library;
        }
    };

    const TabLogo = getTabLogo(activeTab);

    return (
        <div className="max-w-6xl w-full mx-auto p-6 md:p-8 lg:p-10 animate-in fade-in duration-500">
            {/* Compact Header for Mobile (Hide in Dashboard) */}
            {!isStats && (
                <div className="flex items-center justify-between mb-4 md:mb-8 gap-2">
                    <div className="flex items-center gap-2 md:gap-4 overflow-hidden flex-1">
                        {/* Mobile Menu Trigger */}
                        <button
                            onClick={onMobileMenuClick}
                            className="lg:hidden p-1.5 md:p-2 -ml-1 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 rounded-lg transition-colors shrink-0"
                        >
                            <Menu size={20} className="md:w-6 md:h-6" />
                        </button>

                        <div className="flex items-center gap-3">
                            <div className="hidden md:flex p-2 bg-[#262D40] rounded-xl border border-[#262D40]/80 shadow-sm">
                                <TabLogo size={24} className="text-white" />
                            </div>
                            <div className="min-w-0 flex flex-col justify-center">
                                <h1 className="text-lg md:text-3xl font-bold text-slate-900 dark:text-white tracking-tight leading-none truncate">
                                    {getTabLabel(activeTab)}
                                </h1>
                                <p className="text-slate-500 dark:text-slate-400 text-[10px] md:text-sm md:mt-1 font-medium truncate">
                                    {isNotesTab
                                        ? `${stats.total} Highlights`
                                        : (isPersonalNotes
                                            ? `${stats.total} Notes`
                                            : `${stats.total} Items • ${stats.reading} Reading`
                                        )
                                    }
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="flex gap-2">
                        <button
                            onClick={() => {
                                if (isPersonalNotes && onAddPersonalNote) {
                                    const category: PersonalNoteCategory = noteCategoryFilter === 'ALL' ? 'DAILY' : noteCategoryFilter;
                                    const folderId = noteFolderFilter === 'ALL' || noteFolderFilter === '__ROOT__'
                                        ? undefined
                                        : noteFolderFilter;
                                    onAddPersonalNote({ category, folderId, folderPath: folderId ? folderById.get(folderId)?.name : undefined });
                                    return;
                                }
                                onAddBook();
                            }}
                            className="bg-[#262D40] text-white px-3 py-1.5 md:px-5 md:py-2.5 rounded-lg hover:bg-[#1d2333] transition-all flex items-center gap-1.5 shadow-md shadow-[#262D40]/20 dark:shadow-none font-medium shrink-0 active:scale-95"
                        >
                            <Plus size={16} className="md:w-5 md:h-5" />
                            <span className="text-xs md:text-base">
                                Add {activeTab === 'ARTICLE' ? 'Article' : (activeTab === 'WEBSITE' ? 'Web' : (activeTab === 'PERSONAL_NOTE' ? 'Note' : 'Book'))}
                            </span>
                        </button>
                    </div>
                </div>
            )}

            {/* Mobile Menu Trigger for Dashboard (Only button, no text) */}
            {isStats && (
                <div className="lg:hidden mb-4">
                    <button
                        onClick={onMobileMenuClick}
                        className="p-1.5 md:p-2 -ml-1 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 rounded-lg transition-colors shrink-0"
                    >
                        <Menu size={20} className="md:w-6 md:h-6" />
                    </button>
                </div>
            )}

            {/* Compact Filters for Mobile (Hide in Stats view) */}
            {!isStats && (
                <div className="bg-white dark:bg-slate-900 p-2 md:p-4 rounded-xl shadow-sm border border-[#E6EAF2] dark:border-slate-800 mb-4 md:mb-8 flex flex-col md:flex-row gap-2 md:gap-4">
                    <div className="flex-1 relative">
                        <Search className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-4 h-4 md:w-5 md:h-5" />
                        <input
                            type="text"
                            placeholder={getSearchPlaceholder()}
                            value={localInput}
                            onChange={(e) => setLocalInput(e.target.value)}
                            className="w-full pl-8 md:pl-10 pr-4 py-1.5 md:py-2 border border-[#E6EAF2] dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-[#CC561E] focus:border-transparent outline-none transition-all text-xs md:text-base bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500"
                        />
                        {/* Loading Spinner inside input */}
                        {isTyping && (
                            <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                <Loader2 size={16} className="animate-spin text-[#CC561E]" />
                            </div>
                        )}
                    </div>

                    {/* Favorites Toggle for Notes Views */}
                    {(isNotesTab || isPersonalNotes) && (
                        <button
                            onClick={() => onStatusFilterChange(statusFilter === 'FAVORITES' ? 'ALL' : 'FAVORITES')}
                            className={`p-2 rounded-lg border transition-all flex items-center justify-center shrink-0 ${statusFilter === 'FAVORITES'
                                ? 'bg-orange-100 dark:bg-orange-900/30 border-orange-200 dark:border-orange-800 text-orange-600 dark:text-orange-400'
                                : 'bg-white dark:bg-slate-800 border-[#E6EAF2] dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-700'
                                }`}
                            title={statusFilter === 'FAVORITES' ? "Show All" : "Show Favorites Only"}
                        >
                            <Star size={20} className="md:w-5 md:h-5" fill={statusFilter === 'FAVORITES' ? "currentColor" : "none"} />
                        </button>
                    )}

                    {!isNotesTab && !isPersonalNotes && (
                        <div className="grid grid-cols-2 md:flex gap-2 items-center">
                            {/* Filter Dropdown */}
                            <div className="relative min-w-[100px] md:min-w-[160px]">
                                <Filter className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
                                <select
                                    value={statusFilter}
                                    onChange={(e) => {
                                        onStatusFilterChange(e.target.value);
                                        onPageChange(1);
                                    }}
                                    className="w-full pl-7 md:pl-9 pr-6 md:pr-8 py-1.5 md:py-2 border border-[#E6EAF2] dark:border-slate-700 rounded-lg appearance-none bg-white dark:bg-slate-800 focus:ring-2 focus:ring-[#CC561E] text-xs md:text-sm font-medium text-slate-700 dark:text-slate-200 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600"
                                >
                                    <option value="ALL">All</option>
                                    <option value="FAVORITES">Favorites</option>
                                    <option value="HIGHLIGHTS">Highlight</option>
                                    <optgroup label="Status">
                                        <option value="To Read">To Read</option>
                                        <option value="Reading">Reading</option>
                                        <option value="Finished">Finished</option>
                                    </optgroup>
                                    {activeTab === 'BOOK' && (
                                        <optgroup label="Inventory">
                                            <option value="On Shelf">On Shelf</option>
                                            <option value="Lent Out">Lent Out</option>
                                            <option value="Lost">Lost</option>
                                        </optgroup>
                                    )}
                                </select>
                            </div>

                            {/* Sort Dropdown */}
                            <div className="relative min-w-[100px] md:min-w-[160px]">
                                <ArrowUpDown className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
                                <select
                                    value={sortOption}
                                    onChange={(e) => {
                                        onSortOptionChange(e.target.value);
                                        onPageChange(1);
                                    }}
                                    className="w-full pl-7 md:pl-9 pr-6 md:pr-8 py-1.5 md:py-2 border border-[#E6EAF2] dark:border-slate-700 rounded-lg appearance-none bg-white dark:bg-slate-800 focus:ring-2 focus:ring-[#CC561E] text-xs md:text-sm font-medium text-slate-700 dark:text-slate-200 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600"
                                >
                                    <option value="date_desc">Newest</option>
                                    <option value="date_asc">Oldest</option>
                                    <option value="title_asc">A-Z</option>
                                </select>
                            </div>

                            {activeTab === 'BOOK' && (
                                <div className="relative min-w-[140px] md:min-w-[180px]">
                                    <Hash className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
                                    <select
                                        value={categoryFilter || ''}
                                        onChange={(e) => onCategoryFilterChange?.(e.target.value || null)}
                                        className="w-full pl-7 md:pl-9 pr-6 md:pr-8 py-1.5 md:py-2 border border-[#E6EAF2] dark:border-slate-700 rounded-lg appearance-none bg-white dark:bg-slate-800 focus:ring-2 focus:ring-[#CC561E] text-xs md:text-sm font-medium text-slate-700 dark:text-slate-200 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600"
                                    >
                                        <option value="">All categories</option>
                                        {CATEGORIES.map(cat => (
                                            <option key={cat} value={cat}>{cat}</option>
                                        ))}
                                    </select>
                                </div>
                            )}

                            {activeTab === 'ARTICLE' && (
                                <input
                                    type="text"
                                    placeholder="Journal..."
                                    value={publisherFilter}
                                    onChange={(e) => {
                                        onPublisherFilterChange(e.target.value);
                                        onPageChange(1);
                                    }}
                                    className="hidden md:block px-4 py-2 border border-[#E6EAF2] dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-[#CC561E] text-sm min-w-[140px] bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500"
                                />
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Active Category Filter Pill */}
            {activeTab === 'BOOK' && !isStats && categoryFilter && (
                <div className="flex items-center gap-2 mb-4 md:mb-6">
                    <span className="text-xs md:text-sm text-slate-500">Category:</span>
                    <button
                        className="flex items-center gap-2 px-3 py-1 bg-[rgba(204,86,30,0.1)] text-[#CC561E] rounded-full text-xs md:text-sm border border-[#CC561E]/20 shadow-sm"
                        onClick={() => onCategoryFilterChange?.(null)}
                    >
                        <span className="font-semibold">{categoryFilter}</span>
                        <X size={14} />
                    </button>
                </div>
            )}

            {/* Content Views */}
            {renderContent()}

            {isPersonalNotes && undoMove && (
                <div className="fixed bottom-5 right-5 z-50 bg-[#262D40] text-white px-4 py-3 rounded-xl shadow-xl border border-white/10 flex items-center gap-3">
                    <span className="text-sm">Note moved.</span>
                    <button
                        onClick={() => {
                            window.clearTimeout(undoMove.timeoutId);
                            const target = undoMove;
                            setUndoMove(null);
                            performMove(target.noteId, target.category, target.folderId, false);
                        }}
                        className="text-sm font-semibold text-[#FFB58D] hover:text-white"
                    >
                        Undo
                    </button>
                </div>
            )}
        </div>
    );
});
