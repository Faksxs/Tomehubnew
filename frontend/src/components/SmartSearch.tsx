
import React, { useState } from 'react';
import { Search, Loader2, BookOpen, AlertCircle, Sparkles, Wand2, Type } from 'lucide-react';

interface SmartSearchProps {
    userId: string;
}

interface SearchResult {
    title: string;
    page_number: number;
    content_chunk: string;
    summary?: string;
    tags?: string;
    personal_comment?: string;
    source_type: string;
    score: number;
    match_type: string;
}

export default function SmartSearch({ userId }: SmartSearchProps) {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SearchResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searched, setSearched] = useState(false);

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

        const words = query.toLowerCase().split(/\s+/).filter(w => w.length >= 2);
        if (words.length === 0) return text;

        try {
            // Create a fuzzy regex pattern for each word
            const patterns = words.map(word => {
                return word.split('').map(char => turkishCharMap[char] || char).join('');
            });

            const regex = new RegExp(`(${patterns.join('|')})`, 'gi');
            const parts = text.split(regex);

            return parts.map((part, index) =>
                regex.test(part) ? (
                    <mark key={index} className="bg-[#fff3bf] text-gray-900 px-0.5 rounded font-medium shadow-sm transition-colors duration-200">
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

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!query.trim()) return;

        setLoading(true);
        setError(null);
        setResults([]);
        setSearched(true);

        try {
            const response = await fetch('https://141.144.205.97.nip.io/api/smart-search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: query, firebase_uid: userId }),
            });

            if (!response.ok) throw new Error('Search failed');
            const data = await response.json();
            setResults(data.results || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'An error occurred');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full space-y-8 p-6 max-w-5xl mx-auto w-full animate-in fade-in duration-500">
            {/* Premium Header */}
            <div className="text-center space-y-3 pt-6">
                <div className="inline-flex items-center justify-center p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded-2xl mb-2">
                    <Wand2 className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
                </div>
                <h2 className="text-4xl font-extrabold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent tracking-tight">
                    Smart Search
                </h2>
                <p className="text-gray-500 dark:text-gray-400 text-lg max-w-2xl mx-auto font-medium">
                    Layer 2: AI-Enhanced retrieval that understands context, fixes typos, and expands your query.
                </p>
            </div>

            {/* Search Bar Container */}
            <div className="bg-white dark:bg-gray-800 rounded-3xl shadow-xl shadow-indigo-100/50 dark:shadow-none border border-gray-100 dark:border-gray-700 overflow-hidden transform transition-all hover:scale-[1.01] duration-300">
                <div className="p-3">
                    <form onSubmit={handleSearch} className="flex items-center gap-3">
                        <div className="relative flex-1 group">
                            <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-gray-400 w-6 h-6 group-focus-within:text-indigo-500 transition-colors" />
                            <input
                                type="text"
                                placeholder="Search your knowledge base..."
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                className="w-full pl-16 pr-6 py-5 text-xl bg-transparent border-none outline-none text-gray-900 dark:text-gray-100 placeholder:text-gray-400 font-medium"
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={loading}
                            className="bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white px-10 py-5 rounded-2xl font-bold text-lg transition-all flex items-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed m-1"
                        >
                            {loading ? <Loader2 className="w-6 h-6 animate-spin" /> : <span>Search</span>}
                        </button>
                    </form>
                </div>
                <div className="bg-gray-50 dark:bg-gray-900/40 px-8 py-4 border-t border-gray-100 dark:border-gray-700 flex flex-wrap gap-6 text-sm text-gray-500 font-medium">
                    <span className="flex items-center gap-2 bg-white dark:bg-gray-800 px-3 py-1 rounded-full border border-gray-100 dark:border-gray-700 shadow-sm"><Sparkles className="w-4 h-4 text-amber-500" /> AI Query Expansion</span>
                    <span className="flex items-center gap-2 bg-white dark:bg-gray-800 px-3 py-1 rounded-full border border-gray-100 dark:border-gray-700 shadow-sm"><Type className="w-4 h-4 text-blue-500" /> Typo Correction</span>
                    <span className="flex items-center gap-2 bg-white dark:bg-gray-800 px-3 py-1 rounded-full border border-gray-100 dark:border-gray-700 shadow-sm"><BookOpen className="w-4 h-4 text-emerald-500" /> Hybrid Retrieval</span>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-5 rounded-2xl flex items-center gap-4 border border-red-100 dark:border-red-900/50 shadow-sm">
                    <AlertCircle className="w-6 h-6 shrink-0" />
                    <p className="font-medium">{error}</p>
                </div>
            )}

            <div className="space-y-6 pb-12">
                {results.length > 0 ? (
                    <>
                        <div className="flex items-center justify-between px-2">
                            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Found {results.length} relevant items</span>
                        </div>
                        <div className="grid gap-5">
                            {results.map((result, index) => (
                                <div key={index} className="group bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm hover:shadow-xl hover:-translate-y-1 border border-gray-100 dark:border-gray-700 transition-all duration-300">
                                    <div className="flex justify-between items-start mb-4">
                                        <h3 className="font-bold text-xl text-gray-900 dark:text-gray-100 flex items-center gap-3 group-hover:text-indigo-600 transition-colors">
                                            <BookOpen className="w-5 h-5 text-indigo-500" />
                                            {highlightMatches(result.title, query)}
                                        </h3>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {result.match_type === 'content_exact' && (
                                                <span className="px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 ring-1 ring-emerald-500/20">
                                                    Match
                                                </span>
                                            )}
                                            {result.match_type === 'semantic' && (
                                                <span className="px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-blue-100 text-blue-700 dark:bg-blue-900/30 ring-1 ring-blue-500/20">
                                                    Semantic
                                                </span>
                                            )}
                                            <span className="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs px-3 py-1 rounded-full font-mono font-medium">
                                                p.{result.page_number}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Main Highlight/Text - Cleanest view */}
                                    <div className="pl-5 border-l-4 border-gray-100 dark:border-gray-700 group-hover:border-indigo-500 transition-colors">
                                        <p className="text-gray-700 dark:text-gray-200 leading-relaxed text-base whitespace-pre-wrap font-serif">
                                            {highlightMatches(result.content_chunk, query)}
                                        </p>
                                    </div>

                                    {/* Secondary Metadata: Summary & Tags */}
                                    {(result.summary || result.tags) && (
                                        <div className="mt-4 pt-3 border-t border-gray-50 dark:border-gray-800/50 space-y-2">
                                            {result.summary && (
                                                <div className="text-sm">
                                                    <span className="font-semibold text-gray-400 dark:text-gray-500">Summary:</span>{' '}
                                                    <span className="text-gray-600 dark:text-gray-400">{highlightMatches(result.summary, query)}</span>
                                                </div>
                                            )}
                                            {result.tags && (
                                                <div className="text-xs">
                                                    <span className="font-semibold text-gray-400 dark:text-gray-500">Tags:</span>{' '}
                                                    <span className="text-gray-500 dark:text-gray-600 italic">{highlightMatches(result.tags, query)}</span>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Personal Comment - Fixed Position at Bottom */}
                                    {result.personal_comment && (
                                        <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700 bg-indigo-50/10 dark:bg-indigo-900/10 -mx-6 px-6 py-4 rounded-b-2xl">
                                            <div className="flex flex-col gap-2">
                                                <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-500 dark:text-indigo-400">
                                                    Personal comment:
                                                </span>
                                                <p className="text-sm text-gray-800 dark:text-gray-200 italic border-l-2 border-indigo-200 dark:border-indigo-800 pl-3">
                                                    {highlightMatches(result.personal_comment, query)}
                                                </p>
                                            </div>
                                        </div>
                                    )}

                                    <div className="mt-4 pt-2 flex justify-end">
                                        <span className="text-[10px] text-gray-300 dark:text-gray-600 font-bold uppercase tracking-widest">
                                            {result.source_type || 'General'}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </>
                ) : searched && !loading && !error ? (
                    <div className="text-center py-24 opacity-60">
                        <div className="bg-gray-50 dark:bg-gray-800 w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6">
                            <Search className="w-10 h-10 text-gray-300 dark:text-gray-600" />
                        </div>
                        <p className="text-2xl font-bold text-gray-400">No results found</p>
                    </div>
                ) : null}
            </div>
        </div>
    );
}
