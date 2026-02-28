import React, { useState } from 'react';
import { Search, Loader2, BookOpen, AlertCircle, Sparkles, Type, ChevronLeft, LayoutPanelLeft, FileSearch } from 'lucide-react';
import { ConcordanceView } from './ConcordanceView';
import { LibraryItem } from '../types';
import { SmartSearchLogo } from './ui/FeatureLogos';

import { API_BASE_URL, fetchWithAuth, getFriendlyApiErrorMessage, parseApiErrorMessage } from '../services/apiClient';

interface SmartSearchProps {
    userId: string;
    onBack?: () => void;
    books?: LibraryItem[];
}

interface SearchResult {
    title: string;
    page_number: number;
    content_chunk: string;
    summary?: string;
    tags?: string;
    comment?: string;
    personal_comment?: string;
    source_type: string;
    score: number;
    match_type: string;
}

const HIGHLIGHT_STOP_WORDS = new Set([
    've', 'veya', 'ile', 'ama', 'fakat', 'ancak', 'lakin', 'ki',
    'de', 'da', 'gibi', 'icin', 'için', 'gore', 'göre', 'kadar',
    'hem', 'ya', 'yada', 'yahut', 'mi', 'mu', 'mı', 'mü'
]);

export default function SmartSearch({ userId, onBack, books = [] }: SmartSearchProps) {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SearchResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searched, setSearched] = useState(false);
    const [analyticsResult, setAnalyticsResult] = useState<any>(null);
    const [showConcordance, setShowConcordance] = useState(false);
    const [offset, setOffset] = useState(0);
    const [totalResults, setTotalResults] = useState(0);
    const limit = 20;

    // Helper function to highlight matches with Turkish fuzzy logic
    const highlightMatches = (text: string, query: string) => {
        if (!query || !text) return text;

        const turkishCharMap: { [key: string]: string } = {
            'i': '[iıİI]',
            'ı': '[iıİI]',
            's': '[sşSŞ]',
            'ş': '[sşSŞ]',
            'c': '[cçCÇ]',
            'ç': '[cçCÇ]',
            'g': '[gğGĞ]',
            'ğ': '[gğGĞ]',
            'o': '[oöOÖ]',
            'ö': '[oöOÖ]',
            'u': '[uüUÜ]',
            'ü': '[uüUÜ]'
        };

        const words = query
            .toLowerCase()
            .split(/\s+/)
            .map((w) => w.trim())
            .filter((w) => w.length >= 2 && !HIGHLIGHT_STOP_WORDS.has(w));
        if (words.length === 0) return text;

        try {
            const patterns = words.map(word => {
                return word.split('').map(char => turkishCharMap[char] || char).join('');
            });

            const regex = new RegExp(
                `((?<![\\p{L}\\p{N}])(?:${patterns.join('|')})[\\p{L}\\p{N}]*(?![\\p{L}\\p{N}]))`,
                'giu'
            );
            const parts = text.split(regex);

            return parts.map((part, index) =>
                index % 2 === 1 ? (
                    <mark key={index} className="bg-[rgba(204,86,30,0.12)] dark:bg-[rgba(204,86,30,0.25)] text-[#111827] dark:text-white px-0.5 rounded font-medium shadow-sm transition-colors duration-200">
                        {part}
                    </mark>
                ) : (
                    <span key={index}>{part}</span>
                )
            );
        } catch (e) {
            return text;
        }
    };

    const handleSearch = async (e?: React.FormEvent, newOffset: number = 0) => {
        if (e) e.preventDefault();
        if (!query.trim()) return;

        setLoading(true);
        setError(null);
        if (newOffset === 0) {
            setResults([]);
            setSearched(true);
        }
        setOffset(newOffset);

        try {
            // Point to local backend to see our changes (limit:1000, etc.)
            const apiUrl = `${API_BASE_URL}/api/smart-search`;
            console.log('[SmartSearch] Calling:', apiUrl, 'Offset:', newOffset);

            const response = await fetchWithAuth(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: query,
                    firebase_uid: userId,
                    limit: limit,
                    offset: newOffset
                }),
            });

            if (!response.ok) {
                throw new Error(await parseApiErrorMessage(response, 'Search failed'));
            }
            const data = await response.json();

            if (data.metadata?.status === 'analytic' && data.metadata?.analytics) {
                setAnalyticsResult({
                    ...data.metadata.analytics,
                    answer: data.answer
                });
                setResults([]);
                setTotalResults(0);
            } else {
                setResults(data.results || []);
                setTotalResults(data.total || (data.results?.length || 0));
                setAnalyticsResult(null);
            }
        } catch (err) {
            console.error('[SmartSearch] Error:', err);
            setError(getFriendlyApiErrorMessage(err));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={`max-w-[1100px] w-full mx-auto p-3 md:p-6 flex flex-col transition-all duration-1000 ease-in-out ${!searched ? 'min-h-[70vh]' : 'space-y-6 md:space-y-8'}`}>
            <div className="relative flex items-center justify-between w-full h-10 md:h-12 mb-2 md:mb-6">
                <div className="flex-shrink-0 z-10">
                    {onBack && (
                        <button
                            onClick={onBack}
                            className="group flex items-center gap-2 text-slate-500 dark:text-slate-400 hover:text-[#CC561E] transition-all duration-300"
                        >
                            <div className="p-1.5 rounded-lg bg-[#F3F5FA] dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                                <ChevronLeft size={16} />
                            </div>
                            <span className="text-xs font-bold uppercase tracking-wider hidden sm:inline">Back</span>
                        </button>
                    )}
                </div>

                {/* Centered Branding - Only visible when results are shown */}
                {searched && (
                    <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 md:gap-3 transition-all duration-500 origin-center animate-in fade-in zoom-in-95">
                        <div className="p-1.5 md:p-2 bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] rounded-2xl shrink-0 scale-75">
                            <SmartSearchLogo className="w-5 h-5 md:w-8 md:h-8" />
                        </div>
                        <h1 className="font-extrabold bg-gradient-to-r from-[#CC561E] to-[#e66a2e] bg-clip-text text-transparent tracking-tight text-xl md:text-2xl">
                            Search
                        </h1>
                    </div>
                )}
                <div className="w-20 hidden sm:block" /> {/* Spacer for balance */}
            </div>

            <div className={`flex-1 flex flex-col relative transition-all duration-700 ${!searched ? 'justify-center items-center' : 'pt-4 md:pt-6'}`}>
                <form onSubmit={handleSearch} className={`space-y-4 md:space-y-6 w-full transition-all duration-1000 ease-in-out ${!searched ? 'max-w-2xl text-center' : 'max-w-none'}`}>
                    {!searched && (
                        <div className="mb-6 md:mb-10 space-y-4 animate-slide-up">
                            <div className="flex items-center justify-center gap-3">
                                <div className="p-1.5 md:p-2 bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] rounded-2xl shrink-0">
                                    <SmartSearchLogo className="w-6 h-6 md:w-10 md:h-10" />
                                </div>
                                <h1 className="text-2xl md:text-5xl font-extrabold bg-gradient-to-r from-[#CC561E] to-[#e66a2e] bg-clip-text text-transparent tracking-tight">
                                    Search
                                </h1>
                            </div>

                            <div className="flex flex-wrap items-center justify-center gap-2 md:gap-4 mt-4 opacity-80">
                                <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] md:text-xs font-bold text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                                    <Sparkles className="w-3 h-3 text-[#CC561E]" /> AI Query Expansion
                                </span>
                                <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] md:text-xs font-bold text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                                    <Type className="w-3 h-3" /> Typo Correction
                                </span>
                                <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px] md:text-xs font-bold text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                                    <BookOpen className="w-3 h-3" /> Hybrid Retrieval
                                </span>
                            </div>
                        </div>
                    )}

                    <div className="relative group">
                        <Search className="absolute left-4 md:left-5 top-1/2 -translate-y-1/2 w-4 h-4 md:w-5 md:h-5 text-slate-400 group-focus-within:text-[#CC561E] transition-colors" />
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search your library intelligently..."
                            className="w-full pl-11 md:pl-14 pr-4 md:pr-6 py-3.5 md:py-5 rounded-2xl border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-800 text-base md:text-lg text-slate-900 dark:text-white shadow-sm focus:shadow-xl focus:shadow-[#CC561E]/5 focus:outline-none focus:ring-2 focus:ring-[#CC561E]/50 transition-all placeholder:text-slate-400"
                        />
                    </div>
                    <div className={`text-[11px] md:text-xs text-slate-500 dark:text-slate-400 ${!searched ? 'text-center' : 'text-left'}`}>
                        Tip: <span className="font-bold text-[#CC561E]">Enter</span> to search.
                    </div>
                </form>
            </div>

            {error && (
                <div className="bg-[#262D40]/5 dark:bg-[#262D40]/20 text-[#262D40] dark:text-[#262D40]/78 p-5 rounded-2xl flex items-center gap-4 border border-[#262D40]/8 dark:border-[#262D40]/50 shadow-sm">
                    <AlertCircle className="w-6 h-6 shrink-0" />
                    <p className="font-medium">{error}</p>
                </div>
            )}

            <div className="space-y-6 pb-12 mt-6">
                {results.length > 0 ? (
                    <>
                        <div className="flex items-center justify-between px-2">
                            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Found {totalResults} relevant items</span>
                        </div>
                        <div className="grid gap-5">
                            {results.map((result, index) => (
                                <div key={index} className="group bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm hover:shadow-xl hover:-translate-y-1 border border-[#E6EAF2] dark:border-gray-700 transition-all duration-300">
                                    <div className="flex justify-between items-start mb-4">
                                        <h3 className="font-bold text-xl text-gray-900 dark:text-gray-100 flex items-center gap-3 group-hover:text-[#CC561E] transition-colors">
                                            <BookOpen className="w-5 h-5 text-[#CC561E]" />
                                            {highlightMatches(result.title, query)}
                                        </h3>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {result.match_type === 'content_exact' && (
                                                <span className="px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#262D40] text-white ring-1 ring-white/10">
                                                    Match
                                                </span>
                                            )}
                                            {result.match_type === 'semantic' && (
                                                <span className="px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#262D40] text-white ring-1 ring-white/10">
                                                    Semantic
                                                </span>
                                            )}
                                            <span className="bg-[#262D40] text-white text-xs px-3 py-1 rounded-full font-mono font-medium ring-1 ring-white/10">
                                                p.{result.page_number}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="pl-5 border-l-4 border-[#262D40]/10 group-hover:border-[#CC561E]/30 transition-colors">
                                        <p className="text-gray-700 dark:text-gray-200 leading-relaxed text-base whitespace-pre-wrap font-serif">
                                            {highlightMatches(result.content_chunk, query)}
                                        </p>
                                    </div>
                                    {(result.comment || result.personal_comment) && (
                                        <div className="mt-4 pt-4 border-t border-[#E6EAF2] dark:border-gray-700 bg-[rgba(204,86,30,0.08)] dark:bg-[rgba(204,86,30,0.1)] -mx-6 px-6 py-4 rounded-b-2xl">
                                            <span className="text-[10px] font-bold uppercase tracking-widest text-[#CC561E] block mb-1">Comment:</span>
                                            <p className="text-sm text-gray-800 dark:text-gray-200 italic border-l-2 border-[#CC561E]/30 pl-3">
                                                {highlightMatches(result.comment || result.personal_comment || '', query)}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>

                        {totalResults > limit && (
                            <div className="flex items-center justify-between mt-10 pt-6 border-t border-[#E6EAF2] dark:border-gray-700">
                                <button
                                    onClick={() => handleSearch(undefined, Math.max(0, offset - limit))}
                                    disabled={loading || offset === 0}
                                    className="px-6 py-3 bg-white dark:bg-gray-800 border border-[#E6EAF2] dark:border-gray-700 rounded-xl font-bold text-gray-700 dark:text-gray-200 hover:bg-[#F3F5FA] dark:hover:bg-gray-700 transition-all disabled:opacity-50 flex items-center gap-2 shadow-sm"
                                >
                                    <ChevronLeft size={20} />
                                    Previous
                                </button>
                                <span className="text-sm font-bold text-gray-500 uppercase tracking-widest">
                                    Page {Math.floor(offset / limit) + 1} of {Math.ceil(totalResults / limit)}
                                </span>
                                <button
                                    onClick={() => handleSearch(undefined, offset + limit)}
                                    disabled={loading || offset + limit >= totalResults}
                                    className="px-6 py-3 bg-white dark:bg-gray-800 border border-[#E6EAF2] dark:border-gray-700 rounded-xl font-bold text-gray-700 dark:text-gray-200 hover:bg-[#F3F5FA] dark:hover:bg-gray-700 transition-all disabled:opacity-50 flex items-center gap-2 shadow-sm"
                                >
                                    Next
                                    <ChevronLeft size={20} className="rotate-180" />
                                </button>
                            </div>
                        )}
                    </>
                ) : searched && !loading && !error ? (
                    <div className="text-center py-24 opacity-60">
                        <div className="bg-[#F3F5FA] dark:bg-gray-800 w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6">
                            <Search className="w-10 h-10 text-gray-300 dark:text-gray-600" />
                        </div>
                        <p className="text-2xl font-bold text-gray-400">No results found</p>
                    </div>
                ) : null}
            </div>

            {analyticsResult && (
                <div className="bg-white dark:bg-gray-800 rounded-3xl p-8 shadow-xl border-t-4 border-[#CC561E] animate-in zoom-in duration-300 relative overflow-hidden">
                    <div className="absolute right-[-20px] top-[-20px] opacity-[0.03] dark:opacity-[0.05] pointer-events-none">
                        <FileSearch size={220} />
                    </div>
                    <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
                        <div className="space-y-4">
                            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[rgba(204,86,30,0.1)] text-[#CC561E] text-xs font-bold uppercase tracking-widest">
                                <Sparkles size={12} />
                                Deterministic Analytics
                            </div>
                            <h3 className="text-3xl font-extrabold text-slate-900 dark:text-white leading-tight">
                                {analyticsResult.answer}
                            </h3>
                        </div>
                        {analyticsResult.contexts && analyticsResult.contexts.length > 0 && (
                            <button
                                onClick={() => setShowConcordance(true)}
                                className="group flex items-center gap-3 bg-[#CC561E] hover:bg-[#b34b1a] text-white px-8 py-4 rounded-2xl font-bold shadow-lg shadow-[#CC561E]/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
                            >
                                <LayoutPanelLeft size={20} className="group-hover:rotate-12 transition-transform" />
                                See Contexts
                            </button>
                        )}
                    </div>
                </div>
            )}

            {showConcordance && analyticsResult && (
                <div className="fixed inset-0 z-[100] flex justify-end">
                    <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm animate-in fade-in duration-300" onClick={() => setShowConcordance(false)} />
                    <div className="relative w-full max-w-lg h-full overflow-hidden">
                        <ConcordanceView
                            bookId={analyticsResult.resolved_book_id || ''}
                            term={analyticsResult.term}
                            initialContexts={analyticsResult.contexts}
                            firebaseUid={userId}
                            onClose={() => setShowConcordance(false)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
