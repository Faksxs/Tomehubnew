import React, { useEffect, useMemo, useState } from 'react';
import { LogOut, User, ArrowLeft, Sparkles, Play, Square, Loader2, BrainCircuit, RefreshCw, BookOpenText, NotebookTabs, MessagesSquare, CircleHelp } from 'lucide-react';
import { LibraryItem } from '../types';
import { getMemoryProfile, MemoryProfileResponse, refreshMemoryProfile } from '../services/backendApiService';

interface ProfileViewProps {
    userId: string;
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
    userId,
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

    const [memoryProfile, setMemoryProfile] = useState<MemoryProfileResponse | null>(null);
    const [memoryLoading, setMemoryLoading] = useState(true);
    const [memoryRefreshing, setMemoryRefreshing] = useState(false);
    const [memoryError, setMemoryError] = useState<string | null>(null);

    useEffect(() => {
        let isActive = true;

        const loadProfile = async () => {
            if (!userId) {
                if (isActive) {
                    setMemoryProfile(null);
                    setMemoryLoading(false);
                }
                return;
            }
            try {
                setMemoryLoading(true);
                setMemoryError(null);
                const profile = await getMemoryProfile(userId);
                if (isActive) {
                    setMemoryProfile(profile);
                }
            } catch (error) {
                if (isActive) {
                    const message = error instanceof Error ? error.message : 'Memory profile could not be loaded.';
                    setMemoryError(message);
                }
            } finally {
                if (isActive) {
                    setMemoryLoading(false);
                }
            }
        };

        void loadProfile();
        return () => {
            isActive = false;
        };
    }, [userId]);

    const handleRefreshMemory = async () => {
        if (!userId || memoryRefreshing) return;
        try {
            setMemoryRefreshing(true);
            setMemoryError(null);
            const profile = await refreshMemoryProfile(userId, true);
            setMemoryProfile(profile);
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Memory profile could not be refreshed.';
            setMemoryError(message);
        } finally {
            setMemoryRefreshing(false);
        }
    };

    const evidenceCounts = useMemo(() => {
        const counts = memoryProfile?.evidence_counts || {};
        return {
            notes: Number(counts.notes || 0),
            messages: Number(counts.messages || 0),
            sessions: Number(counts.sessions || 0),
            reports: Number(counts.reports || 0),
        };
    }, [memoryProfile]);

    const memorySignalCount = evidenceCounts.notes + evidenceCounts.messages + evidenceCounts.sessions + evidenceCounts.reports;
    const lastRefreshLabel = memoryProfile?.last_refreshed_at
        ? new Date(memoryProfile.last_refreshed_at).toLocaleString()
        : 'Not refreshed yet';

