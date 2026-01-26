import React, { useMemo, useState, useEffect } from 'react';
import { LibraryItem, ReadingStatus, ResourceType, PhysicalStatus } from '../types';
import { Search, Plus, Book as BookIcon, Filter, FileText, Globe, ExternalLink, StickyNote, Quote, ArrowRight, PenTool, BarChart2, AlertTriangle, Library, ArrowUpDown, Calendar, Hash, Menu, Trash2, ChevronDown, ChevronLeft, ChevronRight, Loader2, Star, CheckCircle, Zap } from 'lucide-react';
// import { StatisticsView } from './StatisticsView'; // Lazy loaded below
const StatisticsView = React.lazy(() => import('./StatisticsView').then(module => ({ default: module.StatisticsView })));

interface BookListProps {
    books: LibraryItem[];
    onAddBook: () => void;
    onSelectBook: (book: LibraryItem) => void;
    onSelectBookWithTab?: (book: LibraryItem, tab: 'info' | 'highlights', highlightId?: string) => void; // Optional: select book with specific tab and highlight
    activeTab: ResourceType | 'NOTES' | 'DASHBOARD';
    onMobileMenuClick: () => void;
    userId: string;

    onDeleteBook: (id: string) => void;
    onDeleteMultiple?: (ids: string[]) => void;
    onToggleFavorite: (id: string) => void; // Toggle favorite status
    onToggleHighlightFavorite?: (bookId: string, highlightId: string) => void; // Toggle highlight favorite status
}

