import React, { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    ChevronLeft,
    Activity,
    Zap,
    GitBranch,
    TrendingUp,
    Sparkles,
    Search,
    Clock,
    Calendar,
    Share2,
    Database,
    Binary
} from 'lucide-react';
import { LibraryItem, Highlight } from '../types';

interface InsightsViewProps {
    items: LibraryItem[];
    onBack: () => void;
}

const PulseChart = ({ data }: { data: any[] }) => {
    // Max value is at least 1, and scaled to some sensible minimum
    const maxVal = Math.max(...data.map(d => d.books + d.insights), 1);

    return (
        <div className="w-full h-44 flex flex-col justify-end gap-2 pt-4 group/chart">
            <div className="flex-1 flex items-end justify-between px-1 gap-1 min-h-0">
                {data.map((d, i) => {
                    const total = d.books + d.insights;
                    const bRatio = total > 0 ? (d.books / maxVal) : 0;
                    const iRatio = total > 0 ? (d.insights / maxVal) : 0;

                    return (
                        <div key={i} className="flex-1 flex flex-col justify-end group/bar relative h-full">
                            {/* Tooltip */}
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 bg-slate-900 dark:bg-slate-800 text-white text-[9px] py-1.5 px-2.5 rounded-lg opacity-0 group-hover/bar:opacity-100 transition-all z-50 shadow-[0_8px_30px_rgb(0,0,0,0.3)] border border-white/10 whitespace-nowrap pointer-events-none translate-y-2 group-hover/bar:translate-y-0">
                                <p className="font-black text-primary mb-1 border-b border-white/5 pb-1">{d.label}</p>
                                <div className="space-y-1">
                                    <p className="font-bold flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-primary" /> {d.books} Books</p>
                                    <p className="font-bold flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-primary/40" /> {d.insights} Highlights</p>
                                </div>
                            </div>

                            {/* Stacked Bar container */}
                            <div className="w-full flex flex-col justify-end overflow-hidden rounded-t-[2px] bg-slate-100 dark:bg-white/5 h-full transition-colors group-hover/bar:bg-slate-200 dark:group-hover/bar:bg-white/10 relative">
                                {/* Insights Bar (Top) */}
                                {d.insights > 0 && (
                                    <motion.div
                                        initial={{ height: 0 }}
                                        animate={{ height: `${iRatio * 100}%` }}
                                        className="w-full bg-primary/30 relative z-10"
                                    />
                                )}
                                {/* Books Bar (Bottom) */}
                                {d.books > 0 && (
                                    <motion.div
                                        initial={{ height: 0 }}
                                        animate={{ height: `${bRatio * 100}%` }}
                                        className="w-full bg-primary relative z-20"
                                    />
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Legend & X-Axis */}
            <div className="flex items-center justify-between px-1 mt-1 border-t border-slate-200 dark:border-white/5 pt-3">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-[2px] bg-primary" />
                        <span className="text-[9px] font-black uppercase text-slate-500 tracking-wider">Books</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-[2px] bg-primary/40" />
                        <span className="text-[9px] font-black uppercase text-slate-500 tracking-wider">Highlights</span>
                    </div>
                </div>
                <div className="flex items-center gap-8 text-[9px] font-black text-slate-400 uppercase tracking-widest bg-slate-100 dark:bg-white/5 px-3 py-1 rounded-full border border-slate-200 dark:border-white/5">
                    <span>30 DAYS AGO</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-primary/20" />
                    <span>TODAY</span>
                </div>
            </div>
        </div>
    );
};

const InsightsView: React.FC<InsightsViewProps> = ({ items, onBack }) => {
    const normalizeTextKey = (value: string) => value.trim().toLocaleLowerCase('tr-TR');

    const normalizeDate = (value: unknown): number => {
        if (typeof value === 'number' && Number.isFinite(value)) {
            return value > 0 && value < 1_000_000_000_000 ? value * 1000 : value;
        }
        if (typeof value === 'string') {
            const parsed = Date.parse(value);
            return Number.isFinite(parsed) ? parsed : 0;
        }
        return 0;
    };

    // --- DATA CALCULATIONS ---
    const stats = useMemo(() => {
        const now = Date.now();
        const ninetyDaysMs = 90 * 24 * 60 * 60 * 1000;

        // Tag Stats & Co-occurrence
        const tagMap = new Map<string, { label: string; count: number }>();
        const pairMap = new Map<string, number>();

        items.forEach(item => {
            const tags = Array.from(new Set((item.tags || []).map(t => t.trim()).filter(Boolean)));
            tags.forEach(t => {
                const k = normalizeTextKey(t);
                const prev = tagMap.get(k);
                tagMap.set(k, { label: prev?.label || t, count: (prev?.count || 0) + 1 });
            });

            // Pairs for Network
            for (let i = 0; i < tags.length; i++) {
                for (let j = i + 1; j < tags.length; j++) {
                    const k1 = normalizeTextKey(tags[i]);
                    const k2 = normalizeTextKey(tags[j]);
                    const pair = [k1, k2].sort().join('::');
                    pairMap.set(pair, (pairMap.get(pair) || 0) + 1);
                }
            }
        });

        const sortedTags = Array.from(tagMap.values()).sort((a, b) => b.count - a.count);
        const topTags = sortedTags.slice(0, 10);
        const orphanCount = sortedTags.filter(t => t.count <= 2).length;

        // Rust index calculation
        const itemsWithTime = items.map(item => ({
            item,
            addedMs: normalizeDate(item.addedAt),
            lastHighlightMs: Math.max(...(item.highlights || []).map(h => normalizeDate(h.createdAt)), 0)
        }));

        const coldItems = itemsWithTime.filter(i =>
            i.item.type !== 'PERSONAL_NOTE' &&
            i.addedMs < now - ninetyDaysMs &&
            i.lastHighlightMs < now - ninetyDaysMs
        );

        // Activity over last 30 days (Daily)
        let last30DaysBooks = 0;
        let last30DaysHighlights = 0;
        const thirtyDaysAgo = now - (30 * 24 * 60 * 60 * 1000);
        const heatmapData: Record<string, number> = {};

        const dailyActivity = (() => {
            const data = [];
            const nowTime = new Date();
            for (let i = 29; i >= 0; i--) {
                const d = new Date(nowTime);
                d.setDate(d.getDate() - i);
                const dateStr = d.toISOString().split('T')[0];
                data.push({
                    date: dateStr,
                    books: 0,
                    insights: 0,
                    label: d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })
                });
            }

            itemsWithTime.forEach(i => {
                const date = new Date(i.addedMs).toISOString().split('T')[0];
                heatmapData[date] = (heatmapData[date] || 0) + 1;
                if (i.addedMs >= thirtyDaysAgo) last30DaysBooks++;
                const entry = data.find(d => d.date === date);
                if (entry) entry.books++;
            });

            items.flatMap(item => item.highlights || []).forEach(h => {
                const ms = normalizeDate(h.createdAt);
                const date = new Date(ms).toISOString().split('T')[0];
                heatmapData[date] = (heatmapData[date] || 0) + 1;
                if (ms >= thirtyDaysAgo) last30DaysHighlights++;
                const entry = data.find(d => d.date === date);
                if (entry) entry.insights++;
            });

            return data;
        })();

        const totalReadable = items.filter(i => i.type !== 'PERSONAL_NOTE').length;
        const unexplored = items.filter(i => i.type !== 'PERSONAL_NOTE' && (i.highlights?.length || 0) === 0).length;

        return {
            topTags,
            sortedTags,
            orphanCount,
            tScore: sortedTags.length > 0 ? (sortedTags.slice(0, Math.ceil(sortedTags.length * 0.1)).reduce((s, t) => s + t.count, 0) / Math.max(1, orphanCount)).toFixed(1) : '0.0',
            coldItems: coldItems.sort((a, b) => a.lastHighlightMs - b.lastHighlightMs).slice(0, 5),
            rustPercent: totalReadable > 0 ? Math.round((coldItems.length / totalReadable) * 100) : 0,
            last30DaysBooks,
            last30DaysHighlights,
            dailyActivity,
            heatmapData,
            totalReadable,
            unexplored,
            ingestRatio: totalReadable > 0 ? Math.round((items.filter(i => i.isIngested).length / totalReadable) * 100) : 0,
            pairs: Array.from(pairMap.entries()).sort((a, b) => b[1] - a[1]).slice(0, 15)
        };
    }, [items]);

    return (
        <div className="flex-1 h-full flex flex-col bg-[#F7F8FB] dark:bg-[#0b0e14] overflow-hidden">
            {/* Header */}
            <header className="px-6 py-4 flex items-center justify-between border-b border-slate-200 dark:border-white/5 bg-white/50 dark:bg-slate-900/50 backdrop-blur-md z-30">
                <div className="flex items-center gap-4">
                    <button
                        onClick={onBack}
                        className="p-2 hover:bg-slate-200 dark:hover:bg-white/10 rounded-xl transition-colors text-slate-500 dark:text-slate-400"
                    >
                        <ChevronLeft size={20} />
                    </button>
                    <div>
                        <h1 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <Sparkles className="text-primary animate-pulse" size={18} /> Deep Analytics
                        </h1>
                        <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Internal Knowledge Topography</p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-[10px] font-black uppercase tracking-wider">
                        v2.2_Neural
                    </div>
                </div>
            </header>

            {/* Scrollable Content */}
            <main className="flex-1 overflow-y-auto p-6 space-y-8">

                {/* Top Statistics Row */}
                <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    {[
                        { label: 'Pulse', value: `+${stats.last30DaysBooks + stats.last30DaysHighlights}`, sub: '30 Day Activity', color: 'text-primary', icon: Activity },
                        { label: 'T-Profile', value: stats.tScore, sub: `${stats.orphanCount} Orphans`, color: 'text-[#F63049]', icon: TrendingUp },
                        { label: 'Rust Index', value: `${stats.rustPercent}%`, sub: `${stats.totalReadable - stats.coldItems.length} Active Nodes`, color: 'text-orange-500', icon: Zap },
                        { label: 'Intellect', value: `${stats.ingestRatio}%`, sub: `${items.filter(i => i.isIngested).length} Ingested`, color: 'text-indigo-500', icon: Sparkles },
                    ].map((s, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: i * 0.05 }}
                            className="p-4 rounded-2xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30 shadow-sm flex flex-col justify-between"
                        >
                            <div className="flex justify-between items-start mb-2">
                                <p className="text-[9px] font-black uppercase text-slate-400 tracking-wider truncate mr-1">{s.label}</p>
                                <s.icon size={12} className={s.color} />
                            </div>
                            <div>
                                <p className={`text-xl font-black truncate ${s.color}`}>{s.value}</p>
                                <p className="text-[8px] font-bold text-slate-500 uppercase mt-0.5 truncate">{s.sub}</p>
                            </div>
                        </motion.div>
                    ))}
                </section>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                    {/* Activity Heatmap (7/12 Span) */}
                    <div className="lg:col-span-8 space-y-4">
                        <div className="flex items-center justify-between px-2">
                            <div className="space-y-1">
                                <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                                    <Activity size={14} className="text-primary" /> Learning Pulse
                                </h3>
                                <div className="flex items-center gap-4 mt-1">
                                    <div className="flex items-baseline gap-1.5">
                                        <span className="text-lg font-black text-slate-700 dark:text-slate-200">{stats.last30DaysBooks}</span>
                                        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">Books</span>
                                    </div>
                                    <div className="w-1 h-1 rounded-full bg-slate-300 dark:bg-white/10" />
                                    <div className="flex items-baseline gap-1.5">
                                        <span className="text-lg font-black text-slate-700 dark:text-slate-200">{stats.last30DaysHighlights}</span>
                                        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-tight">Highlights</span>
                                    </div>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-[10px] font-bold text-slate-500 uppercase">Knowledge Intake Frequency</p>
                                <p className="text-[9px] font-medium text-slate-400">Last 30 Days Activity</p>
                            </div>
                        </div>
                        <div className="p-6 rounded-3xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30">
                            <PulseChart data={stats.dailyActivity} />
                        </div>
                    </div>

                    {/* Top Nodes / Focus (5/12 Span) */}
                    <div className="lg:col-span-4 space-y-4">
                        <div className="flex items-center justify-between px-2">
                            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                                <Binary size={14} className="text-indigo-500" /> Top Nodes
                            </h3>
                        </div>
                        <div className="p-6 rounded-3xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30 space-y-3">
                            {stats.topTags.slice(0, 6).map((tag, idx) => (
                                <div key={idx} className="space-y-1.5">
                                    <div className="flex justify-between items-center text-xs font-bold">
                                        <span className="text-slate-700 dark:text-slate-200 uppercase tracking-tight">{tag.label}</span>
                                        <span className="text-slate-400">{tag.count}</span>
                                    </div>
                                    <div className="h-1.5 w-full bg-slate-100 dark:bg-white/5 rounded-full overflow-hidden">
                                        <motion.div
                                            initial={{ width: 0 }}
                                            animate={{ width: `${(tag.count / stats.topTags[0].count) * 100}%` }}
                                            className="h-full bg-indigo-500/60"
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                    {/* Paslanma / Rust Index Details (12/12 Span) */}
                    <div className="lg:col-span-12 space-y-4">
                        <div className="flex items-center justify-between px-2">
                            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                                <Clock size={14} className="text-orange-500" /> Stale Nodes (Forgotten Knowledge)
                            </h3>
                        </div>
                        <div className="p-6 rounded-3xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30 space-y-4">
                            {stats.coldItems.length > 0 ? stats.coldItems.map((cold, idx) => (
                                <motion.div
                                    key={idx}
                                    className="flex items-center justify-between p-3 rounded-2xl bg-orange-500/5 border border-orange-500/10"
                                >
                                    <div className="flex-1 truncate mr-4">
                                        <p className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{cold.item.title}</p>
                                        <p className="text-[10px] text-slate-500 font-medium">Added {new Date(cold.addedMs).toLocaleDateString()}</p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-[10px] font-black text-orange-500 uppercase">Last Read</p>
                                        <p className="text-[10px] font-bold text-slate-500 uppercase">
                                            {cold.lastHighlightMs > 0 ? new Date(cold.lastHighlightMs).toLocaleDateString() : 'Never'}
                                        </p>
                                    </div>
                                </motion.div>
                            )) : (
                                <div className="h-40 flex flex-col items-center justify-center text-center opacity-40">
                                    <Calendar size={32} className="mb-2" />
                                    <p className="text-xs font-bold uppercase tracking-widest">Your Knowledge is Fresh</p>
                                </div>
                            )}
                            <div className="pt-2">
                                <p className="text-[10px] font-bold text-slate-500 text-center uppercase tracking-widest italic">
                                    Refresh these nodes by adding new insights
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

            </main>
        </div>
    );
};

export default InsightsView;
