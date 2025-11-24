import React from 'react';
import { LogOut, User, ArrowLeft, Sparkles, Play, Square, Loader2 } from 'lucide-react';
import { ImportBooks } from './ImportBooks';
import { ExportBooks } from './ExportBooks';
import { LibraryItem } from '../types';

interface ProfileViewProps {
    email: string | null | undefined;
    onLogout: () => void;
    onBack: () => void;
    books: LibraryItem[];
    onStartEnrichment: (books: LibraryItem[]) => void;
    onStopEnrichment: () => void;
    isEnriching: boolean;
    enrichmentStats: {
        total: number;
        processed: number;
        success: number;
        failed: number;
        currentBookTitle?: string;
    };
}

export const ProfileView: React.FC<ProfileViewProps> = ({
    email,
    onLogout,
    onBack,
    books,
    onStartEnrichment,
    onStopEnrichment,
    isEnriching,
    enrichmentStats
}) => {
    // Calculate how many books need enrichment
    const booksNeedingEnrichment = books.filter(b =>
        b.type === 'BOOK' &&
        (!b.generalNotes || b.generalNotes.length < 10) &&
        (!b.tags || b.tags.length === 0)
    ).length;
    return (
        <div className="p-6 md:p-10 max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4">
            {/* Back Button */}
            <button
                onClick={onBack}
                className="flex items-center gap-2 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white mb-6 transition-colors group"
            >
                <ArrowLeft size={20} className="group-hover:-translate-x-1 transition-transform" />
                <span className="font-medium">Back</span>
            </button>

            <div className="mb-8">
                <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Profile</h1>
                <p className="text-slate-500 dark:text-slate-400 mt-2">Manage your account settings</p>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden mb-8">
                <div className="p-6 md:p-8 border-b border-slate-100 dark:border-slate-800 flex flex-col md:flex-row items-start md:items-center gap-6">
                    <div className="w-20 h-20 bg-indigo-100 dark:bg-indigo-900/30 rounded-full flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                        <User size={40} />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-slate-900 dark:text-white">Account Information</h2>
                        <p className="text-slate-500 dark:text-slate-400 mt-1">Signed in as</p>
                        <p className="text-lg font-medium text-slate-900 dark:text-slate-200 mt-1">{email || 'No email available'}</p>
                    </div>
                </div>
                <div className="p-6 md:p-8 bg-slate-50/50 dark:bg-slate-900/50">
                    <button
                        onClick={onLogout}
                        className="flex items-center gap-2 px-6 py-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg font-medium transition-colors border border-red-100 dark:border-red-900/30"
                    >
                        <LogOut size={20} />
                        Log Out
                    </button>
                </div>
            </div>

            {/* AI Library Assistant Section */}
            <div className="bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800 shadow-sm overflow-hidden mb-8">
                <div className="p-6 md:p-8">
                    <div className="flex items-start gap-4 mb-6">
                        <div className="p-3 bg-white dark:bg-slate-900 rounded-lg shadow-sm text-indigo-600 dark:text-indigo-400">
                            <Sparkles size={24} />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-slate-900 dark:text-white">AI Library Assistant</h2>
                            <p className="text-slate-600 dark:text-slate-300 mt-1">
                                Automatically fill in missing summaries and tags for your imported books.
                            </p>
                        </div>
                    </div>

                    <div className="bg-white/60 dark:bg-slate-900/60 rounded-xl p-6 border border-indigo-100/50 dark:border-indigo-800/50">
                        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                            <div>
                                <h3 className="font-medium text-slate-900 dark:text-white mb-1">
                                    {isEnriching ? 'Enrichment in Progress...' : 'Library Status'}
                                </h3>
                                <p className="text-slate-500 dark:text-slate-400 text-sm">
                                    {isEnriching ? (
                                        <span>Processing: <span className="font-medium text-indigo-600 dark:text-indigo-400">{enrichmentStats.currentBookTitle || 'Initializing...'}</span></span>
                                    ) : (
                                        <span><span className="font-bold text-indigo-600 dark:text-indigo-400">{booksNeedingEnrichment}</span> books are missing details.</span>
                                    )}
                                </p>
                            </div>

                            {isEnriching ? (
                                <button
                                    onClick={onStopEnrichment}
                                    className="flex items-center gap-2 px-6 py-3 bg-white dark:bg-slate-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg font-medium transition-colors border border-red-100 dark:border-red-900/30 shadow-sm"
                                >
                                    <Square size={18} fill="currentColor" />
                                    Stop
                                </button>
                            ) : (
                                <button
                                    onClick={() => onStartEnrichment(books)}
                                    disabled={booksNeedingEnrichment === 0}
                                    className="flex items-center gap-2 px-6 py-3 bg-indigo-600 dark:bg-indigo-500 text-white hover:bg-indigo-700 dark:hover:bg-indigo-600 rounded-lg font-medium transition-colors shadow-md shadow-indigo-200 dark:shadow-none disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <Play size={18} fill="currentColor" />
                                    Auto-fill Missing Info
                                </button>
                            )}
                        </div>

                        {/* Progress Bar */}
                        {isEnriching && (
                            <div className="mt-6">
                                <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-2">
                                    <span>Progress</span>
                                    <span>{Math.round((enrichmentStats.processed / enrichmentStats.total) * 100)}%</span>
                                </div>
                                <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-indigo-500 dark:bg-indigo-400 transition-all duration-500 ease-out"
                                        style={{ width: `${(enrichmentStats.processed / enrichmentStats.total) * 100}%` }}
                                    />
                                </div>
                                <div className="flex justify-between text-xs text-slate-400 dark:text-slate-500 mt-2">
                                    <span>Processed: {enrichmentStats.processed}/{enrichmentStats.total}</span>
                                    <span>Success: {enrichmentStats.success} • Failed: {enrichmentStats.failed}</span>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <ImportBooks />
            <ExportBooks books={books} />
        </div>
    );
};