export const BookList: React.FC<BookListProps> = React.memo(({ books, onAddBook, onSelectBook, onSelectBookWithTab, activeTab, onMobileMenuClick, onDeleteBook, onDeleteMultiple, onToggleFavorite, onToggleHighlightFavorite, userId }) => {
    // UI State
    const [inputValue, setInputValue] = useState(''); // Immediate input for UI
    const [debouncedSearch, setDebouncedSearch] = useState(''); // Delayed search for logic
    const [isTyping, setIsTyping] = useState(false); // Visual feedback

    const [statusFilter, setStatusFilter] = useState<ReadingStatus | PhysicalStatus | 'ALL' | 'HIGHLIGHTS' | 'FAVORITES'>('ALL');
    const [sortOption, setSortOption] = useState<'date_desc' | 'date_asc' | 'title_asc'>('date_desc');
    const [publisherFilter, setPublisherFilter] = useState('');

    // Pagination State
    const [currentPage, setCurrentPage] = useState(1);

    const statusColors = {
        'To Read': 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200',
        'Reading': 'bg-indigo-100 text-indigo-800 border border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-800',
        'Finished': 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
    };

    const isStats = activeTab === 'DASHBOARD';
    const isNotesTab = activeTab === 'NOTES';
    const isPersonalNotes = activeTab === 'PERSONAL_NOTE';

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
    useEffect(() => {
        if (inputValue !== debouncedSearch) {
            setIsTyping(true);
            const timer = setTimeout(() => {
                setDebouncedSearch(inputValue);
                setCurrentPage(1); // Reset pagination on new search
                setIsTyping(false);
            }, 300);

            return () => clearTimeout(timer);
        }
    }, [inputValue, debouncedSearch]);

    // Reset pagination when filters or tab change
    useEffect(() => {
        setCurrentPage(1);
    }, [activeTab, statusFilter, publisherFilter, sortOption]);

    // Reset filters when tab changes
    useEffect(() => {
        setStatusFilter('ALL');
        setPublisherFilter('');
        setDebouncedSearch('');
        setInputValue('');
        setIsTyping(false);
    }, [activeTab]);

    // --- FILTER & ENRICH LOGIC ---
    const filteredBooks = useMemo(() => {
        if (isNotesTab || isStats) return [];

        const term = debouncedSearch.toLowerCase().trim();

        const result = books.filter(book => {
            if (book.type !== activeTab) return false;
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
            if (publisherFilter) {
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

            const notesMatch = book.generalNotes && book.generalNotes.toLowerCase().includes(term);
            if (notesMatch) return true;

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

    }, [books, debouncedSearch, statusFilter, publisherFilter, sortOption, activeTab, isNotesTab, isStats]);

    // --- AGGREGATE HIGHLIGHTS ---
    const filteredHighlights = useMemo(() => {
        if (!isNotesTab) return [];

        const term = debouncedSearch.toLowerCase();

        return books
            .flatMap(book => book.highlights.map(h => ({ ...h, source: book })))
            .filter(item => {
                // 1. Status Filter
                if (statusFilter === 'FAVORITES') {
                    if (!item.isFavorite) return false;
                }

                if (!term) return true;
                return item.text.toLowerCase().includes(term) ||
                    (item.note && item.note.toLowerCase().includes(term)) ||
                    item.source.title.toLowerCase().includes(term) ||
                    item.source.author.toLowerCase().includes(term) ||
                    (item.tags && item.tags.some(t => t.toLowerCase().includes(term)));
            })
            .sort((a, b) => b.createdAt - a.createdAt);
    }, [books, isNotesTab, debouncedSearch, statusFilter]);

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

    // --- RENDER LOGIC: PAGINATION ---
    const totalItems = isNotesTab ? filteredHighlights.length : filteredBooks.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage);

    const displayedBooks = useMemo(() => {
        const start = (currentPage - 1) * itemsPerPage;
        return filteredBooks.slice(start, start + itemsPerPage);
    }, [filteredBooks, currentPage, itemsPerPage]);

    const displayedHighlights = useMemo(() => {
        const start = (currentPage - 1) * itemsPerPage;
        return filteredHighlights.slice(start, start + itemsPerPage);
    }, [filteredHighlights, currentPage, itemsPerPage]);



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
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-indigo-600 dark:hover:text-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                                    onClick={() => setCurrentPage(page as number)}
                                    className={`w-8 h-8 md:w-10 md:h-10 rounded-lg text-sm font-medium transition-colors ${currentPage === page
                                        ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200 dark:shadow-none'
                                        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-indigo-600 dark:hover:text-indigo-400'
                                        }`}
                                >
                                    {page}
                                </button>
                            )}
                        </React.Fragment>
                    ))}
                </div>

                <button
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-indigo-600 dark:hover:text-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                        <Loader2 size={32} className="animate-spin text-indigo-500" />
                    </div>
                }>
                    <StatisticsView items={books} />
                </React.Suspense>
            );
        }

        // Loading State for Search (Debounce visual)
        if (isTyping) {
            return (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400 animate-in fade-in duration-200">
                    <Loader2 size={32} className="animate-spin text-indigo-500 mb-4" />
                    <p>Searching library...</p>
                </div>
            );
        }

        if (isNotesTab) {
            if (displayedHighlights.length === 0) {
                return (
                    <div className="text-center py-12 md:py-20 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                        <div className="bg-slate-50 dark:bg-slate-800 w-12 h-12 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4">
                            <StickyNote size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />
                        </div>
                        <h3 className="text-base md:text-lg font-medium text-slate-900 dark:text-white">No highlights found</h3>
                        <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm max-w-xs mx-auto mt-2">
                            {debouncedSearch ? "Try a different search term." : "Highlights added to books appear here."}
                        </p>
                    </div>
                );
            }

            return (
                <div className="pb-20">
                    <div className="columns-2 lg:columns-3 gap-3 md:gap-6 space-y-3 md:space-y-6">
                        {displayedHighlights.map((highlight, idx) => {
                            const isNote = highlight.type === 'note';
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
                                        ? 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-500'
                                        : 'bg-yellow-50 dark:bg-yellow-900/10 border-yellow-100 dark:border-yellow-900/30 hover:border-yellow-300 dark:hover:border-yellow-700'
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
                                            ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-500 dark:text-amber-400 opacity-100'
                                            : 'bg-white/80 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500 hover:text-amber-500 dark:hover:text-amber-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                            }`}
                                        title={highlight.isFavorite ? "Remove from Favorites" : "Add to Favorites"}
                                    >
                                        <Star size={14} fill={highlight.isFavorite ? "currentColor" : "none"} />
                                    </button>
                                    <div className="mb-2 md:mb-3">
                                        {isNote ? (
                                            <StickyNote className="text-indigo-400 fill-indigo-50 w-4 h-4 md:w-6 md:h-6" />
                                        ) : (
                                            <Quote className="text-yellow-400 fill-yellow-200 w-4 h-4 md:w-6 md:h-6" />
                                        )}
                                    </div>
                                    <p className={`text-[10px] md:text-base leading-relaxed mb-2 md:mb-4 whitespace-pre-wrap line-clamp-[8] md:line-clamp-none font-lora ${isNote ? 'text-slate-700 dark:text-slate-300' : 'text-slate-900 dark:text-slate-200'}`}>
                                        {highlight.text}
                                    </p>

                                    {highlight.tags && highlight.tags.length > 0 && (
                                        <div className="flex flex-wrap gap-1 mb-2 md:mb-3">
                                            {highlight.tags.map((tag, i) => (
                                                <span key={i} className="px-1 md:px-1.5 py-0.5 bg-white/60 dark:bg-slate-700/50 border border-black/5 dark:border-white/10 rounded text-[8px] md:text-[10px] text-slate-500 dark:text-slate-400 flex items-center gap-0.5">
                                                    <Hash size={8} /> {tag}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    <div className={`pt-2 md:pt-4 mt-auto flex items-center justify-between border-t ${isNote ? 'border-slate-100' : 'border-yellow-200/50'}`}>
                                        <div className="flex-1 min-w-0">
                                            <h4 className="text-[10px] md:text-sm font-bold text-slate-900 dark:text-white truncate">{highlight.source.title}</h4>
                                            <div className="flex items-center gap-1 md:gap-2 text-[9px] md:text-xs text-slate-500 dark:text-slate-400">
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
        if (displayedBooks.length === 0) {
            return (
                <div className="text-center py-12 md:py-20 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                    <div className="bg-slate-50 dark:bg-slate-800 w-12 h-12 md:w-16 md:h-16 rounded-full flex items-center justify-center mx-auto mb-3 md:mb-4">
                        {activeTab === 'BOOK' ? <BookIcon size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" /> :
                            activeTab === 'ARTICLE' ? <FileText size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" /> :
                                <Globe size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />}
                    </div>
                    <h3 className="text-base md:text-lg font-medium text-slate-900 dark:text-white">No {getTabLabel(activeTab).toLowerCase()} found</h3>
                    <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm max-w-xs mx-auto mt-2">
                        {debouncedSearch ? "Try a different search term." : "Adjust filters or add a new item."}
                    </p>
                </div>
            );
        }

        return (
            <div className="pb-20">
                {isPersonalNotes ? (
                    // Personal Notes List
                    <div className="columns-2 lg:columns-3 gap-3 md:gap-6 space-y-3 md:space-y-6">
                        {displayedBooks.map(note => (
                            <div
                                key={note.id}
                                onClick={() => onSelectBook(note)}
                                className="break-inside-avoid bg-white dark:bg-slate-900 p-3 md:p-6 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-indigo-300 dark:hover:border-indigo-500 hover:shadow-lg hover:-translate-y-1 transition-all cursor-pointer flex flex-col h-auto group relative"
                            >
                                {/* Action Buttons */}
                                <div className="absolute top-2 right-2 flex gap-1 z-10">
                                    <button
                                        onClick={(e) => { e.stopPropagation(); onToggleFavorite(note.id); }}
                                        className={`p-1.5 rounded-full transition-all shadow-sm ${note.isFavorite
                                            ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-500 dark:text-amber-400 opacity-100'
                                            : 'bg-white/80 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500 hover:text-amber-500 dark:hover:text-amber-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                            }`}
                                        title={note.isFavorite ? "Remove from Favorites" : "Add to Favorites"}
                                    >
                                        <Star size={14} fill={note.isFavorite ? "currentColor" : "none"} />
                                    </button>
                                    <button
                                        onClick={(e) => { e.stopPropagation(); onDeleteBook(note.id); }}
                                        className="p-1.5 bg-white/80 dark:bg-slate-800/80 hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-600 dark:hover:text-red-400 rounded-full transition-all opacity-0 group-hover:opacity-100 focus:opacity-100 shadow-sm"
                                        title="Delete Note"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>

                                <h3 className="font-bold text-sm md:text-lg text-slate-900 dark:text-white mb-1 md:mb-3 leading-tight pr-6">{note.title}</h3>

                                <div className="text-slate-600 dark:text-slate-300 text-xs md:text-base mb-2 md:mb-4 whitespace-pre-wrap leading-relaxed max-h-[150px] md:max-h-[300px] overflow-hidden relative font-lora">
                                    {note.generalNotes || <span className="italic text-slate-400 dark:text-slate-500">Empty</span>}
                                    {note.generalNotes && note.generalNotes.length > 100 && (
                                        <div className="absolute bottom-0 inset-x-0 h-8 md:h-12 bg-gradient-to-t from-white dark:from-slate-900 to-transparent" />
                                    )}
                                </div>

                                <div className="mt-auto pt-2 md:pt-3 flex flex-wrap gap-1 md:gap-2 border-t border-slate-50 dark:border-slate-800">
                                    {note.tags.slice(0, 2).map((tag, idx) => (
                                        <span key={idx} className="px-1.5 py-0.5 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 text-[9px] md:text-xs rounded">#{tag}</span>
                                    ))}
                                    {note.tags.length > 2 && (
                                        <span className="text-[9px] md:text-xs text-slate-400">+{note.tags.length - 2}</span>
                                    )}
                                    <span className="ml-auto text-[9px] md:text-xs text-slate-300 flex items-center gap-1">
                                        <Calendar size={8} />
                                        {new Date(note.addedAt).toLocaleDateString()}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    // Standard Grid (Books/Articles/Websites)
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-6">
                        {displayedBooks.map((book) => (
                            <div
                                key={book.id}
                                onClick={() => onSelectBook(book)}
                                className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden hover:shadow-lg hover:-translate-y-1 transition-all cursor-pointer group flex flex-col h-full relative"
                            >
                                {/* Compact Cover / Icon Container */}
                                <div className="h-24 md:h-40 bg-slate-100 dark:bg-slate-800 relative flex items-end justify-between overflow-hidden group-hover:opacity-95 transition-opacity">

                                    {/* Action Buttons Overlay */}
                                    <div className="absolute top-2 right-2 z-40 flex gap-1">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onToggleFavorite(book.id);
                                            }}
                                            className={`p-1.5 rounded-full shadow-sm backdrop-blur-sm border border-slate-100 dark:border-slate-800 transition-all ${book.isFavorite
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
                                            className="p-1.5 bg-white/90 dark:bg-slate-900/90 hover:bg-red-50 dark:hover:bg-red-900/30 text-slate-400 dark:text-slate-500 hover:text-red-600 dark:hover:text-red-400 rounded-full shadow-sm backdrop-blur-sm border border-slate-100 dark:border-slate-800 transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                                            title="Delete Item"
                                        >
                                            <Trash2 size={14} className="md:w-4 md:h-4" />
                                        </button>

                                        {/* Ingested Status Badge */}
                                        {book.isIngested && (
                                            <div
                                                className="p-1.5 bg-indigo-500/90 dark:bg-indigo-600/90 text-white rounded-full shadow-sm backdrop-blur-sm border border-indigo-400/50 dark:border-indigo-500/50 transition-all z-40"
                                                title="Added to AI Library"
                                            >
                                                <CheckCircle size={14} className="md:w-4 md:h-4" fill="currentColor" />
                                            </div>
                                        )}
                                    </div>

                                    {/* Fallback Icon */}
                                    <div className="absolute inset-0 flex items-center justify-center text-slate-300 dark:text-slate-600 bg-slate-100 dark:bg-slate-800">
                                        {book.type === 'BOOK' ? <BookIcon className="w-8 h-8 md:w-16 md:h-16" strokeWidth={1} /> :
                                            book.type === 'ARTICLE' ? <FileText className="w-8 h-8 md:w-16 md:h-16" strokeWidth={1} /> :
                                                <Globe className="w-8 h-8 md:w-16 md:h-16" strokeWidth={1} />}
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
                                                <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center shadow-sm border border-white/20" title="Lent Out">
                                                    <AlertTriangle size={10} className="md:w-3 md:h-3" />
                                                </div>
                                            )}
                                            {book.type === 'BOOK' && book.status === 'Lost' && (
                                                <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-red-100 text-red-600 flex items-center justify-center shadow-sm border border-white/20" title="Lost">
                                                    <AlertTriangle size={10} className="md:w-3 md:h-3" />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Card Body */}
                                <div className="p-3 md:p-5 flex-1 flex flex-col">
                                    <h3 className="font-bold text-sm md:text-lg text-slate-900 dark:text-white leading-tight mb-0.5 md:mb-1 line-clamp-2 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
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
                                            <span className="bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500 dark:text-slate-400 font-mono">
                                                {book.publicationYear}
                                            </span>
                                        )}
                                        {book.type === 'WEBSITE' && book.url && (
                                            <a href={book.url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:text-indigo-600" onClick={(e) => e.stopPropagation()}>
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

    return (
        <div className="max-w-7xl mx-auto p-3 md:p-8 pb-24 md:pb-20">
            {/* Compact Header for Mobile */}
            <div className="flex items-center justify-between mb-4 md:mb-8 gap-2">
                <div className="flex items-center gap-2 md:gap-4 overflow-hidden flex-1">
                    {/* Mobile Menu Trigger */}
                    <button
                        onClick={onMobileMenuClick}
                        className="lg:hidden p-1.5 md:p-2 -ml-1 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors shrink-0"
                    >
                        <Menu size={20} className="md:w-6 md:h-6" />
                    </button>

                    <div className="min-w-0 flex flex-col justify-center">
                        <h1 className="text-lg md:text-3xl font-bold text-slate-900 dark:text-white tracking-tight leading-none truncate">
                            {getTabLabel(activeTab)}
                        </h1>
                        {!isStats && (
                            <p className="text-slate-500 dark:text-slate-400 text-[10px] md:text-sm md:mt-1 font-medium truncate">
                                {isNotesTab
                                    ? `${stats.total} Highlights`
                                    : (isPersonalNotes
                                        ? `${stats.total} Notes`
                                        : `${stats.total} Items • ${stats.reading} Reading`
                                    )
                                }
                            </p>
                        )}
                        {isStats && (
                            <p className="text-slate-500 text-[10px] md:text-sm mt-0.5 font-medium truncate">Analytics</p>
                        )}
                    </div>
                </div>

                {!isStats && (
                    <div className="flex gap-2">
                        <button
                            onClick={onAddBook}
                            className="bg-indigo-600 dark:bg-indigo-500 text-white px-3 py-1.5 md:px-5 md:py-2.5 rounded-lg hover:bg-indigo-700 dark:hover:bg-indigo-600 transition-colors flex items-center gap-1.5 shadow-md shadow-indigo-200 dark:shadow-none font-medium shrink-0"
                        >
                            <Plus size={16} className="md:w-5 md:h-5" />
                            <span className="text-xs md:text-base">
                                Add {activeTab === 'ARTICLE' ? 'Article' : (activeTab === 'WEBSITE' ? 'Web' : (activeTab === 'PERSONAL_NOTE' ? 'Note' : 'Book'))}
                            </span>
                        </button>
                    </div>
                )}
            </div>

            {/* Compact Filters for Mobile (Hide in Stats view) */}
            {!isStats && (
                <div className="bg-white dark:bg-slate-900 p-2 md:p-4 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 mb-4 md:mb-8 flex flex-col md:flex-row gap-2 md:gap-4">
                    <div className="flex-1 relative">
                        <Search className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-4 h-4 md:w-5 md:h-5" />
                        <input
                            type="text"
                            placeholder={getSearchPlaceholder()}
                            value={inputValue}
                            onChange={(e) => setInputValue(e.target.value)}
                            className="w-full pl-8 md:pl-10 pr-4 py-1.5 md:py-2 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all text-xs md:text-base bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500"
                        />
                        {/* Loading Spinner inside input */}
                        {isTyping && (
                            <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                <Loader2 size={16} className="animate-spin text-indigo-400" />
                            </div>
                        )}
                    </div>

                    {/* Favorites Toggle for Notes Views */}
                    {(isNotesTab || isPersonalNotes) && (
                        <button
                            onClick={() => setStatusFilter(prev => prev === 'FAVORITES' ? 'ALL' : 'FAVORITES')}
                            className={`p-2 rounded-lg border transition-all flex items-center justify-center shrink-0 ${statusFilter === 'FAVORITES'
                                ? 'bg-amber-100 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800 text-amber-600 dark:text-amber-400'
                                : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700'
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
                                    onChange={(e) => setStatusFilter(e.target.value as ReadingStatus | PhysicalStatus | 'ALL' | 'HIGHLIGHTS' | 'FAVORITES')}
                                    className="w-full pl-7 md:pl-9 pr-6 md:pr-8 py-1.5 md:py-2 border border-slate-200 dark:border-slate-700 rounded-lg appearance-none bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500 text-xs md:text-sm font-medium text-slate-700 dark:text-slate-200 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600"
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
                                    onChange={(e) => setSortOption(e.target.value as 'date_desc' | 'date_asc' | 'title_asc')}
                                    className="w-full pl-7 md:pl-9 pr-6 md:pr-8 py-1.5 md:py-2 border border-slate-200 dark:border-slate-700 rounded-lg appearance-none bg-white dark:bg-slate-800 focus:ring-2 focus:ring-indigo-500 text-xs md:text-sm font-medium text-slate-700 dark:text-slate-200 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600"
                                >
                                    <option value="date_desc">Newest</option>
                                    <option value="date_asc">Oldest</option>
                                    <option value="title_asc">A-Z</option>
                                </select>
                            </div>

                            {activeTab !== 'WEBSITE' && (
                                <input
                                    type="text"
                                    placeholder={activeTab === 'ARTICLE' ? "Journal..." : "Publisher..."}
                                    value={publisherFilter}
                                    onChange={(e) => setPublisherFilter(e.target.value)}
                                    className="hidden md:block px-4 py-2 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-indigo-500 text-sm min-w-[140px] bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500"
                                />
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Content Views */}
            {renderContent()}
        </div>
    );
});