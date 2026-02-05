import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Book,
    BookOpen,
    FileText,
    Globe,
    PenTool,
    Quote,
    ChevronDown,
    ChevronUp,
    PieChart,
    Activity,
    TrendingUp,
    GitBranch,
    Sparkles,
    Search,
    CheckCircle,
    Clock,
    Star,
    Zap,
    LayoutGrid,
    Archive
} from 'lucide-react';
import { LibraryItem } from '../../types';
import { CATEGORIES } from '../CategorySelector';

interface KnowledgeDashboardProps {
    items: LibraryItem[];
    onCategorySelect?: (category: string) => void;
    onNavigateToTab?: (tab: string) => void;
}

export const KnowledgeDashboard: React.FC<KnowledgeDashboardProps> = ({
    items,
    onCategorySelect,
    onNavigateToTab
}) => {
    const [showLevelC, setShowLevelC] = useState(false);

    // --- DATA PROCESSING (LEVEL A) ---
    const books = items.filter(i => i.type === 'BOOK');
    const articles = items.filter(i => i.type === 'ARTICLE');
    const websites = items.filter(i => i.type === 'WEBSITE');
    const personalNotes = items.filter(i => i.type === 'PERSONAL_NOTE');
    const allHighlights = items.flatMap(i => i.highlights || []);

    const statsA = [
        { label: 'Highlights', value: allHighlights.length, icon: Quote, tab: 'NOTES' },
        { label: 'Total Books', value: books.length, icon: Book, tab: 'BOOK' },
        { label: 'Articles', value: articles.length, icon: FileText, tab: 'ARTICLE' },
        { label: 'Websites', value: websites.length, icon: Globe, tab: 'WEBSITE' },
        { label: 'Notes', value: personalNotes.length, icon: PenTool, tab: 'PERSONAL_NOTE' },
    ];

    // --- DATA PROCESSING (LEVEL B) ---
    const readableItems = items.filter(i => i.type !== 'PERSONAL_NOTE');
    const finishedCount = readableItems.filter(i => i.readingStatus === 'Finished').length;
    const readingCount = readableItems.filter(i => i.readingStatus === 'Reading').length;
    const toReadCount = readableItems.filter(i => i.readingStatus === 'To Read').length;

    const lentCount = books.filter(i => i.status === 'Lent Out').length;
    const lostCount = books.filter(i => i.status === 'Lost').length;
    const onShelfCount = books.filter(i => i.status === 'On Shelf').length;

    // --- DATA PROCESSING (LEVEL C) ---
    const now = Date.now();
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    const addedLast7 = items.filter(i => i.addedAt >= now - weekMs).length;
    const addedPrev7 = items.filter(i => i.addedAt >= now - (2 * weekMs) && i.addedAt < now - weekMs).length;
    const last7Delta = addedLast7 - addedPrev7;

    const itemsLast7 = items.filter(i => i.addedAt >= now - weekMs);
    const conceptBridgesLast7 = itemsLast7.reduce((sum, i) => sum + Math.max(0, (i.tags?.length || 0) - 1), 0);

    const tagCounts = new Map<string, number>();
    items.forEach(item => {
        (item.tags || []).forEach(tag => {
            const key = tag.trim();
            if (!key) return;
            tagCounts.set(key, (tagCounts.get(key) || 0) + 1);
        });
    });
    let topTag = '';
    let topTagCount = 0;
    tagCounts.forEach((count, tag) => {
        if (count > topTagCount) {
            topTag = tag;
            topTagCount = count;
        }
    });
    const unexploredCount = readableItems.filter(i => (i.highlights?.length || 0) === 0).length;

    return (
        <div className="min-h-full w-full p-6 md:p-8 lg:p-10 space-y-8 animate-in fade-in duration-700 relative">

            {/* Header (Perfect Size) */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-5 max-w-6xl mx-auto relative z-20">
                <div className="space-y-1">
                    <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-xl border border-primary/5">
                            <LayoutGrid className="w-6 h-6 text-primary" />
                        </div>
                        Knowledge Base
                    </h2>
                    <p className="text-slate-500 dark:text-slate-400 font-medium text-xs md:text-sm pl-1">
                        Intellect Operating System
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <span className="px-3 py-1 rounded-xl bg-white/40 dark:bg-white/5 backdrop-blur-md text-slate-500 dark:text-slate-400 text-[10px] font-bold uppercase tracking-widest border border-slate-200/50 dark:border-white/10 shadow-sm">
                        System v2.1.3 Balanced
                    </span>
                </div>
            </div>

            <div className="max-w-6xl mx-auto space-y-8 relative z-20">

                {/* 🔸 Level A – Core Assets (Perfect Ratios) */}
                <section className="space-y-4">
                    <div className="flex items-center gap-2 px-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
                        <Activity size={12} className="text-primary/60" /> Level A • Core Stats
                    </div>
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                        {statsA.map((stat, idx) => (
                            <motion.div
                                key={stat.label}
                                initial={{ opacity: 0, scale: 0.98, y: 10 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                transition={{ delay: idx * 0.04 }}
                                onClick={() => onNavigateToTab?.(stat.tab)}
                                className="
                    relative overflow-hidden
                    group cursor-pointer
                    rounded-[1.5rem] border border-white/80 dark:border-white/10
                    bg-white/50 dark:bg-slate-900/40
                    backdrop-blur-xl shadow-sm
                    hover:shadow-md hover:border-primary/20 hover:-translate-y-1
                    transition-all duration-300
                    flex flex-col items-center justify-center p-6 gap-3
                    text-center
                "
                            >
                                <div className="p-3 rounded-2xl bg-primary/5 dark:bg-primary/10 group-hover:bg-primary/15 transition-colors">
                                    <stat.icon className="w-5 h-5 text-primary" strokeWidth={1.5} />
                                </div>
                                <div className="space-y-1">
                                    <p className="text-3xl font-black text-slate-900 dark:text-white tracking-tight tabular-nums group-hover:text-primary transition-colors">
                                        {stat.value}
                                    </p>
                                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500/80">{stat.label}</p>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </section>

                {/* 🔸 Level B – Organization (Perfect Fit Glass Pane) */}
                <section className="space-y-4">
                    <div className="flex items-center gap-2 px-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
                        <PieChart size={12} className="text-primary/60" /> Level B • Structure
                    </div>

                    <div className="
                rounded-[2rem] border border-white/60 dark:border-white/10
                bg-white/40 dark:bg-slate-900/30
                backdrop-blur-2xl shadow-sm
                p-8 lg:p-10
            ">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-12">

                            {/* Category Distribution */}
                            <div className="md:col-span-8 flex flex-col gap-6">
                                <div className="flex items-center gap-3 border-b border-slate-200/50 dark:border-white/5 pb-4">
                                    <LayoutGrid size={16} className="text-primary" />
                                    <h3 className="font-bold text-slate-800 dark:text-slate-200 tracking-tight">System Distribution</h3>
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-y-4 gap-x-10">
                                    {CATEGORIES.map(category => {
                                        const count = books.filter(b => b.tags?.includes(category)).length;
                                        const percentage = books.length > 0 ? (count / books.length) * 100 : 0;
                                        if (count === 0 && books.length > 0) return null;

                                        return (
                                            <div key={category}
                                                onClick={() => onCategorySelect?.(category)}
                                                className="group cursor-pointer p-2.5 rounded-xl hover:bg-white/80 dark:hover:bg-white/5 transition-all duration-300 border border-transparent hover:border-slate-200/80 dark:hover:border-white/10"
                                            >
                                                <div className="flex justify-between items-end mb-2">
                                                    <span className="text-xs font-bold text-slate-500 group-hover:text-primary transition-colors">{category}</span>
                                                    <span className="text-xs font-black text-slate-800 dark:text-slate-200">{count}</span>
                                                </div>
                                                <div className="w-full h-1.5 bg-slate-200/50 dark:bg-slate-700/30 rounded-full overflow-hidden">
                                                    <motion.div
                                                        initial={{ width: 0 }}
                                                        animate={{ width: `${percentage}%` }}
                                                        className="h-full bg-primary/70 group-hover:bg-primary transition-colors"
                                                    />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Right Column */}
                            <div className="md:col-span-4 flex flex-col gap-8">
                                {/* Progress */}
                                <div className="space-y-4">
                                    <div className="flex items-center gap-3 border-b border-slate-200/50 dark:border-white/5 pb-4">
                                        <BookOpen size={16} className="text-emerald-500" />
                                        <h3 className="font-bold text-slate-800 dark:text-slate-200">Progress</h3>
                                    </div>
                                    <div className="space-y-1.5">
                                        <div className="flex items-center justify-between p-3 rounded-xl hover:bg-white/50 dark:hover:bg-white/5 transition-all text-xs font-bold text-slate-500">
                                            <span className="flex items-center gap-2"><CheckCircle size={14} className="text-emerald-500/70" /> Finished</span>
                                            <span className="text-slate-800 dark:text-slate-200">{finishedCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-xl hover:bg-white/50 dark:hover:bg-white/5 transition-all text-xs font-bold text-slate-500">
                                            <span className="flex items-center gap-2"><Zap size={14} className="text-amber-500/70" /> Reading</span>
                                            <span className="text-slate-800 dark:text-slate-200">{readingCount}</span>
                                        </div>
                                        <div className="flex items-center justify-between p-3 rounded-xl hover:bg-white/50 dark:hover:bg-white/5 transition-all text-xs font-bold text-slate-500">
                                            <span className="flex items-center gap-2"><Clock size={14} className="text-blue-500/70" /> To Read</span>
                                            <span className="text-slate-800 dark:text-slate-200">{toReadCount}</span>
                                        </div>
                                    </div>
                                </div>

                                {/* Inventory */}
                                <div className="space-y-4">
                                    <div className="flex items-center gap-3 border-b border-slate-200/50 dark:border-white/5 pb-4">
                                        <Archive size={16} className="text-indigo-500" />
                                        <h3 className="font-bold text-slate-800 dark:text-slate-200">Inventory</h3>
                                    </div>
                                    <div className="flex gap-3">
                                        <div className="flex-1 p-3 rounded-xl bg-white/50 dark:bg-white/5 text-center border border-slate-100 dark:border-white/5">
                                            <p className="text-[10px] uppercase font-black text-slate-400 mb-1">Shelf</p>
                                            <p className="text-base font-black text-slate-800 dark:text-slate-100">{onShelfCount}</p>
                                        </div>
                                        <div className="flex-1 p-3 rounded-xl bg-orange-500/5 text-center border border-primary/10">
                                            <p className="text-[10px] uppercase font-black text-primary/60 mb-1">Lent</p>
                                            <p className="text-base font-black text-primary">{lentCount}</p>
                                        </div>
                                        <div className="flex-1 p-3 rounded-xl bg-rose-500/5 text-center border border-rose-500/10">
                                            <p className="text-[10px] uppercase font-black text-rose-600/60 mb-1">Lost</p>
                                            <p className="text-base font-black text-rose-600">{lostCount}</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                        </div>
                    </div>
                </section>

                {/* 🔸 Level C – AI Insights (Perfect Minimal Toggle) */}
                <section className="space-y-4">
                    <button
                        onClick={() => setShowLevelC(!showLevelC)}
                        className="w-full flex items-center gap-4 px-1 py-2 group transition-all opacity-60 hover:opacity-100"
                    >
                        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-primary/80">
                            <Sparkles size={14} className="text-primary animate-pulse" /> Level C Insights
                        </div>
                        <div className="h-[1px] bg-slate-300 dark:bg-white/10 flex-1" />
                        <div className="text-slate-400 group-hover:text-primary transition-colors">
                            {showLevelC ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </div>
                    </button>

                    <AnimatePresence>
                        {showLevelC && (
                            <motion.div
                                initial={{ opacity: 0, height: 0, y: 10 }}
                                animate={{ opacity: 1, height: 'auto', y: 0 }}
                                exit={{ opacity: 0, height: 0, y: 10 }}
                                className="overflow-hidden"
                            >
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
                                    <div className="p-6 rounded-2xl border border-white/40 dark:border-white/10 bg-white/20 dark:bg-black/20 backdrop-blur-xl flex flex-col gap-2 shadow-sm">
                                        <p className="text-[10px] font-black uppercase text-slate-400 flex items-center gap-2">
                                            <TrendingUp size={12} className="text-emerald-500" /> Momentum
                                        </p>
                                        <p className={`text-2xl font-black ${last7Delta > 0 ? 'text-emerald-500' : 'text-slate-700 dark:text-slate-200'}`}>
                                            {last7Delta > 0 ? `+${last7Delta}` : last7Delta}
                                        </p>
                                    </div>
                                    <div className="p-6 rounded-2xl border border-white/40 dark:border-white/10 bg-white/20 dark:bg-black/20 backdrop-blur-xl flex flex-col gap-2 shadow-sm">
                                        <p className="text-[10px] font-black uppercase text-slate-400 flex items-center gap-2">
                                            <GitBranch size={12} className="text-blue-500" /> Bridges
                                        </p>
                                        <p className="text-2xl font-black text-slate-700 dark:text-slate-200">{conceptBridgesLast7}</p>
                                    </div>
                                    <div className="p-6 rounded-2xl border border-white/40 dark:border-white/10 bg-white/20 dark:bg-black/20 backdrop-blur-xl flex flex-col gap-2 shadow-sm">
                                        <p className="text-[10px] font-black uppercase text-slate-400 flex items-center gap-2">
                                            <Star size={12} className="text-amber-500" /> Focus
                                        </p>
                                        <p className="text-lg font-black text-slate-700 dark:text-slate-200 truncate">{topTag || '—'}</p>
                                    </div>
                                    <div className="p-6 rounded-2xl border border-white/40 dark:border-white/10 bg-white/20 dark:bg-black/20 backdrop-blur-xl flex flex-col gap-2 shadow-sm">
                                        <p className="text-[10px] font-black uppercase text-slate-400 flex items-center gap-2">
                                            <Search size={12} className="text-indigo-500" /> Discovery
                                        </p>
                                        <p className="text-2xl font-black text-slate-700 dark:text-slate-200">{unexploredCount}</p>
                                    </div>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </section>

            </div>

            {/* Footer Branding */}
            <div className="max-w-6xl mx-auto pt-8 border-t border-slate-200/50 dark:border-white/5 text-center opacity-20">
                <p className="text-[9px] font-black uppercase tracking-[0.5em] text-slate-500">TomeHub • Intellect Engine • v2.1.3_Balanced</p>
            </div>
        </div>
    );
};
