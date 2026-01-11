import React, { useState } from 'react';
import { Search, BookOpen, Loader2, AlertCircle, ExternalLink, User } from 'lucide-react';
import { searchLibrary, SearchResponse } from '../services/backendApiService';

interface RAGSearchProps {
    userId: string;
    userEmail?: string | null;
}

export const RAGSearch: React.FC<RAGSearchProps> = ({ userId, userEmail }) => {
    const [question, setQuestion] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [result, setResult] = useState<SearchResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!question.trim()) {
            setError('Please enter a question');
            return;
        }

        setIsSearching(true);
        setError(null);
        setResult(null);

        try {
            const response = await searchLibrary(question, userId);
            setResult(response);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Search failed');
        } finally {
            setIsSearching(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6 space-y-6">
            {/* Header */}
            <div className="text-center space-y-2">
                <div className="flex items-center justify-center gap-2">
                    <BookOpen className="w-8 h-8 text-indigo-600" />
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
                        Ask Your Library
                    </h1>
                </div>
                <p className="text-slate-600 dark:text-slate-400">
                    Search your personal library using AI-powered semantic search
                </p>
                {userEmail && (
                    <div className="flex items-center justify-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                        <User className="w-4 h-4" />
                        <span>Searching as: {userEmail}</span>
                    </div>
                )}
            </div>

            {/* Search Form */}
            <form onSubmit={handleSearch} className="space-y-4">
                <div className="relative">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <input
                        type="text"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder="Ask a question about your books..."
                        className="w-full pl-12 pr-4 py-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                        disabled={isSearching}
                    />
                </div>

                <button
                    type="submit"
                    disabled={isSearching || !question.trim()}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 dark:disabled:bg-slate-700 text-white font-medium py-3 px-6 rounded-xl transition-colors flex items-center justify-center gap-2"
                >
                    {isSearching ? (
                        <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            Searching...
                        </>
                    ) : (
                        <>
                            <Search className="w-5 h-5" />
                            Search
                        </>
                    )}
                </button>
            </form>

            {/* Error Message */}
            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                        <h3 className="font-medium text-red-900 dark:text-red-100">Search Failed</h3>
                        <p className="text-sm text-red-700 dark:text-red-300 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* Results */}
            {result && (
                <div className="space-y-6">
                    {/* Answer */}
                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
                        <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                            <BookOpen className="w-5 h-5 text-indigo-600" />
                            Answer
                        </h2>
                        <div className="prose prose-slate dark:prose-invert max-w-none">
                            <p className="text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
                                {result.answer}
                            </p>
                        </div>
                    </div>

                    {/* Sources */}
                    {result.sources && result.sources.length > 0 && (
                        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                                <ExternalLink className="w-5 h-5 text-indigo-600" />
                                Sources ({result.sources.length})
                            </h3>
                            <div className="space-y-2">
                                {result.sources.map((source, index) => (
                                    <div
                                        key={index}
                                        className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                                    >
                                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-sm font-medium">
                                            {index + 1}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="font-medium text-slate-900 dark:text-white truncate">
                                                {source.title}
                                            </p>
                                            <p className="text-sm text-slate-600 dark:text-slate-400">
                                                Page {source.page_number}
                                                {source.similarity_score !== undefined && (
                                                    <span className="ml-2 text-xs text-slate-500">
                                                        (Relevance: {(1 - source.similarity_score).toFixed(2)})
                                                    </span>
                                                )}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Example Questions */}
            {!result && !isSearching && (
                <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-6 space-y-3">
                    <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                        Example questions:
                    </h3>
                    <div className="space-y-2">
                        {[
                            "What is phenomenology?",
                            "What does Heidegger say about being-in-the-world?",
                            "Summarize the main ideas about Stoicism",
                        ].map((example, index) => (
                            <button
                                key={index}
                                onClick={() => setQuestion(example)}
                                className="block w-full text-left px-4 py-2 rounded-lg bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors"
                            >
                                {example}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