    return (
        <div className="p-6 md:p-10 max-w-[1100px] w-full mx-auto animate-in fade-in slide-in-from-bottom-4">
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
                    <div className="w-20 h-20 bg-[#262D40]/8 dark:bg-[#262D40]/30 rounded-full flex items-center justify-center text-[#262D40] dark:text-[#262D40]/82">
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
            <div className="bg-gradient-to-br from-[#262D40]/5 to-purple-50 dark:from-[#262D40]/20 dark:to-purple-900/20 rounded-xl border border-[#262D40]/8 dark:border-[#262D40]/70 shadow-sm overflow-hidden mb-8">
                <div className="p-6 md:p-8">
                    <div className="flex items-start gap-4 mb-6">
                        <div className="p-3 bg-white dark:bg-slate-900 rounded-lg shadow-sm text-[#262D40] dark:text-[#262D40]/82">
                            <Sparkles size={24} />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-slate-900 dark:text-white">AI Library Assistant</h2>
                            <p className="text-slate-600 dark:text-slate-300 mt-1">
                                Automatically fill in missing summaries and tags for your imported books.
                            </p>
                        </div>
                    </div>

                    <div className="bg-white/60 dark:bg-slate-900/60 rounded-xl p-6 border border-[#262D40]/50 dark:border-[#262D40]/50">
                        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                            <div>
                                <h3 className="font-medium text-slate-900 dark:text-white mb-1">
                                    {isEnriching ? 'Enrichment in Progress...' : 'Library Status'}
                                </h3>
                                <p className="text-slate-500 dark:text-slate-400 text-sm">
                                    {isEnriching ? (
                                        <span>Processing: <span className="font-medium text-[#262D40] dark:text-[#262D40]/82">{enrichmentStats.currentBookTitle || 'Initializing...'}</span></span>
                                    ) : (
                                        <span><span className="font-bold text-[#262D40] dark:text-[#262D40]/82">{booksNeedingEnrichment}</span> books are missing details.</span>
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
                                    className="flex items-center gap-2 px-6 py-3 bg-[#262D40]/40 dark:bg-[#262D40]/30 text-white hover:bg-[#262D40]/55 dark:hover:bg-[#262D40]/40 rounded-lg font-medium transition-colors shadow-md shadow-[#262D40]/12 dark:shadow-none disabled:opacity-50 disabled:cursor-not-allowed"
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
                                        className="h-full bg-[#262D40]/30 dark:bg-[#262D40]/24 transition-all duration-500 ease-out"
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

            <div className="bg-[radial-gradient(circle_at_top_left,_rgba(20,184,166,0.18),_transparent_42%),linear-gradient(135deg,_rgba(15,23,42,0.96),_rgba(30,41,59,0.94))] rounded-2xl border border-slate-800 shadow-[0_30px_80px_-45px_rgba(15,23,42,0.85)] overflow-hidden mb-8">
                <div className="p-6 md:p-8">
                    <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                        <div className="max-w-2xl">
                            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                                <BrainCircuit size={14} />
                                Reading Memory
                            </div>
                            <h2 className="mt-4 text-2xl font-semibold text-white">Cross-session reading profile</h2>
                            <p className="mt-2 text-sm leading-6 text-slate-300">
                                TomeHub now compacts your recent notes, chats, and reports into a reusable memory layer for Explorer and future weekly summaries.
                            </p>
                        </div>

                        <button
                            onClick={handleRefreshMemory}
                            disabled={memoryRefreshing || memoryLoading}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-medium text-white transition hover:bg-white/14 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            {memoryRefreshing || memoryLoading ? (
                                <Loader2 size={16} className="animate-spin" />
                            ) : (
                                <RefreshCw size={16} />
                            )}
                            Refresh Memory
                        </button>
                    </div>

                    <div className="mt-6 grid gap-4 md:grid-cols-4">
                        <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-slate-400">
                                <NotebookTabs size={14} />
                                Notes
                            </div>
                            <div className="mt-3 text-3xl font-semibold text-white">{evidenceCounts.notes}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-slate-400">
                                <MessagesSquare size={14} />
                                Messages
                            </div>
                            <div className="mt-3 text-3xl font-semibold text-white">{evidenceCounts.messages}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-slate-400">
                                <BookOpenText size={14} />
                                Reports
                            </div>
                            <div className="mt-3 text-3xl font-semibold text-white">{evidenceCounts.reports}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/6 p-4">
                            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-slate-400">
                                <Sparkles size={14} />
                                Signals
                            </div>
                            <div className="mt-3 text-3xl font-semibold text-white">{memorySignalCount}</div>
                        </div>
                    </div>

                    <div className="mt-6 grid gap-4 lg:grid-cols-[1.45fr_0.95fr]">
                        <div className="rounded-2xl border border-white/10 bg-white/6 p-5">
                            <div className="flex items-center justify-between gap-3">
                                <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-300">Current Profile</h3>
                                <span className="text-xs text-slate-400">Last refresh: {lastRefreshLabel}</span>
                            </div>
                            {memoryLoading ? (
                                <div className="mt-4 space-y-3">
                                    <div className="h-4 w-3/4 animate-pulse rounded bg-white/10" />
                                    <div className="h-4 w-full animate-pulse rounded bg-white/10" />
                                    <div className="h-4 w-5/6 animate-pulse rounded bg-white/10" />
                                </div>
                            ) : memoryError ? (
                                <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                                    {memoryError}
                                </div>
                            ) : memoryProfile?.profile_summary ? (
                                <p className="mt-4 text-sm leading-7 text-slate-200">
                                    {memoryProfile.profile_summary}
                                </p>
                            ) : (
                                <div className="mt-4 rounded-xl border border-dashed border-white/15 bg-slate-950/30 px-4 py-4 text-sm text-slate-300">
                                    Memory profile is still thin. Add more highlights, personal notes, or Explorer chats, then refresh this panel.
                                </div>
                            )}
                        </div>

                        <div className="rounded-2xl border border-white/10 bg-white/6 p-5">
                            <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-slate-300">
                                <CircleHelp size={15} />
                                Open Questions
                            </h3>
                            <div className="mt-4 space-y-3">
                                {(memoryProfile?.open_questions || []).slice(0, 4).map((question) => (
                                    <div
                                        key={question}
                                        className="rounded-xl border border-amber-300/20 bg-amber-200/10 px-4 py-3 text-sm leading-6 text-amber-50"
                                    >
                                        {question}
                                    </div>
                                ))}
                                {!(memoryProfile?.open_questions || []).length && (
                                    <div className="rounded-xl border border-dashed border-white/15 bg-slate-950/30 px-4 py-4 text-sm text-slate-300">
                                        No recurring question has been promoted yet.
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="mt-6 grid gap-4 lg:grid-cols-2">
                        <div className="rounded-2xl border border-white/10 bg-white/6 p-5">
                            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-300">Active Themes</h3>
                            <div className="mt-4 flex flex-wrap gap-2">
                                {(memoryProfile?.active_themes || []).slice(0, 8).map((theme) => (
                                    <span
                                        key={theme}
                                        className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 text-xs font-medium text-emerald-100"
                                    >
                                        {theme}
                                    </span>
                                ))}
                                {!(memoryProfile?.active_themes || []).length && (
                                    <span className="text-sm text-slate-400">Themes will appear after the first usable summary.</span>
                                )}
                            </div>
                        </div>

                        <div className="rounded-2xl border border-white/10 bg-white/6 p-5">
                            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-300">Recurring Sources</h3>
                            <div className="mt-4 flex flex-wrap gap-2">
                                {(memoryProfile?.recurring_sources || []).slice(0, 8).map((source) => (
                                    <span
                                        key={source}
                                        className="rounded-full border border-sky-300/25 bg-sky-300/10 px-3 py-1.5 text-xs font-medium text-sky-100"
                                    >
                                        {source}
                                    </span>
                                ))}
                                {!(memoryProfile?.recurring_sources || []).length && (
                                    <span className="text-sm text-slate-400">Repeated books, authors, and references will show up here.</span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Migration Section removed */}
        </div>
    );
};
