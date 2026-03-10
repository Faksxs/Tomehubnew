import React, { useMemo, useState } from 'react';
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
    Zap,
    LayoutGrid,
    Archive,
    Menu,
    Film
} from 'lucide-react';
import { LibraryItem } from '../../types';
import { CATEGORIES, MIN_CATEGORY_BOOKS_VISIBLE } from '../CategorySelector';
import {
    KnowledgeBaseLogo,
    HighlightsLogo,
    BooksLogo,
    ArticlesLogo,
    NotesLogo,
    SystemDistributionLogo,
    ProgressLogo,
    FocusLogo,
    CinemaLogo
} from '../ui/FeatureLogos';

interface KnowledgeDashboardProps {
    items: LibraryItem[];
    userId: string;
    onCategorySelect?: (category: string) => void;
    onStatusSelect?: (status: string) => void;
    onNavigateToTab?: (tab: string) => void;
    onNavigateToTabWithStatus?: (tab: string, status: string) => void;
    onMobileMenuClick?: () => void;
}

const CountUp = ({ value, prefix = '', suffix = '' }: { value: number | string, prefix?: string, suffix?: string }) => {
    const numericValue = typeof value === 'string' ? Number(value) : value;
    if (typeof value === 'string' && !Number.isFinite(numericValue)) {
        return <span>{`${prefix}${value}${suffix}`}</span>;
    }
    const stableValue = Number.isFinite(numericValue)
        ? (Number.isInteger(numericValue) ? String(Math.round(numericValue)) : numericValue.toFixed(1))
        : '0';
    return <span>{`${prefix}${stableValue}${suffix}`}</span>;
};

