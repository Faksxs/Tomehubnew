import React, { useState } from 'react';
import { Search, BookOpen, Loader2, AlertCircle, ExternalLink, ThumbsUp, ThumbsDown, MessageCircle, ChevronLeft, Sparkles, BarChart2, LayoutPanelLeft, FileSearch } from 'lucide-react';
import { DeepChatbotLogo, SmartSearchLogo } from './ui/FeatureLogos';
import { searchLibrary, submitFeedback, SearchResponse } from '../services/backendApiService';
import { ExplorerChat } from './ExplorerChat';
import { ConcordanceView } from './ConcordanceView';
import { getFriendlyApiErrorMessage } from '../services/apiClient';

import { LibraryItem } from '../types';

interface RAGSearchProps {
    userId: string;
    userEmail?: string | null;
    onBack?: () => void;
    books?: LibraryItem[];
}

export const RAGSearch: React.FC<RAGSearchProps> = ({ userId, userEmail, onBack, books = [] }) => {
    const [question, setQuestion] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [result, setResult] = useState<SearchResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [feedbackStatus, setFeedbackStatus] = useState<'none' | 'liked' | 'disliked'>('none');
    const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
    const [mode, setMode] = useState<'STANDARD' | 'EXPLORER'>('STANDARD');
    const [lastQuestion, setLastQuestion] = useState('');
    const [showConcordance, setShowConcordance] = useState(false);


    // If Explorer mode is active, render the dedicated chat component
    if (mode === 'EXPLORER') {
        return (
            <div className="max-w-[1100px] w-full mx-auto p-6 animate-fade-in space-y-4">
                <div className="flex justify-start">
                    <button
                        onClick={onBack}
                        className="group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                    >
                        <div className="p-1.5 rounded-lg bg-[#F3F5FA] dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                            <ChevronLeft size={16} />
                        </div>
                        <span className="text-xs font-bold uppercase tracking-wider">Back</span>
                    </button>
                </div>

                <div className="flex justify-center mb-2 md:mb-4">
                    <div className="bg-[#F3F5FA] dark:bg-slate-800 p-0.5 md:p-1 rounded-lg inline-flex items-center">
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

        if (!userId || userId.includes('@')) {
            setError('Authentication is still loading. Please wait a moment and try again.');
            return;
        }

        setIsSearching(true);
        setError(null);
        setResult(null);
        setFeedbackStatus('none');

        try {
            const response = await searchLibrary(question, userId, 'STANDARD');
            setResult(response);
            setLastQuestion(question);
        } catch (err) {
            setError(getFriendlyApiErrorMessage(err));
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

    const rawAnswer = result?.answer || "";
    const internalNotes = Array.from(rawAnswer.matchAll(/<think>([\s\S]*?)<\/think>/gi))
        .map((match) => (match[1] || '').trim())
        .filter(Boolean)
        .join('\n\n');
    const cleanAnswer = rawAnswer
        .replace(/<think>[\s\S]*?<\/think>/gi, '')
        .replace(/## AŞAMA 0:[\s\S]*?(?=##|$)/i, '')
        .trim();

    return (
        <div className={`max-w-[1100px] w-full mx-auto p-3 md:p-6 flex flex-col transition-all duration-1000 ease-in-out ${!result ? 'min-h-[70vh]' : 'space-y-6 md:space-y-8'}`}>
            {/* Header Area */}
            {/* Header Area */}
            <div className="relative flex flex-row items-center justify-between w-full h-10 md:h-12 mb-2 md:mb-6">
                <div className="flex items-center gap-3 md:gap-5 z-10">
                    <button
                        onClick={onBack}
                        className="group flex items-center gap-2 text-slate-500 dark:text-slate-400 hover:text-[#CC561E] transition-all duration-300"
                    >
                        <div className="p-1.5 rounded-lg bg-[#F3F5FA] dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                            <ChevronLeft size={16} />
                        </div>
                        <span className="text-xs font-bold uppercase tracking-wider hidden sm:inline">Back</span>
                    </button>
                </div>

                {/* Centered Branding - Only visible when results are shown */}
                {result && (
                    <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 md:gap-3 transition-all duration-500 origin-center animate-in fade-in zoom-in-95">
                        <div className="p-1.5 md:p-2 bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] rounded-2xl shrink-0 scale-75">
                            <SmartSearchLogo className="w-5 h-5 md:w-8 md:h-8" />
                        </div>
                        <h1 className="font-extrabold bg-gradient-to-r from-[#CC561E] to-[#e66a2e] bg-clip-text text-transparent tracking-tight text-xl md:text-2xl">
                            LogosChat
                        </h1>
                    </div>
                )}

                <div className="bg-[#F3F5FA] dark:bg-slate-800 p-0.5 md:p-1 rounded-lg inline-flex items-center z-10">
                    <button
                        type="button"
                        className="px-3 md:px-4 py-1.5 md:py-2 rounded-md text-xs md:text-sm font-medium transition-all bg-white dark:bg-slate-700 text-[#CC561E] shadow-sm"
                    >
                        Standard
                    </button>
                    <button
                        type="button"
                        onClick={() => setMode('EXPLORER')}
                        className="px-3 md:px-4 py-1.5 md:py-2 rounded-md text-xs md:text-sm font-medium transition-all flex items-center gap-1.5 md:gap-2 text-slate-500 hover:text-slate-700 dark:text-slate-400"
                    >
                        <MessageCircle className="w-3.5 h-3.5 md:w-4 md:h-4" /> Explorer
                    </button>
                </div>
            </div>

            <div className={`flex-1 flex flex-col relative transition-all duration-700 ${!result ? 'justify-center items-center' : 'pt-4 md:pt-6'}`}>
                {!result && !isSearching && (
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-4xl h-full pointer-events-none -z-10 animate-fade-in">
                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] md:w-[600px] h-[300px] md:h-[600px] bg-[#CC561E]/5 dark:bg-[#CC561E]/10 rounded-full blur-[80px] md:blur-[120px]" />
                        <div className="absolute top-1/3 left-1/4 w-[200px] h-[200px] bg-blue-500/5 dark:bg-blue-500/5 rounded-full blur-[100px]" />
                    </div>
                )}

                <form onSubmit={handleSearch} className={`space-y-4 md:space-y-6 w-full transition-all duration-1000 ease-in-out ${!result ? 'max-w-2xl text-center' : 'max-w-none'}`}>
                    {!result && !isSearching && (
                        <div className="mb-6 md:mb-10 space-y-4 animate-slide-up">
                            <div className="flex items-center justify-center gap-3">
                                <div className="p-1.5 md:p-2 bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] rounded-xl shrink-0">
                                    <DeepChatbotLogo className="w-5 h-5 md:w-8 md:h-8" />
                                </div>
                                <h1 className="text-2xl md:text-4xl font-black text-slate-900 dark:text-white tracking-tight">
                                    Logos<span className="text-[#CC561E]">Chat</span>
                                </h1>
                            </div>
                            <p className="text-sm md:text-base text-slate-500 dark:text-slate-400 max-w-lg mx-auto leading-relaxed">
                                Analyze your library with intelligence. Ask anything.
                            </p>
                        </div>
                    )}

                    <div className="relative group flex items-center">
                        <div className="relative flex-1 group">
                            <Search className="absolute left-4 md:left-5 top-1/2 -translate-y-1/2 w-4 h-4 md:w-5 md:h-5 text-slate-400 group-focus-within:text-[#CC561E] transition-colors" />
                            <input
                                type="text"
                                value={question}
                                onChange={(e) => setQuestion(e.target.value)}
                                placeholder="Type your question here..."
                                className="w-full pl-11 md:pl-14 pr-4 md:pr-6 py-3.5 md:py-5 rounded-2xl border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-800 text-base md:text-lg text-slate-900 dark:text-white shadow-sm focus:shadow-xl focus:shadow-[#CC561E]/5 focus:outline-none focus:ring-2 focus:ring-[#CC561E]/50 transition-all placeholder:text-slate-400"
                                disabled={isSearching}
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={isSearching || !question.trim()}
                            className={`ml-2 md:ml-3 p-3.5 md:p-5 rounded-2xl bg-[#CC561E] text-white shadow-lg shadow-[#CC561E]/20 hover:bg-[#b04a1a] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed group/btn`}
                        >
                            {isSearching ? (
                                <Loader2 className="w-5 h-5 md:w-6 md:h-6 animate-spin" />
                            ) : (
                                <Search className="w-5 h-5 md:w-6 md:h-6 group-hover/btn:scale-110 transition-transform" />
                            )}
                        </button>
                    </div>

                    <div className={`text-[11px] md:text-xs text-slate-500 dark:text-slate-400 ${!result ? 'text-center' : 'text-left'}`}>
                        Tip: <span className="font-bold text-[#CC561E]">Enter</span> to search. Mention <span className="font-bold text-[#CC561E]">@book</span> for focus.
                    </div>
                </form>
            </div>

            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                    <div>
                        <h3 className="font-medium text-red-900 dark:text-red-100">Search Failed</h3>
                        <p className="text-sm text-red-700 mt-1">{error}</p>
                    </div>
                </div>
            )}

            {result && (
                <div className="space-y-4 md:space-y-6">
                    <div className="bg-white dark:bg-slate-800 rounded-xl border border-[#E6EAF2] dark:border-slate-700 p-3.5 md:p-6 space-y-3 md:space-y-4">
                        <h2 className="text-lg md:text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-1.5 md:gap-2">
                            <BookOpen className="w-4 h-4 md:w-5 md:h-5 text-[#CC561E]" />
                            Answer
                        </h2>
                        <div className="max-w-none">
                            {cleanAnswer.split('\n').map((line, i) => {
                                const trimmed = line.trim();
                                if (trimmed.startsWith('## ')) {
                                    return (
                                        <h3 key={i} className="text-base md:text-lg font-bold underline decoration-[#CC561E]/50 underline-offset-4 mt-2.5 md:mt-6 mb-1 md:mb-2.5 text-slate-900 dark:text-white">
                                            {trimmed.replace(/^##\s+/, '')}
                                        </h3>
                                    );
                                } else if (trimmed === '') {
                                    return <div key={i} className="h-1 md:h-2" />;
                                } else {
                                    return (
                                        <p key={i} className="text-justify text-[14px] md:text-base leading-[1.55] md:leading-relaxed text-slate-700 dark:text-slate-300 mb-1.5 md:mb-2">
                                            {line}
                                        </p>
                                    );
                                }
                            })}
                        </div>

                        {internalNotes && (
                            <details className="rounded-lg border border-[#E6EAF2] dark:border-slate-700 bg-[#F8FAFC] dark:bg-slate-900/40">
                                <summary className="cursor-pointer select-none px-3 md:px-4 py-2.5 text-xs md:text-sm font-medium text-slate-600 dark:text-slate-300">
                                    Internal Notes (Optional)
                                </summary>
                                <div className="px-3 md:px-4 pb-3 md:pb-4 border-t border-[#E6EAF2] dark:border-slate-700">
                                    <pre className="mt-3 whitespace-pre-wrap break-words text-xs md:text-sm leading-relaxed text-slate-600 dark:text-slate-300 font-sans">
                                        {internalNotes}
                                    </pre>
                                </div>
                            </details>
                        )}

                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 md:gap-4 pt-2.5 md:pt-4 border-t border-[#E6EAF2] dark:border-slate-700">
                            <div className="flex items-center gap-2.5 md:gap-4">
                                <span className="text-xs md:text-sm text-slate-500 dark:text-slate-400">Was this answer helpful?</span>
                                <div className="flex items-center gap-1.5 md:gap-2">
                                    <button
                                        onClick={() => handleFeedback(1)}
                                        disabled={feedbackStatus !== 'none' || isSubmittingFeedback}
                                        className={`p-1.5 md:p-2 rounded-lg transition-colors ${feedbackStatus === 'liked' ? 'bg-green-100 text-green-600' : 'text-slate-400 hover:text-green-600'}`}
                                    >
                                        <ThumbsUp className="w-4 h-4 md:w-5 md:h-5" />
                                    </button>
                                    <button
                                        onClick={() => handleFeedback(0)}
                                        disabled={feedbackStatus !== 'none' || isSubmittingFeedback}
                                        className={`p-1.5 md:p-2 rounded-lg transition-colors ${feedbackStatus === 'disliked' ? 'bg-red-100 text-red-600' : 'text-slate-400 hover:text-red-600'}`}
                                    >
                                        <ThumbsDown className="w-4 h-4 md:w-5 md:h-5" />
                                    </button>
                                </div>
                            </div>

                            {/* Move Analytic Actions Here */}
                            {result.metadata?.status === 'analytic' && result.metadata?.analytics?.contexts && result.metadata.analytics.contexts.length > 0 && (
                                <button
                                    onClick={() => setShowConcordance(true)}
                                    className="flex items-center gap-1.5 md:gap-2 text-[#CC561E] hover:text-[#b34b1a] font-bold text-xs md:text-sm transition-colors py-1.5 md:py-2 px-2.5 md:px-3 hover:bg-orange-50 dark:hover:bg-orange-900/10 rounded-lg"
                                >
                                    <LayoutPanelLeft size={14} className="md:w-4 md:h-4" />
                                    See Contexts
                                </button>
                            )}
                        </div>
                    </div>

                    {result.sources && result.sources.length > 0 && (
                        <div className="bg-white dark:bg-slate-800 rounded-xl border border-[#E6EAF2] dark:border-slate-700 p-3.5 md:p-6 space-y-3 md:space-y-4">
                            <h3 className="text-base md:text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-1.5 md:gap-2">
                                <ExternalLink className="w-4 h-4 md:w-5 md:h-5 text-[#CC561E]" />
                                Sources ({result.sources.length})
                            </h3>
                            <div className="space-y-1.5 md:space-y-2">
                                {result.sources.map((source, index) => (
                                    <div key={index} className="flex items-start gap-2 md:gap-3 p-2 md:p-3 rounded-lg bg-[#F3F5FA] dark:bg-slate-700/50 hover:bg-[#F3F5FA] transition-colors">
                                        <div className="flex-shrink-0 w-5 h-5 md:w-6 md:h-6 rounded-full bg-[rgba(204,86,30,0.1)] text-[#CC561E] flex items-center justify-center text-xs md:text-sm font-medium">
                                            {index + 1}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm md:text-base font-medium text-slate-900 dark:text-white truncate">{source.title}</p>
                                            <p className="text-xs md:text-sm text-slate-600 dark:text-slate-400">Page {source.page_number}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {showConcordance && result?.metadata?.analytics && (
                <div className="fixed inset-0 z-[100] flex justify-end">
                    <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setShowConcordance(false)} />
                    <div className="relative w-full max-w-2xl h-full bg-white dark:bg-gray-900 shadow-2xl flex flex-col">
                        <ConcordanceView
                            term={result.metadata.analytics.term}
                            bookId={result.metadata.analytics.resolved_book_id}
                            initialContexts={result.metadata.analytics.contexts}
                            firebaseUid={userId}
                            onClose={() => setShowConcordance(false)}
                        />
                    </div>
                </div>
            )}


        </div>
    );
};

