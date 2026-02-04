import React, { useState } from 'react';
import { Search, BookOpen, Loader2, AlertCircle, ExternalLink, User, ThumbsUp, ThumbsDown, MessageCircle, ChevronLeft } from 'lucide-react';
import { searchLibrary, submitFeedback, SearchResponse } from '../services/backendApiService';
import { ExplorerChat } from './ExplorerChat';

interface RAGSearchProps {
    userId: string;
    userEmail?: string | null;
    onBack?: () => void;
}

export const RAGSearch: React.FC<RAGSearchProps> = ({ userId, userEmail, onBack }) => {
    const [question, setQuestion] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [result, setResult] = useState<SearchResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [feedbackStatus, setFeedbackStatus] = useState<'none' | 'liked' | 'disliked'>('none');
    const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
    const [mode, setMode] = useState<'STANDARD' | 'EXPLORER'>('STANDARD');
    const [lastQuestion, setLastQuestion] = useState('');

    // If Explorer mode is active, render the dedicated chat component
    if (mode === 'EXPLORER') {
        return (
            <div className="max-w-[1100px] w-full mx-auto p-6 animate-fade-in space-y-4">
                {/* Back to Home Button */}
                <div className="flex justify-start">
                    <button
                        onClick={onBack}
                        className="group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                    >
                        <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                            <ChevronLeft size={16} />
                        </div>
                        <span className="text-xs font-bold uppercase tracking-wider">Back to Home</span>
                    </button>
                </div>

                {/* Mode Toggle - stays visible */}
                <div className="flex justify-center mb-4">
                    <div className="bg-slate-100 dark:bg-slate-800 p-1 rounded-lg inline-flex items-center">
                        <button
                            type="button"
                            onClick={() => setMode('STANDARD')}
                            className="px-4 py-2 rounded-md text-sm font-medium transition-all text-slate-500 hover:text-slate-700 dark:text-slate-400"
                        >
                            Standard
                        </button>
                        <button
                            type="button"
                            className="px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 bg-white dark:bg-slate-700 text-[#CC561E] shadow-sm"
                        >
                            <MessageCircle className="w-4 h-4 text-[#CC561E]" /> Explorer
                        </button>
                    </div>
                </div>
                <ExplorerChat userId={userId} onBack={() => setMode('STANDARD')} />
            </div>
        );
    }

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!question.trim()) {
            setError('Please enter a question');
            return;
        }

        console.log('[RAGSearch] Searching with userId:', userId, 'Mode:', mode);

        if (!userId || userId.includes('@')) {
            console.error('[RAGSearch] INVALID UID detected (looks like email). Blocking search.');
            setError('Authentication is still loading. Please wait a moment and try again.');
            return;
        }

        setIsSearching(true);
        setError(null);
        setResult(null);
        setFeedbackStatus('none');

        try {
            // STANDARD Mode: Use search API (stateless)
            const response = await searchLibrary(question, userId, 'STANDARD');
            setResult(response);
            setLastQuestion(question);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Search failed');
        } finally {
            setIsSearching(false);
        }
    };

    const handleFeedback = async (rating: 1 | 0) => {
        if (!result || isSubmittingFeedback) return;
        setIsSubmittingFeedback(true);
        try {
            await submitFeedback({
                firebase_uid: userId,
                query: lastQuestion || question,
                answer: result.answer,
                rating,
                search_log_id: result.metadata?.search_log_id,
            });
            setFeedbackStatus(rating === 1 ? 'liked' : 'disliked');
        } catch (err) {
            console.error('Feedback failed:', err);
        } finally {
            setIsSubmittingFeedback(false);
        }
    };

    // Hide "AŞAMA 0" (Internal Self-Check) from user view
    const cleanAnswer = result?.answer.replace(/## AŞAMA 0:[\s\S]*?(?=##)/, "").trim() || "";

    return (
        <div className="max-w-[1100px] w-full mx-auto p-6 space-y-6">
            {/* Back to Home Button */}
            <div className="flex justify-start">
                <button
                    onClick={onBack}
                    className="group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                >
                    <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                        <ChevronLeft size={16} />
                    </div>
                    <span className="text-xs font-bold uppercase tracking-wider">Back to Home</span>
                </button>
            </div>

            {/* Search Form */}
            <form onSubmit={handleSearch} className="space-y-4">
                <div className="flex justify-center mb-4">
                    <div className="bg-slate-100 dark:bg-slate-800 p-1 rounded-lg inline-flex items-center">
                        <button
                            type="button"
                            className="px-4 py-2 rounded-md text-sm font-medium transition-all bg-white dark:bg-slate-700 text-[#CC561E] shadow-sm"
                        >
                            Standard
                        </button>
                        <button
                            type="button"
                            onClick={() => setMode('EXPLORER')}
                            className="px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 text-slate-500 hover:text-slate-700 dark:text-slate-400"
                        >
                            <MessageCircle className="w-4 h-4" /> Explorer
                        </button>
                    </div>
                </div>

                <div className="relative">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                    <input
                        type="text"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder={mode === 'EXPLORER' ? "Ask a complex question for deep analysis..." : "Ask a question about your books..."}
                        className="w-full pl-12 pr-4 py-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#CC561E] focus:border-transparent transition-all"
                        disabled={isSearching}
                    />
                </div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                    Tip: Kelimeyi netleştirmek için <span className="font-medium text-slate-700 dark:text-slate-300">@zaman</span> gibi yazabilirsin.
                </div>

                <button
                    type="submit"
                    disabled={isSearching || !question.trim()}
                    className={`w-full text-white font-medium py-3 px-6 rounded-xl transition-all duration-300 flex items-center justify-center gap-2 shadow-lg ${mode === 'EXPLORER'
                        ? 'bg-[#CC561E] hover:bg-[#b34b1a] shadow-[#CC561E]/20'
                        : 'bg-[#CC561E] hover:bg-[#b34b1a] shadow-[#CC561E]/20'
                        } disabled:bg-slate-300 dark:disabled:bg-slate-700`}
                >
                    {isSearching ? (
                        <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            {mode === 'EXPLORER' ? 'Deep Analysis...' : 'Searching...'}
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
                            <BookOpen className="w-5 h-5 text-[#CC561E]" />
                            Answer
                        </h2>
                        <div className="prose prose-slate dark:prose-invert max-w-none">
                            {/* Custom Rendering for Headers and Justified Text */}
                            {cleanAnswer.split('\n').map((line, i) => {
                                const trimmed = line.trim();
                                if (trimmed.startsWith('## ')) {
                                    // Header Style: Bold and Underlined
                                    return (
                                        <h3 key={i} className="text-lg font-bold underline decoration-[#CC561E]/50 underline-offset-4 mt-6 mb-3 text-slate-900 dark:text-white">
                                            {trimmed.replace(/^##\s+/, '')}
                                        </h3>
                                    );
                                }
                                else if (trimmed === '') {
                                    return <br key={i} />;
                                }
                                else {
                                    // Paragraph Style: Justified
                                    return (
                                        <p key={i} className="text-justify leading-relaxed text-slate-700 dark:text-slate-300 mb-2">
                                            {line}
                                        </p>
                                    );
                                }
                            })}
                        </div>

                        {/* Feedback Buttons */}
                        <div className="flex items-center gap-4 pt-4 border-t border-slate-100 dark:border-slate-700">
                            <span className="text-sm text-slate-500 dark:text-slate-400">
                                Was this answer helpful?
                            </span>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => handleFeedback(1)}
                                    disabled={feedbackStatus !== 'none' || isSubmittingFeedback}
                                    className={`p-2 rounded-lg transition-colors ${feedbackStatus === 'liked'
                                        ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                                        : 'text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-green-600'
                                        }`}
                                    title="Helpful"
                                >
                                    <ThumbsUp className="w-5 h-5" />
                                </button>
                                <button
                                    onClick={() => handleFeedback(0)}
                                    disabled={feedbackStatus !== 'none' || isSubmittingFeedback}
                                    className={`p-2 rounded-lg transition-colors ${feedbackStatus === 'disliked'
                                        ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'
                                        : 'text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-red-600'
                                        }`}
                                    title="Not helpful"
                                >
                                    <ThumbsDown className="w-5 h-5" />
                                </button>
                            </div>
                            {feedbackStatus !== 'none' && (
                                <span className="text-sm text-green-600 dark:text-green-400 animate-fade-in">
                                    Thanks for your feedback!
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Sources */}
                    {result.sources && result.sources.length > 0 && (
                        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                                <ExternalLink className="w-5 h-5 text-[#CC561E]" />
                                Sources ({result.sources.length})
                            </h3>
                            <div className="space-y-2">
                                {result.sources.map((source, index) => (
                                    <div
                                        key={index}
                                        className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                                    >
                                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] text-[#CC561E] dark:text-[#f3a47b] flex items-center justify-center text-sm font-medium">
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
                <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-6 space-y-3 w-full">
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