export const KnowledgeDashboard: React.FC<KnowledgeDashboardProps> = ({
    items,
    userId,
    onCategorySelect,
    onStatusSelect,
    onNavigateToTab,
    onNavigateToTabWithStatus,
    onMobileMenuClick
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
    const baseStats = useMemo(() => {
        const books: LibraryItem[] = [];
        const cinema: LibraryItem[] = [];
        const articles: LibraryItem[] = [];
        const personalNotes: LibraryItem[] = [];
        const allHighlights = [];
        let finishedCount = 0;
        let readingCount = 0;
        let toReadCount = 0;
        let cinemaWatchlistCount = 0;
        let cinemaWatchingCount = 0;
        let cinemaWatchedCount = 0;

        items.forEach((item) => {
            if (item.type === 'BOOK') books.push(item);
            if (item.type === 'MOVIE' || item.type === 'SERIES') cinema.push(item);
            if (item.type === 'ARTICLE') articles.push(item);
            if (item.type === 'PERSONAL_NOTE') personalNotes.push(item);
            allHighlights.push(...(item.highlights || []));

            if (item.type !== 'PERSONAL_NOTE' && item.type !== 'MOVIE' && item.type !== 'SERIES') {
                if (item.readingStatus === 'Finished') finishedCount += 1;
                if (item.readingStatus === 'Reading') readingCount += 1;
                if (item.readingStatus === 'To Read') toReadCount += 1;
            }

            if (item.type === 'MOVIE' || item.type === 'SERIES') {
                if (item.readingStatus === 'To Read') cinemaWatchlistCount += 1;
                if (item.readingStatus === 'Reading') cinemaWatchingCount += 1;
                if (item.readingStatus === 'Finished') cinemaWatchedCount += 1;
            }
        });

        return {
            books,
            cinema,
            articles,
            personalNotes,
            allHighlights,
            finishedCount,
            readingCount,
            toReadCount,
            cinemaWatchlistCount,
            cinemaWatchingCount,
            cinemaWatchedCount,
        };
    }, [items]);

    const {
        books,
        cinema,
        articles,
        personalNotes,
        allHighlights,
        finishedCount,
        readingCount,
        toReadCount,
        cinemaWatchlistCount,
        cinemaWatchingCount,
        cinemaWatchedCount,
    } = baseStats;

    const statsA = [
        { label: 'All Notes', value: allHighlights.length, icon: HighlightsLogo, tab: 'NOTES' },
        { label: 'Total Books', value: books.length, icon: BooksLogo, tab: 'BOOK' },
        { label: 'Cinema', value: cinema.length, icon: CinemaLogo, tab: 'MOVIE' },
        { label: 'Personal Notes', value: personalNotes.length, icon: NotesLogo, tab: 'PERSONAL_NOTE' },
        { label: 'Articles', value: articles.length, icon: ArticlesLogo, tab: 'ARTICLE' },
    ];

    const advancedStats = useMemo(() => {
        const now = Date.now();
        const thirtyDaysMs = 30 * 24 * 60 * 60 * 1000;
        const ninetyDaysMs = 90 * 24 * 60 * 60 * 1000;

        // 1. Pulse (Activity in last 30 days)
        const itemsWithTime = items.map(item => ({
            item,
            addedAtMs: normalizeAddedAt(item.addedAt),
            lastHighlightMs: Math.max(...(item.highlights || []).map(h => normalizeAddedAt(h.createdAt)), 0)
        }));
        const recentActivity = itemsWithTime.filter(i => i.addedAtMs >= now - thirtyDaysMs || i.lastHighlightMs >= now - thirtyDaysMs).length;
        const recentHighlights = items.flatMap(i => i.highlights || []).filter(h => normalizeAddedAt(h.createdAt) >= now - thirtyDaysMs).length;
        const pulseValue = recentActivity + recentHighlights;

        // 2. T-Profile (Focus vs Orphans)
        const tagMap = new Map<string, number>();
        items.forEach(item => (item.tags || []).forEach(t => {
            const k = normalizeTextKey(t);
            tagMap.set(k, (tagMap.get(k) || 0) + 1);
        }));
        const frequencies = Array.from(tagMap.values()).sort((a, b) => b - a);
        const top10PercentCount = Math.max(1, Math.ceil(frequencies.length * 0.1));
        const topSum = frequencies.slice(0, top10PercentCount).reduce((a, b) => a + b, 0);
        const orphanCount = frequencies.filter(f => f <= 2).length;
        const totalTagUses = frequencies.reduce((a, b) => a + b, 0);
        const tScore = totalTagUses > 0 ? (topSum / Math.max(1, orphanCount)).toFixed(1) : '0.0';

        // 3. Core Nexus (Co-occurrence & Density)
        const pairs = new Map<string, number>();
        items.forEach(item => {
            const tags = Array.from(new Set((item.tags || []).map(normalizeTextKey)));
            for (let i = 0; i < tags.length; i++) {
                for (let j = i + 1; j < tags.length; j++) {
                    const pair = [tags[i], tags[j]].sort().join(' & ');
                    pairs.set(pair, (pairs.get(pair) || 0) + 1);
                }
            }
        });
        let strongestNexus = '-';
        let maxBond = 0;
        pairs.forEach((count, pair) => {
            if (count > maxBond) {
                maxBond = count;
                strongestNexus = pair;
            }
        });
        const density = frequencies.length > 0 ? (items.length / frequencies.length).toFixed(1) : '0.0';

        // 4. Rust Index (Inactivity)
        const inactiveItems = itemsWithTime.filter(i =>
            i.addedAtMs < now - ninetyDaysMs &&
            i.lastHighlightMs < now - ninetyDaysMs &&
            i.item.type !== 'PERSONAL_NOTE'
        ).length;
        const totalReadable = items.filter(i => i.type !== 'PERSONAL_NOTE').length;
        const rustPercentage = totalReadable > 0 ? Math.round((inactiveItems / totalReadable) * 100) : 0;

        // 5. Intellect Engine (AI Readiness)
        const ingestedCount = items.filter(i => i.isIngested).length;
        const ingestRatio = totalReadable > 0 ? Math.round((ingestedCount / totalReadable) * 100) : 0;

        // 6. Discovery (Unexplored)
        const unexplored = items.filter(i => i.type !== 'PERSONAL_NOTE' && (i.highlights?.length || 0) === 0).length;

        return {
            pulse: pulseValue,
            tScore,
            orphanCount,
            nexus: strongestNexus,
            density,
            rust: rustPercentage,
            activeNodes: totalReadable - inactiveItems,
            ingestRatio,
            ingestedCount,
            totalReadable,
            unexplored
        };
    }, [items]);

    // --- DATA PROCESSING (LEVEL B - CATEGORIES) ---
    const categoryLookup = useMemo(() => new Map<string, string>(
        CATEGORIES.map(category => [normalizeTextKey(category), category])
    ), []);

    const categoryCounts = useMemo(() => {
        const counts = new Map<string, number>();
        books.forEach(book => {
            (book.tags || []).forEach(tag => {
                const canonical = categoryLookup.get(normalizeTextKey(tag));
                if (!canonical) return;
                counts.set(canonical, (counts.get(canonical) || 0) + 1);
            });
        });
        return counts;
    }, [books, categoryLookup]);

    return (
        <div className="min-h-full w-full space-y-5 md:space-y-8 animate-in fade-in duration-700 relative">

            {/* Header (Perfect Size) */}
            <div className="flex flex-row items-center justify-between gap-3 md:gap-5 relative z-20">
                {/* Mobile Menu Trigger (Left) */}
                <div className="lg:hidden">
                    <button
                        onClick={onMobileMenuClick}
                        className="p-1 -ml-1 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 rounded-lg transition-colors shrink-0"
                    >
                        <Menu size={18} className="md:w-6 md:h-6" />
                    </button>
                </div>

                {/* Dashboard Title */}
                <div className="space-y-1">
                    <h2 className="text-xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5 md:gap-3 flex-row-reverse md:flex-row">
                        <div className="relative group">
                            <div className="relative p-2 md:p-2.5 bg-primary/10 dark:bg-primary/20 rounded-xl border border-primary/30 dark:border-primary/40 shadow-[0_0_15px_rgba(204,86,30,0.2)]">
                                <KnowledgeBaseLogo size={28} className="text-primary dark:text-primary md:w-8 md:h-8" />
                            </div>
                        </div>
                        Dashboard
                    </h2>
                </div>
            </div>

            <div className="max-w-6xl mx-auto space-y-5 md:space-y-8 relative z-20">



                {/* Level A - Core Assets */}
                <section className="space-y-2 md:space-y-4">
                    <div className="flex items-center gap-1.5 md:gap-2 px-1 text-xs md:text-sm font-bold uppercase tracking-[0.15em] md:tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        <Activity size={11} className="text-primary/60 md:w-3 md:h-3" /> Level A - Core Stats
                    </div>
                    <div className="grid grid-cols-2 min-[560px]:grid-cols-3 lg:grid-cols-6 gap-2.5 md:gap-4">
                        {statsA.map((stat) => (
                            <div
                                key={stat.label}
                                onClick={() => onNavigateToTab?.(stat.tab)}
                                className="
                                    relative overflow-hidden
                                    group cursor-pointer
                                    rounded-2xl border border-slate-800/20 dark:border-white/10
                                    bg-card dark:bg-slate-900/50
                                    shadow-lg lg:shadow-md
                                    hover:shadow-xl hover:border-primary/40 dark:hover:border-primary/40
                                    transition-colors duration-200
                                    flex flex-col items-center p-2 md:p-3 gap-1 md:gap-3
                                "
                            >
                                <div className="flex items-center justify-center gap-1.5 md:gap-2.5 w-full">
                                    <div className="relative shrink-0">
                                        <div className="relative p-1 md:p-1.5 bg-orange-500/5 dark:bg-orange-500/10 rounded-lg md:rounded-xl border border-orange-500/10 dark:border-orange-500/20 transition-colors group-hover:border-orange-500/40">
                                            <stat.icon className="w-3 h-3 md:w-4 md:h-4 text-[#CC561E] dark:text-[#f3a47b]" />
                                        </div>
                                    </div>
                                    <div className="text-[7.5px] md:text-[10px] font-bold uppercase tracking-[0.05em] md:tracking-widest text-slate-400 group-hover:text-slate-300 transition-colors leading-tight">
                                        {stat.label}
                                    </div>
                                </div>
                                <div className="w-full text-center mt-auto">
                                    <div className="text-base md:text-2xl font-black tracking-tight text-white leading-none">
                                        <CountUp value={stat.value} />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Level B - Structure */}
                <section className="space-y-1 md:space-y-4">
                    <div className="flex items-center gap-1.5 md:gap-2 px-1 text-xs md:text-sm font-bold uppercase tracking-[0.15em] md:tracking-[0.2em] text-slate-500 dark:text-slate-400">
                        <PieChart size={12} className="text-primary/60" /> Level B - Structure
                    </div>

                    <div className="
                rounded-3xl md:rounded-[2rem] border border-slate-800/10 dark:border-white/10
                bg-card dark:bg-slate-900/50
                shadow-xl
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
                                        if (count < MIN_CATEGORY_BOOKS_VISIBLE) return null;
                                        const percentage = books.length > 0 ? (count / books.length) * 100 : 0;
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
                                                    <div
                                                        style={{ width: `${percentage}%` }}
                                                        className="h-full bg-primary group-hover:bg-primary transition-colors"
                                                    />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Right Column (Progress & Cinema) */}
                            <div className="md:col-span-4 flex flex-col gap-3 md:gap-8">
                                <div className="space-y-2 md:space-y-4">
                                    <div className="flex items-center gap-2 md:gap-3 border-b border-white/10 pb-2 md:pb-4">
                                        <ProgressLogo size={16} className="text-primary md:w-5 md:h-5" />
                                        <h3 className="font-extrabold text-white tracking-tight uppercase text-sm">Progress</h3>
                                    </div>
                                    <div className="space-y-1">
                                        <div onClick={() => onStatusSelect?.('Finished')} className="flex items-center justify-between p-1.5 md:p-3 rounded-lg md:rounded-xl hover:bg-slate-800/20 dark:hover:bg-white/5 transition-all text-xs md:text-sm font-bold text-slate-400 cursor-pointer group">
                                            <span className="flex items-center gap-1.5 md:gap-2 group-hover:text-[#22C55E] transition-colors"><CheckCircle size={12} className="text-[#22C55E] md:w-[14px] md:h-[14px]" /> Finished</span>
                                            <span className="text-white text-xs md:text-sm">{finishedCount}</span>
                                        </div>
                                        <div onClick={() => onStatusSelect?.('Reading')} className="flex items-center justify-between p-1.5 md:p-3 rounded-lg md:rounded-xl hover:bg-slate-800/20 dark:hover:bg-white/5 transition-all text-xs md:text-sm font-bold text-slate-400 cursor-pointer group">
                                            <span className="flex items-center gap-1.5 md:gap-2 group-hover:text-[#38BDF8] transition-colors"><PlayCircle size={12} className="text-[#38BDF8] md:w-[14px] md:h-[14px]" /> Reading</span>
                                            <span className="text-white text-xs md:text-sm">{readingCount}</span>
                                        </div>
                                        <div onClick={() => onStatusSelect?.('To Read')} className="flex items-center justify-between p-1.5 md:p-3 rounded-lg md:rounded-xl hover:bg-slate-800/20 dark:hover:bg-white/5 transition-all text-xs md:text-sm font-bold text-white cursor-pointer group">
                                            <span className="flex items-center gap-1.5 md:gap-2 group-hover:text-[#94A3B8] transition-colors"><Clock size={12} className="text-[#94A3B8] md:w-[14px] md:h-[14px]" /> To Read</span>
                                            <span className="text-white text-xs md:text-sm">{toReadCount}</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="space-y-2 md:space-y-4">
                                    <div className="flex items-center gap-2 md:gap-3 border-b border-white/10 pb-2 md:pb-4">
                                        <Film size={16} className="text-primary md:w-5 md:h-5" />
                                        <h3 className="font-extrabold text-white tracking-tight uppercase text-xs">Cinema</h3>
                                    </div>
                                    <div className="flex gap-1.5 md:gap-3">
                                        <div
                                            onClick={() => {
                                                if (onNavigateToTabWithStatus) {
                                                    onNavigateToTabWithStatus('MOVIE', 'To Read');
                                                    return;
                                                }
                                                onNavigateToTab?.('MOVIE');
                                                onStatusSelect?.('To Read');
                                            }}
                                            className="flex-1 p-1.5 md:p-3 rounded-lg md:rounded-xl bg-slate-800/80 text-center border border-white/10 cursor-pointer hover:border-primary/50 transition-all font-bold group"
                                        >
                                            <p className="text-[9px] md:text-[10px] uppercase font-black text-slate-400 mb-0.5 md:mb-1 group-hover:text-primary transition-colors">Watchlist</p>
                                            <p className="text-sm md:text-lg font-black text-white"><CountUp value={cinemaWatchlistCount} /></p>
                                        </div>
                                        <div
                                            onClick={() => {
                                                if (onNavigateToTabWithStatus) {
                                                    onNavigateToTabWithStatus('MOVIE', 'Reading');
                                                    return;
                                                }
                                                onNavigateToTab?.('MOVIE');
                                                onStatusSelect?.('Reading');
                                            }}
                                            className="flex-1 p-1.5 md:p-3 rounded-lg md:rounded-xl bg-slate-800/80 text-center border border-white/10 cursor-pointer hover:border-primary/50 transition-all font-bold group"
                                        >
                                            <p className="text-[9px] md:text-[10px] uppercase font-black text-slate-400 mb-0.5 md:mb-1 group-hover:text-primary transition-colors">Watching</p>
                                            <p className="text-sm md:text-lg font-black text-white"><CountUp value={cinemaWatchingCount} /></p>
                                        </div>
                                        <div
                                            onClick={() => {
                                                if (onNavigateToTabWithStatus) {
                                                    onNavigateToTabWithStatus('MOVIE', 'Finished');
                                                    return;
                                                }
                                                onNavigateToTab?.('MOVIE');
                                                onStatusSelect?.('Finished');
                                            }}
                                            className="flex-1 p-1.5 md:p-3 rounded-lg md:rounded-xl bg-slate-800/80 text-center border border-white/10 cursor-pointer hover:border-primary/50 transition-all font-bold group"
                                        >
                                            <p className="text-[9px] md:text-[10px] uppercase font-black text-slate-400 mb-0.5 md:mb-1 group-hover:text-primary transition-colors">Watched</p>
                                            <p className="text-sm md:text-lg font-black text-white"><CountUp value={cinemaWatchedCount} /></p>
                                        </div>
                                    </div>
                                </div>

                            </div>
                        </div>
                    </div>
                </section>

                {/* Level C - Deep Analytics (6 Widget Redesign) */}
                <section className="space-y-1 md:space-y-4">
                    <button
                        onClick={() => setShowLevelC(!showLevelC)}
                        className="w-full flex items-center gap-2 md:gap-4 px-1 py-0.5 md:py-2 group transition-all opacity-60 hover:opacity-100"
                    >
                        <div className="flex items-center gap-1 md:gap-2 text-xs md:text-sm font-black uppercase tracking-[0.12em] md:tracking-[0.18em] text-primary/80">
                            <Sparkles size={10} className="text-primary animate-pulse md:w-[14px] md:h-[14px]" /> Level C Deep Analytics
                        </div>
                        <div className="h-[1px] bg-slate-300 dark:bg-white/10 flex-1" />
                        <div className="text-slate-400 group-hover:text-primary transition-colors">
                            {showLevelC ? <ChevronUp size={12} className="md:w-4 md:h-4" /> : <ChevronDown size={12} className="md:w-4 md:h-4" />}
                        </div>
                    </button>

                    {showLevelC && (
                        <div
                            className="overflow-hidden animate-in fade-in duration-200"
                            onClick={() => onNavigateToTab?.('INSIGHTS')}
                        >
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 md:gap-4 pt-0.5 md:pt-2">

                                {/* 1. Pulse */}
                                <div className="p-3 md:p-5 rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 flex flex-col gap-1.5 md:gap-3 shadow-lg hover:border-primary/40 transition-colors cursor-pointer group">
                                    <p className="text-[9px] md:text-[10px] font-black uppercase text-slate-400/80 flex items-center gap-1.5">
                                        <Activity size={10} className="text-[#FF4D4D]" /> Pulse
                                    </p>
                                    <div className="flex flex-col">
                                        <p className="text-xl md:text-2xl font-black text-white"><CountUp prefix="+" value={advancedStats.pulse} /></p>
                                        <p className="text-[8px] md:text-[9px] font-bold text-slate-500 uppercase">30 Day Activity</p>
                                    </div>
                                </div>

                                {/* 2. T-Profile */}
                                <div className="p-3 md:p-5 rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 flex flex-col gap-1.5 md:gap-3 shadow-lg hover:border-primary/40 transition-colors cursor-pointer group">
                                    <p className="text-[9px] md:text-[10px] font-black uppercase text-slate-400/80 flex items-center gap-1.5">
                                        <TrendingUp size={10} className="text-[#F63049]" /> T-Profile
                                    </p>
                                    <div className="flex flex-col">
                                        <p className="text-xl md:text-2xl font-black text-white"><CountUp value={advancedStats.tScore} /></p>
                                        <p className="text-[8px] md:text-[9px] font-bold text-slate-500 uppercase">{advancedStats.orphanCount} Orphans</p>
                                    </div>
                                </div>

                                {/* 3. Forgetting Curve (Rust) */}
                                <div className="p-3 md:p-5 rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 flex flex-col gap-1.5 md:gap-3 shadow-lg hover:border-primary/40 transition-colors cursor-pointer group">
                                    <p className="text-[9px] md:text-[10px] font-black uppercase text-slate-400/80 flex items-center gap-1.5">
                                        <Zap size={10} className="text-orange-400" /> Rust Index
                                    </p>
                                    <div className="flex flex-col">
                                        <p className="text-xl md:text-2xl font-black text-white"><CountUp value={advancedStats.rust} suffix="%" /></p>
                                        <p className="text-[8px] md:text-[9px] font-bold text-slate-500 uppercase">{advancedStats.activeNodes} Active Nodes</p>
                                    </div>
                                </div>

                                {/* 4. Intellect Engine */}
                                <div className="p-3 md:p-5 rounded-2xl border border-slate-800/20 dark:border-white/10 bg-card dark:bg-slate-900/50 flex flex-col gap-1.5 md:gap-3 shadow-lg hover:border-primary/40 transition-colors cursor-pointer group">
                                    <p className="text-[9px] md:text-[10px] font-black uppercase text-slate-400/80 flex items-center gap-1.5">
                                        <Sparkles size={10} className="text-primary" /> Intellect
                                    </p>
                                    <div className="flex flex-col">
                                        <p className="text-xl md:text-2xl font-black text-white"><CountUp value={advancedStats.ingestRatio} suffix="%" /></p>
                                        <p className="text-[8px] md:text-[9px] font-bold text-slate-500 uppercase">{advancedStats.ingestedCount} Ingested</p>
                                    </div>
                                </div>

                            </div>
                            <div className="mt-3 text-center">
                                <p className="text-[9px] md:text-[10px] font-bold text-slate-500 uppercase tracking-widest animate-pulse">Click any card for full network analysis</p>
                            </div>
                        </div>
                    )}
                </section >
            </div >

        </div >
    );
};
