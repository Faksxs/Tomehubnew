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

        // Activity Heatmap (Last 12 months)
        const heatmapData: Record<string, number> = {};
        itemsWithTime.forEach(i => {
            const date = new Date(i.addedMs).toISOString().split('T')[0];
            heatmapData[date] = (heatmapData[date] || 0) + 1;
        });
        items.flatMap(i => i.highlights || []).forEach(h => {
            const date = new Date(normalizeDate(h.createdAt)).toISOString().split('T')[0];
            heatmapData[date] = (heatmapData[date] || 0) + 1;
        });

        return {
            topTags,
            sortedTags,
            orphanCount,
            tScore: sortedTags.length > 0 ? (sortedTags.slice(0, Math.ceil(sortedTags.length * 0.1)).reduce((s, t) => s + t.count, 0) / Math.max(1, orphanCount)).toFixed(1) : '0.0',
            coldItems: coldItems.sort((a, b) => a.lastHighlightMs - b.lastHighlightMs).slice(0, 5),
            rustPercent: items.length > 0 ? Math.round((coldItems.length / items.length) * 100) : 0,
            heatmapData,
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
                <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    {[
                        { label: 'T-Profile Score', value: stats.tScore, sub: `${stats.orphanCount} Orphan Tags`, color: 'text-primary', icon: TrendingUp },
                        { label: 'Rust Index', value: `${stats.rustPercent}%`, sub: 'Inactive Nodes', color: 'text-orange-500', icon: Zap },
                        { label: 'Network Density', value: stats.sortedTags.length > 0 ? (items.length / stats.sortedTags.length).toFixed(1) : '0.0', sub: 'Node to Connection Ratio', color: 'text-blue-500', icon: Share2 },
                        { label: 'AI Readiness', value: `${items.length > 0 ? Math.round((items.filter(i => i.isIngested).length / items.length) * 100) : 0}%`, sub: 'Vectorized Assets', color: 'text-indigo-500', icon: Database },
                    ].map((s, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.1 }}
                            className="p-5 rounded-2xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30 shadow-sm"
                        >
                            <div className="flex justify-between items-start mb-2">
                                <p className="text-[10px] font-black uppercase text-slate-400 tracking-wider">{s.label}</p>
                                <s.icon size={14} className={s.color} />
                            </div>
                            <p className={`text-3xl font-black ${s.color}`}>{s.value}</p>
                            <p className="text-[10px] font-bold text-slate-500 uppercase mt-1">{s.sub}</p>
                        </motion.div>
                    ))}
                </section>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                    {/* Activity Heatmap (7/12 Span) */}
                    <div className="lg:col-span-8 space-y-4">
                        <div className="flex items-center justify-between px-2">
                            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                                <Activity size={14} className="text-primary" /> Learning Pulse
                            </h3>
                            <p className="text-[10px] font-bold text-slate-500 uppercase">Knowledge Intake Frequency</p>
                        </div>
                        <div className="p-6 rounded-3xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30">
                            <div className="flex gap-1.5 justify-center">
                                {Array.from({ length: 5 }).map((_, weekIdx) => (
                                    <div key={weekIdx} className="flex flex-col gap-1.5">
                                        {Array.from({ length: 7 }).map((_, dayIdx) => {
                                            const date = new Date();
                                            // 5 weeks = 35 days. (4 - weekIdx) * 7 + (6 - dayIdx)
                                            date.setDate(date.getDate() - (4 - weekIdx) * 7 - (6 - dayIdx));
                                            const dateStr = date.toISOString().split('T')[0];
                                            const count = stats.heatmapData[dateStr] || 0;
                                            const opacity = count === 0 ? 0.05 : Math.min(1, 0.2 + count * 0.2);

                                            return (
                                                <div
                                                    key={dayIdx}
                                                    title={`${dateStr}: ${count} actions`}
                                                    className="w-5 h-5 rounded-[4px] transition-all hover:scale-125 hover:ring-2 hover:ring-primary/50 cursor-pointer"
                                                    style={{ backgroundColor: `rgba(204, 86, 30, ${opacity})` }}
                                                />
                                            );
                                        })}
                                    </div>
                                ))}
                            </div>
                            <div className="flex justify-between mt-4 text-[9px] font-bold text-slate-400 uppercase tracking-widest px-2 max-w-[200px] mx-auto">
                                <span>30 Days Ago</span>
                                <span>Today</span>
                            </div>
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

                    {/* Core Nexus / Network (6/12 Span) */}
                    <div className="lg:col-span-6 space-y-4">
                        <div className="flex items-center justify-between px-2">
                            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 flex items-center gap-2">
                                <GitBranch size={14} className="text-blue-500" /> Core Nexus Connections
                            </h3>
                        </div>
                        <div className="p-6 rounded-3xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/30 overflow-hidden relative min-h-[300px]">
                            <div className="space-y-4">
                                {stats.pairs.slice(0, 8).map(([pair, count], idx) => {
                                    const [p1, p2] = pair.split('::');
                                    return (
                                        <motion.div
                                            key={idx}
                                            initial={{ x: -20, opacity: 0 }}
                                            animate={{ x: 0, opacity: 1 }}
                                            transition={{ delay: idx * 0.05 }}
                                            className="flex items-center gap-4 bg-slate-50 dark:bg-white/5 p-3 rounded-2xl border border-transparent hover:border-blue-500/20 transition-all"
                                        >
                                            <div className="w-8 h-8 rounded-full bg-blue-500/10 flex items-center justify-center text-[10px] font-black text-blue-500">
                                                {count}
                                            </div>
                                            <div className="flex-1 flex items-center gap-2 text-xs font-bold text-slate-600 dark:text-slate-300">
                                                <span className="px-2 py-0.5 rounded bg-blue-500/10 uppercase tracking-tight">{p1}</span>
                                                <span className="text-slate-400">↔</span>
                                                <span className="px-2 py-0.5 rounded bg-blue-500/10 uppercase tracking-tight">{p2}</span>
                                            </div>
                                        </motion.div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    {/* Paslanma / Rust Index Details (6/12 Span) */}
                    <div className="lg:col-span-6 space-y-4">
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
