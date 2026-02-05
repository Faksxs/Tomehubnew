
import React from 'react';
import { LibraryItem } from '../types';
import {
    Activity,
    Archive,
    Book,
    BookOpen,
    CheckCircle,
    ChevronDown,
    Clock,
    FileText,
    GitBranch,
    Globe,
    Layers,
    Network,
    PenTool,
    PieChart,
    Quote,
    Sparkles,
    TrendingUp
} from 'lucide-react';
import { CATEGORIES } from './CategorySelector';

interface StatisticsViewProps {
    items: LibraryItem[];
    onCategorySelect?: (category: string) => void;
}

export const StatisticsView: React.FC<StatisticsViewProps> = ({ items, onCategorySelect }) => {
    const books = items.filter(i => i.type === 'BOOK');
    const articles = items.filter(i => i.type === 'ARTICLE');
    const websites = items.filter(i => i.type === 'WEBSITE');
    const personalNotes = items.filter(i => i.type === 'PERSONAL_NOTE');

    const allHighlights = items.flatMap(i => i.highlights || []);
    const quotes = allHighlights.filter(h => h.type === 'highlight' || !h.type); // Default to highlight for legacy items

    // Reading Status (Books, Articles, Websites) - exclude Personal Notes
    const readableItems = items.filter(i => i.type !== 'PERSONAL_NOTE');
    const totalReadable = readableItems.length;

    // Status Counts
    const finishedCount = readableItems.filter(i => i.readingStatus === 'Finished').length;
    const readingCount = readableItems.filter(i => i.readingStatus === 'Reading').length;
    const toReadCount = readableItems.filter(i => i.readingStatus === 'To Read').length;

    // Inventory Counts (BOOKS ONLY)
    const lentCount = books.filter(i => i.status === 'Lent Out').length;
    const lostCount = books.filter(i => i.status === 'Lost').length;
    const onShelfCount = books.filter(i => i.status === 'On Shelf').length;

    // Knowledge status (TomeHub-specific heuristics)
    const activeKnowledge = readableItems.filter(i => (i.highlights?.length || 0) > 0).length;
    const dormantKnowledge = Math.max(totalReadable - activeKnowledge, 0);
    const dormantRate = totalReadable ? dormantKnowledge / totalReadable : 0;

    // AI-inspired signals (lightweight heuristics for now)
    const now = Date.now();
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    const addedLast7 = items.filter(i => i.addedAt >= now - weekMs).length;
    const addedPrev7 = items.filter(i => i.addedAt >= now - (2 * weekMs) && i.addedAt < now - weekMs).length;
    const last7Delta = addedLast7 - addedPrev7;
    const last7DeltaLabel = last7Delta === 0 ? '±0' : last7Delta > 0 ? `+${last7Delta}` : `${last7Delta}`;

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

    const PrimaryStat = ({ label, value, icon: Icon }: { label: string; value: number; icon: any }) => (
        <div className="flex items-center gap-3 px-3 py-2 md:px-4 md:py-3">
            <div className="rounded-full bg-muted/60 p-1.5 text-muted-foreground">
                <Icon size={16} />
            </div>
            <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground truncate">{label}</p>
                <p className="text-xl md:text-2xl font-semibold text-foreground leading-tight">{value}</p>
            </div>
        </div>
    );

    return (
        <div className="space-y-6 pb-20 animate-in fade-in slide-in-from-bottom-4">
            {/* Level A - Always visible */}
            <section className="rounded-2xl border border-border/60 bg-card/40 p-4 md:p-6">
                <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Level A • Always visible</p>
                        <div className="mt-2 flex items-center gap-2">
                            <Layers size={18} className="text-primary" />
                            <h2 className="text-lg md:text-2xl font-semibold text-foreground">TomeHub Atlas</h2>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                            Knowledge OS snapshot. Compact, hierarchical, and TomeHub-native.
                        </p>
                    </div>
                    <div className="text-xs text-muted-foreground">Total items: {items.length}</div>
                </div>

                <div className="mt-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-border/40">
                    <PrimaryStat label="Total Books" value={books.length} icon={Book} />
                    <PrimaryStat label="Articles" value={articles.length} icon={FileText} />
                    <PrimaryStat label="Websites" value={websites.length} icon={Globe} />
                    <PrimaryStat label="Notes" value={personalNotes.length} icon={PenTool} />
                    <PrimaryStat label="Highlights" value={allHighlights.length} icon={Quote} />
                </div>
            </section>

            {/* Level B - Contextual */}
            <details className="group rounded-2xl border border-border/60 bg-card/40">
                <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 md:px-6 md:py-4">
                    <div>
                        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Level B • Contextual</p>
                        <div className="mt-1 flex items-center gap-2">
                            <PieChart size={16} className="text-primary" />
                            <span className="text-base font-semibold text-foreground">Context Layer</span>
                        </div>
                    </div>
                    <ChevronDown size={16} className="text-muted-foreground transition-transform group-open:rotate-180" />
                </summary>

                <div className="border-t border-border/40 px-4 py-4 md:px-6 md:py-6 space-y-6">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {/* Category Distribution */}
                        <div className="lg:col-span-2">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                                    <Archive size={16} className="text-muted-foreground" />
                                    Category Distribution
                                </h3>
                                <span className="text-xs text-muted-foreground">{books.length} Books</span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {CATEGORIES.map(category => {
                                    const count = books.filter(b => b.tags?.includes(category)).length;
                                    const percentage = books.length > 0 ? (count / books.length) * 100 : 0;

                                    return (
                                        <button
                                            key={category}
                                            type="button"
                                            className="space-y-2 group text-left focus:outline-none"
                                            onClick={() => onCategorySelect?.(category)}
                                        >
                                            <div className="flex justify-between items-center text-sm">
                                                <span className="font-medium text-foreground group-hover:text-primary transition-colors">
                                                    {category}
                                                </span>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-muted-foreground text-xs">{percentage.toFixed(0)}%</span>
                                                    <span className="font-semibold text-foreground">{count}</span>
                                                </div>
                                            </div>
                                            <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                                                <div
                                                    className="bg-primary h-full rounded-full transition-all duration-1000 ease-out opacity-80 group-hover:opacity-100"
                                                    style={{ width: `${percentage}%` }}
                                                ></div>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>

                            {books.length === 0 && (
                                <div className="py-8 text-center">
                                    <p className="text-muted-foreground text-sm italic">No books in library to categorize.</p>
                                </div>
                            )}
                        </div>

                        {/* Reading + Inventory + Knowledge Status */}
                        <div className="space-y-6">
                            <div>
                                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                                    <BookOpen size={16} className="text-muted-foreground" />
                                    Reading Progress
                                </h3>
                                <p className="text-xs text-muted-foreground mt-1">Books, Articles, Websites</p>

                                <div className="space-y-4 mt-4">
                                    <div>
                                        <div className="flex justify-between text-sm mb-2">
                                            <span className="flex items-center gap-2 text-muted-foreground"><CheckCircle size={14} /> Finished</span>
                                            <span className="font-medium text-foreground">{finishedCount}</span>
                                        </div>
                                        <div className="w-full bg-muted rounded-full h-2">
                                            <div className="bg-primary h-2 rounded-full transition-all duration-1000" style={{ width: `${totalReadable ? (finishedCount / totalReadable) * 100 : 0}%` }}></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div className="flex justify-between text-sm mb-2">
                                            <span className="flex items-center gap-2 text-muted-foreground"><BookOpen size={14} /> Reading</span>
                                            <span className="font-medium text-foreground">{readingCount}</span>
                                        </div>
                                        <div className="w-full bg-muted rounded-full h-2">
                                            <div className="bg-accent h-2 rounded-full transition-all duration-1000" style={{ width: `${totalReadable ? (readingCount / totalReadable) * 100 : 0}%` }}></div>
                                        </div>
                                    </div>
                                    <div>
                                        <div className="flex justify-between text-sm mb-2">
                                            <span className="flex items-center gap-2 text-muted-foreground"><Clock size={14} /> To Read</span>
                                            <span className="font-medium text-foreground">{toReadCount}</span>
                                        </div>
                                        <div className="w-full bg-muted rounded-full h-2">
                                            <div className="bg-muted-foreground/50 h-2 rounded-full transition-all duration-1000" style={{ width: `${totalReadable ? (toReadCount / totalReadable) * 100 : 0}%` }}></div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                                        <Archive size={16} className="text-muted-foreground" />
                                        Books Inventory
                                    </h3>
                                    <ul className="mt-2 divide-y divide-border/40 text-sm">
                                        <li className="flex items-center justify-between py-2">
                                            <span className="text-muted-foreground">On Shelf</span>
                                            <span className="font-semibold text-foreground">{onShelfCount}</span>
                                        </li>
                                        <li className="flex items-center justify-between py-2">
                                            <span className="text-muted-foreground">Lent Out</span>
                                            <span className="font-semibold text-foreground">{lentCount}</span>
                                        </li>
                                        <li className="flex items-center justify-between py-2">
                                            <span className="text-muted-foreground">Lost</span>
                                            <span className="font-semibold text-foreground">{lostCount}</span>
                                        </li>
                                    </ul>
                                </div>

                                <div>
                                    <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                                        <Activity size={16} className="text-muted-foreground" />
                                        Knowledge Status
                                    </h3>
                                    <ul className="mt-2 divide-y divide-border/40 text-sm">
                                        <li className="flex items-center justify-between py-2">
                                            <span className="text-muted-foreground">Active</span>
                                            <span className="font-semibold text-foreground">{activeKnowledge}</span>
                                        </li>
                                        <li className="flex items-center justify-between py-2">
                                            <span className="text-muted-foreground">Dormant</span>
                                            <span className="font-semibold text-foreground">{dormantRate.toFixed(2)}</span>
                                        </li>
                                    </ul>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        Active = items with highlights. Dormant shows the ratio of untouched knowledge.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </details>

            {/* Level C - AI-assisted */}
            <details className="group rounded-2xl border border-border/60 bg-card/40">
                <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 md:px-6 md:py-4">
                    <div>
                        <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Level C • AI-assisted</p>
                        <div className="mt-1 flex items-center gap-2">
                            <Sparkles size={16} className="text-primary" />
                            <span className="text-base font-semibold text-foreground">AI Lens</span>
                        </div>
                    </div>
                    <ChevronDown size={16} className="text-muted-foreground transition-transform group-open:rotate-180" />
                </summary>

                <div className="border-t border-border/40 px-4 py-4 md:px-6 md:py-6 space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="flex items-start justify-between gap-4 rounded-xl border border-border/50 bg-background/60 px-4 py-3">
                            <div>
                                <p className="text-xs text-muted-foreground flex items-center gap-2">
                                    <TrendingUp size={14} /> Last 7 Days Delta
                                </p>
                                <p className={`text-2xl font-semibold ${last7Delta > 0 ? 'text-emerald-600' : last7Delta < 0 ? 'text-rose-600' : 'text-foreground'}`}>
                                    {last7DeltaLabel}
                                </p>
                                <p className="text-xs text-muted-foreground">{addedLast7} new items in the last week</p>
                            </div>
                        </div>

                        <div className="flex items-start justify-between gap-4 rounded-xl border border-border/50 bg-background/60 px-4 py-3">
                            <div>
                                <p className="text-xs text-muted-foreground flex items-center gap-2">
                                    <GitBranch size={14} /> New Concept Bridges
                                </p>
                                <p className="text-2xl font-semibold text-foreground">{conceptBridgesLast7}</p>
                                <p className="text-xs text-muted-foreground">Estimated from multi-tag items</p>
                            </div>
                        </div>

                        <div className="flex items-start justify-between gap-4 rounded-xl border border-border/50 bg-background/60 px-4 py-3">
                            <div>
                                <p className="text-xs text-muted-foreground flex items-center gap-2">
                                    <Activity size={14} /> Most Active Concept
                                </p>
                                <p className="text-lg font-semibold text-foreground">{topTag || '—'}</p>
                                <p className="text-xs text-muted-foreground">{topTag ? `${topTagCount} items tagged` : 'No tags yet'}</p>
                            </div>
                        </div>

                        <div className="flex items-start justify-between gap-4 rounded-xl border border-border/50 bg-background/60 px-4 py-3">
                            <div>
                                <p className="text-xs text-muted-foreground flex items-center gap-2">
                                    <Network size={14} /> Unexplored
                                </p>
                                <p className="text-2xl font-semibold text-foreground">{unexploredCount}</p>
                                <p className="text-xs text-muted-foreground">Items without highlights</p>
                            </div>
                        </div>
                    </div>

                    <p className="text-xs text-muted-foreground">
                        AI Lens uses lightweight heuristics for now. We can replace these with real AI signals step by step.
                    </p>
                </div>
            </details>
        </div>
    );
};
