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
    PlayCircle,
    Star,
    Zap,
    LayoutGrid,
    Archive
} from 'lucide-react';
import { LibraryItem } from '../../types';
import { CATEGORIES } from '../CategorySelector';
import {
    KnowledgeBaseLogo,
    HighlightsLogo,
    BooksLogo,
    ArticlesLogo,
    WebsitesLogo,
    NotesLogo,
    SystemDistributionLogo,
    ProgressLogo,
    FocusLogo,
    InventoryLogo
} from '../ui/FeatureLogos';

interface KnowledgeDashboardProps {
    items: LibraryItem[];
    onCategorySelect?: (category: string) => void;
    onStatusSelect?: (status: string) => void;
    onNavigateToTab?: (tab: string) => void;
}

export const KnowledgeDashboard: React.FC<KnowledgeDashboardProps> = ({
    items,
    onCategorySelect,
    onStatusSelect,
    onNavigateToTab
}) => {
    const [showLevelC, setShowLevelC] = useState(false);
    const normalizeTextKey = (value: string) => value.trim().toLocaleLowerCase('tr-TR');
    const normalizeAddedAt = (value: unknown): number => {
        if (typeof value === 'number' && Number.isFinite(value)) {
            // Support both millisecond and second epoch values.
            return value > 0 && value < 1_000_000_000_000 ? value * 1000 : value;
        }
        if (typeof value === 'string') {
            const parsed = Date.parse(value);
            return Number.isFinite(parsed) ? parsed : 0;
        }
        return 0;
    };

    // --- DATA PROCESSING (LEVEL A) ---
    const books = items.filter(i => i.type === 'BOOK');
    const articles = items.filter(i => i.type === 'ARTICLE');
    const websites = items.filter(i => i.type === 'WEBSITE');
    const personalNotes = items.filter(i => i.type === 'PERSONAL_NOTE');
    const allHighlights = items.flatMap(i => i.highlights || []);

    const statsA = [
        { label: 'All Notes', value: allHighlights.length, icon: HighlightsLogo, tab: 'NOTES' },
        { label: 'Total Books', value: books.length, icon: BooksLogo, tab: 'BOOK' },
        { label: 'Articles', value: articles.length, icon: ArticlesLogo, tab: 'ARTICLE' },
        { label: 'Websites', value: websites.length, icon: WebsitesLogo, tab: 'WEBSITE' },
        { label: 'Personal Notes', value: personalNotes.length, icon: NotesLogo, tab: 'PERSONAL_NOTE' },
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
    const itemsWithAddedAt = items.map(item => ({
        item,
        addedAtMs: normalizeAddedAt(item.addedAt),
    }));
    const addedLast7 = itemsWithAddedAt.filter(i => i.addedAtMs >= now - weekMs).length;
    const addedPrev7 = itemsWithAddedAt.filter(i => i.addedAtMs >= now - (2 * weekMs) && i.addedAtMs < now - weekMs).length;
    const last7Delta = addedLast7 - addedPrev7;

    const itemsLast7 = itemsWithAddedAt.filter(i => i.addedAtMs >= now - weekMs).map(i => i.item);
    const conceptBridgesLast7 = itemsLast7.reduce((sum, i) => sum + Math.max(0, (i.tags?.length || 0) - 1), 0);

    const tagCounts = new Map<string, { label: string; count: number }>();
    items.forEach(item => {
        (item.tags || []).forEach(tag => {
            const trimmed = tag.trim();
            if (!trimmed) return;
            const key = normalizeTextKey(trimmed);
            const prev = tagCounts.get(key);
            tagCounts.set(key, {
                label: prev?.label || trimmed,
                count: (prev?.count || 0) + 1
            });
        });
    });
    let topTag = '';
    let topTagCount = 0;
    tagCounts.forEach((entry) => {
        if (entry.count > topTagCount) {
            topTag = entry.label;
            topTagCount = entry.count;
        }
    });
    const unexploredCount = readableItems.filter(i => (i.highlights?.length || 0) === 0).length;
    const categoryLookup = new Map<string, string>(
        CATEGORIES.map(category => [normalizeTextKey(category), category])
    );
    const categoryCounts = new Map<string, number>();
    books.forEach(book => {
        (book.tags || []).forEach(tag => {
            const canonical = categoryLookup.get(normalizeTextKey(tag));
            if (!canonical) return;
            categoryCounts.set(canonical, (categoryCounts.get(canonical) || 0) + 1);
        });
    });

    return (
        <div className="min-h-full w-full space-y-5 md:space-y-8 animate-in fade-in duration-700 relative">

            {/* Header (Perfect Size) */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-5 relative z-20">
                <div className="space-y-1">
                    <h2 className="text-xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5 md:gap-3">
                        <div className="relative group">
                            <div className="absolute -inset-2 bg-primary/20 blur-xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                            <div className="relative p-1.5 md:p-2 bg-primary/10 dark:bg-primary/20 rounded-xl border border-primary/30 dark:border-primary/40 shadow-[0_0_15px_rgba(204,86,30,0.2)]">
                                <KnowledgeBaseLogo size={24} className="text-primary dark:text-primary drop-shadow-[0_0_8px_rgba(204,86,30,0.8)] md:w-7 md:h-7" />
                            </div>
                        </div>
                        Dashboard
                    </h2>
                </div>
                <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-xl bg-white/40 dark:bg-white/5 backdrop-blur-md text-slate-500 dark:text-slate-400 text-[9px] md:text-[10px] font-bold uppercase tracking-widest border border-slate-200/50 dark:border-white/10 shadow-sm">
                        System v2.1.3 Balanced
                    </span>
                </div>
            </div>

            <div className="max-w-6xl mx-auto space-y-5 md:space-y-8 relative z-20">

                {/* 🔸 Level A – Core Assets (Perfect Ratios) */}
                <section className="space-y-2 md:space-y-4">
                    <div className="flex items-center gap-1.5 md:gap-2 px-1 text-[9px] md:text-[10px] font-bold uppercase tracking-[0.15em] md:tracking-[0.2em] text-slate-400 dark:text-slate-500">
                        <Activity size={11} className="text-primary/60 md:w-3 md:h-3" /> Level A • Core Stats
                    </div>
                    <div className="grid grid-cols-2 min-[560px]:grid-cols-3 lg:grid-cols-5 gap-2.5 md:gap-4">
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
                    rounded-xl md:rounded-[1.4rem] border border-slate-800/20 dark:border-white/10
                    bg-card dark:bg-slate-900/50
                    backdrop-blur-xl shadow-lg lg:shadow-md
                    hover:shadow-2xl hover:border-primary/40 dark:hover:border-primary/40 hover:-translate-y-1
                    transition-all duration-300
                    flex flex-col items-center justify-center p-2.5 md:p-5 gap-1 md:gap-2.5 min-h-[86px] md:min-h-0
                "
                            >
                                <div className="relative">
                                    <div className="absolute -inset-4 bg-orange-500/10 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                                    <div className="relative p-1.5 md:p-2.5 bg-orange-500/5 dark:bg-orange-500/10 rounded-lg md:rounded-2xl border border-orange-500/10 dark:border-orange-500/20 transition-colors group-hover:border-orange-500/40">
                                        <stat.icon className="w-4 h-4 md:w-[22px] md:h-[22px] text-[#CC561E] dark:text-[#f3a47b] drop-shadow-[0_0_5px_rgba(204,86,30,0.4)] group-hover:drop-shadow-[0_0_10px_rgba(204,86,30,0.8)] transition-all" />
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className="text-lg md:text-[28px] font-black tracking-tight text-white leading-none mb-0 md:mb-1">
                                        {stat.value}
                                    </div>
                                    <div className="text-[8px] md:text-[11px] font-bold uppercase tracking-[0.14em] md:tracking-widest text-slate-400/60 leading-none">
                                        {stat.label}
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </section>

                {/* 🔸 Level B – Organization (Perfect Fit Glass Pane) */}
                <section className="space-y-1 md:space-y-4">
                    <div className="flex items-center gap-1.5 md:gap-2 px-1 text-xs md:text-sm font-bold uppercase tracking-[0.15em] md:tracking-[0.2em] text-slate-400 dark:text-slate-500">
                        <PieChart size={12} className="text-primary/60" /> Level B • Structure
                    </div>

                    <div className="
                rounded-3xl md:rounded-[2rem] border border-slate-800/10 dark:border-white/10
                bg-card dark:bg-slate-900/50
                backdrop-blur-2xl shadow-xl
                p-3 md:p-8 lg:p-10
            ">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 md:gap-12">

                            {/* Category Distribution */}
                            <div className="md:col-span-8 flex flex-col gap-2.5 md:gap-6">
                                <div className="flex items-center gap-2 md:gap-3 border-b border-white/10 pb-2 md:pb-4">
                                    <SystemDistributionLogo size={16} className="text-primary md:w-5 md:h-5" />
                                    <h3 className="font-extrabold text-white tracking-tight uppercase text-sm">Category</h3>
                                </div>

                                <div className="grid grid-cols-2 lg:grid-cols-3 gap-y-1 md:gap-y-4 gap-x-2.5 md:gap-x-10">
                                    {CATEGORIES.map(category => {
                                        const count = categoryCounts.get(category) || 0;
                                        const percentage = books.length > 0 ? (count / books.length) * 100 : 0;
                                        if (count === 0 && books.length > 0) return null;

                                        return (
                                            <div
                                                key={category}
                                                onClick={() => onCategorySelect?.(category)}
                                                className="group cursor-pointer p-1 md:p-2.5 rounded-lg md:rounded-xl transition-all duration-200"
                                            >
                                                <div className="flex items-center justify-between mb-0.5 md:mb-2 px-0.5 md:px-1">
                                                    <span className="text-xs md:text-sm font-semibold text-white transition-all duration-200 inline-block group-hover:scale-[1.04] group-hover:font-bold truncate pr-2">
                                                        {category}
                                                    </span>
                                                    <span className="text-xs md:text-sm font-black text-white shrink-0">{count}</span>
                                                </div>
                                                <div className="w-full h-1 md:h-2 bg-slate-200 dark:bg-slate-700/30 rounded-full overflow-hidden shadow-inner">
                                                    <motion.div
                                                        initial={{ width: 0 }}
                                                        animate={{ width: `${percentage}%` }}
                                                        className="h-full bg-primary group-hover:bg-primary transition-colors"
                                                    />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Right Column */}
                            <div className="md:col-span-4 flex flex-col gap-3 md:gap-8">
                                {/* Progress */}
                                <div className="space-y-2 md:space-y-4">
                                    <div className="flex items-center gap-2 md:gap-3 border-b border-white/10 pb-2 md:pb-4">
                                        <ProgressLogo size={16} className="text-primary md:w-5 md:h-5" />
                                        <h3 className="font-extrabold text-white tracking-tight uppercase text-sm">Progress</h3>
                                    </div>
                                    <div className="space-y-1">
                                        <div
                                            onClick={() => onStatusSelect?.('Finished')}
                                            className="flex items-center justify-between p-1.5 md:p-3 rounded-lg md:rounded-xl hover:bg-slate-800/20 dark:hover:bg-white/5 transition-all text-xs md:text-sm font-bold text-slate-400 cursor-pointer group"
                                        >
                                            <span className="flex items-center gap-1.5 md:gap-2 group-hover:text-[#22C55E] transition-colors"><CheckCircle size={12} className="text-[#22C55E] md:w-[14px] md:h-[14px]" /> Finished</span>
                                            <span className="text-white text-xs md:text-sm">{finishedCount}</span>
                                        </div>
                                        <div
                                            onClick={() => onStatusSelect?.('Reading')}
                                            className="flex items-center justify-between p-1.5 md:p-3 rounded-lg md:rounded-xl hover:bg-slate-800/20 dark:hover:bg-white/5 transition-all text-xs md:text-sm font-bold text-slate-400 cursor-pointer group"
                                        >
                                            <span className="flex items-center gap-1.5 md:gap-2 group-hover:text-[#38BDF8] transition-colors"><PlayCircle size={12} className="text-[#38BDF8] md:w-[14px] md:h-[14px]" /> Reading</span>
                                            <span className="text-white text-xs md:text-sm">{readingCount}</span>
                                        </div>
                                        <div
                                            onClick={() => onStatusSelect?.('To Read')}
                                            className="flex items-center justify-between p-1.5 md:p-3 rounded-lg md:rounded-xl hover:bg-slate-800/20 dark:hover:bg-white/5 transition-all text-xs md:text-sm font-bold text-white cursor-pointer group"
                                        >
                                            <span className="flex items-center gap-1.5 md:gap-2 group-hover:text-[#94A3B8] transition-colors"><Clock size={12} className="text-[#94A3B8] md:w-[14px] md:h-[14px]" /> To Read</span>
                                            <span className="text-white text-xs md:text-sm">{toReadCount}</span>
                                        </div>
                                    </div>
                                </div>

                                {/* Inventory */}
                                <div className="space-y-2 md:space-y-4">
                                    <div className="flex items-center gap-2 md:gap-3 border-b border-white/10 pb-2 md:pb-4">
                                        <InventoryLogo size={16} className="text-primary md:w-5 md:h-5" />
                                        <h3 className="font-extrabold text-white tracking-tight uppercase text-xs">Inventory</h3>
                                    </div>
                                    <div className="flex gap-1.5 md:gap-3">
                                        <div
                                            onClick={() => onStatusSelect?.('On Shelf')}
                                            className="flex-1 p-1.5 md:p-3 rounded-lg md:rounded-xl bg-[#14B8A6]/85 text-center border border-[#14B8A6]/55 cursor-pointer hover:border-[#14B8A6]/70 transition-all font-bold group"
                                        >
                                            <p className="text-[9px] md:text-[10px] uppercase font-black text-white mb-0.5 md:mb-1">Shelf</p>
                                            <p className="text-sm md:text-lg font-black text-white">{onShelfCount}</p>
                                        </div>
                                        <div
                                            onClick={() => onStatusSelect?.('Lent Out')}
                                            className="flex-1 p-1.5 md:p-3 rounded-lg md:rounded-xl bg-[#F59E0B]/85 text-center border border-[#F59E0B]/55 cursor-pointer hover:border-[#F59E0B]/70 transition-all font-bold group"
                                        >
                                            <p className="text-[9px] md:text-[10px] uppercase font-black text-white mb-0.5 md:mb-1">Lent</p>
                                            <p className="text-sm md:text-lg font-black text-white">{lentCount}</p>
                                        </div>
                                        <div
                                            onClick={() => onStatusSelect?.('Lost')}
                                            className="flex-1 p-1.5 md:p-3 rounded-lg md:rounded-xl bg-[#F43F5E]/85 text-center border border-[#F43F5E]/55 cursor-pointer hover:border-[#F43F5E]/70 transition-all font-bold group"
                                        >
                                            <p className="text-[9px] md:text-[10px] uppercase font-black text-white mb-0.5 md:mb-1">Lost</p>
                                            <p className="text-sm md:text-lg font-black text-white">{lostCount}</p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                        </div>
                    </div>
                </section>

                {/* 🔸 Level C – AI Insights (Perfect Minimal Toggle) */}
                <section className="space-y-1 md:space-y-4">
                    <button
                        onClick={() => setShowLevelC(!showLevelC)}
                        className="w-full flex items-center gap-2 md:gap-4 px-1 py-0.5 md:py-2 group transition-all opacity-60 hover:opacity-100"
                    >
                        <div className="flex items-center gap-1 md:gap-2 text-[8px] md:text-[10px] font-black uppercase tracking-[0.12em] md:tracking-[0.2em] text-primary/80">
                            <Sparkles size={10} className="text-primary animate-pulse md:w-[14px] md:h-[14px]" /> Level C Insights
                        </div>
                        <div className="h-[1px] bg-slate-300 dark:bg-white/10 flex-1" />
                        <div className="text-slate-400 group-hover:text-primary transition-colors">
                            {showLevelC ? <ChevronUp size={12} className="md:w-4 md:h-4" /> : <ChevronDown size={12} className="md:w-4 md:h-4" />}
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
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-4 pt-0.5 md:pt-2">
                                    <div className="p-2.5 md:p-5 rounded-lg md:rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 backdrop-blur-xl flex flex-col gap-1 md:gap-2 shadow-lg min-h-[70px] md:min-h-0">
                                        <p className="text-[9px] md:text-[11px] font-black uppercase text-slate-300/80 flex items-center gap-1 md:gap-2">
                                            <TrendingUp size={9} className="text-[#F63049] md:w-3 md:h-3" /> Momentum
                                        </p>
                                        <p className="text-lg md:text-2xl font-black text-white leading-none">
                                            {last7Delta > 0 ? `+${last7Delta}` : last7Delta}
                                        </p>
                                    </div>
                                    <div className="p-2.5 md:p-5 rounded-lg md:rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 backdrop-blur-xl flex flex-col gap-1 md:gap-2 shadow-lg min-h-[70px] md:min-h-0">
                                        <p className="text-[9px] md:text-[11px] font-black uppercase text-slate-300/80 flex items-center gap-1 md:gap-2">
                                            <GitBranch size={9} className="text-blue-500 md:w-3 md:h-3" /> Bridges
                                        </p>
                                        <p className="text-lg md:text-2xl font-black text-white leading-none">{conceptBridgesLast7}</p>
                                    </div>
                                    <div className="p-2.5 md:p-5 rounded-lg md:rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 backdrop-blur-xl flex flex-col gap-1 md:gap-2 shadow-lg min-h-[70px] md:min-h-0">
                                        <p className="text-[9px] md:text-[11px] font-black uppercase text-slate-300/80 flex items-center gap-1 md:gap-2">
                                            <FocusLogo size={9} className="text-[#A5C89E] md:w-3 md:h-3" /> Focus
                                        </p>
                                        <p className="text-sm md:text-lg font-black text-white truncate leading-none">{topTag || '—'}</p>
                                    </div>
                                    <div className="p-2.5 md:p-5 rounded-lg md:rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 backdrop-blur-xl flex flex-col gap-1 md:gap-2 shadow-lg min-h-[70px] md:min-h-0">
                                        <p className="text-[9px] md:text-[11px] font-black uppercase text-slate-300/80 flex items-center gap-1 md:gap-2">
                                            <Search size={9} className="text-indigo-500 md:w-3 md:h-3" /> Discovery
                                        </p>
                                        <p className="text-lg md:text-2xl font-black text-white leading-none">{unexploredCount}</p>
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



