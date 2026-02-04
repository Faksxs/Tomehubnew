
import React from 'react';
import { LibraryItem } from '../types';
import { Book, FileText, Globe, PenTool, Quote, StickyNote, PieChart, CheckCircle, Clock, BookOpen, Archive, AlertTriangle } from 'lucide-react';
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

    const allHighlights = items.flatMap(i => i.highlights);
    const quotes = allHighlights.filter(h => h.type === 'highlight' || !h.type); // Default to highlight for legacy items
    const attachedNotes = allHighlights.filter(h => h.type === 'note');

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

    const StatCard = ({ title, count, icon: Icon, color, subtext }: any) => (
        <div className="bg-white p-3 md:p-5 rounded-xl border border-slate-200 shadow-sm flex items-center gap-2 md:gap-4 hover:shadow-md transition-shadow">
            <div className={`p-2 md:p-3.5 rounded-full ${color} bg-opacity-10 shrink-0`}>
                <Icon size={20} className={`${color.replace('bg-', 'text-')} md:w-7 md:h-7`} />
            </div>
            <div className="flex-1 text-center pr-2 md:pr-4">
                <p className="text-[10px] md:text-xs text-slate-500 font-medium uppercase tracking-wide truncate">{title}</p>
                <h3 className="text-xl md:text-3xl font-bold text-slate-900 leading-tight">{count}</h3>
                {subtext && <p className="text-[10px] md:text-xs text-slate-400 mt-0.5">{subtext}</p>}
            </div>
        </div>
    );

    return (
        <div className="space-y-4 md:space-y-8 pb-20 animate-in fade-in slide-in-from-bottom-4">
            <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-6">
                <StatCard
                    title="Total Books"
                    count={books.length}
                    icon={Book}
                    color="bg-indigo-500"
                />
                <StatCard title="Articles" count={articles.length} icon={FileText} color="bg-blue-500" />
                <StatCard title="Websites" count={websites.length} icon={Globe} color="bg-emerald-500" />
                <StatCard title="Personal Notes" count={personalNotes.length} icon={PenTool} color="bg-amber-500" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Highlights Stats */}
                <div className="bg-white p-3 md:p-6 rounded-xl border border-slate-200 shadow-sm lg:col-span-2">
                    <h3 className="text-sm md:text-lg font-bold text-slate-800 mb-3 md:mb-6 flex items-center gap-2">
                        <Quote size={16} className="text-indigo-600 md:w-5 md:h-5" />
                        Content Collection
                    </h3>
                    <div className="grid grid-cols-1 gap-2 md:gap-4">
                        <div className="p-3 md:p-5 bg-yellow-50 rounded-xl border border-yellow-100">
                            <div className="flex items-center gap-2 md:gap-3 mb-1 md:mb-2">
                                <div className="p-1.5 md:p-2 bg-yellow-100 rounded-lg">
                                    <Quote className="text-yellow-600" size={16} />
                                </div>
                                <span className="font-semibold text-yellow-900 text-xs md:text-base">Highlights & Insights</span>
                            </div>
                            <p className="text-2xl md:text-4xl font-bold text-yellow-700 mt-1 md:mt-2">{quotes.length}</p>
                            <p className="text-[10px] md:text-xs text-yellow-600/80 mt-0.5 md:mt-1">Passages saved from books & articles</p>
                        </div>
                    </div>

                    {/* Inventory Check (Books Only) */}
                    <div className="mt-4 md:mt-6 pt-4 md:pt-6 border-t border-slate-100">
                        <h4 className="text-[10px] md:text-sm font-bold text-slate-500 uppercase tracking-wider mb-2 md:mb-4">Books Inventory</h4>
                        <div className="grid grid-cols-3 gap-2 md:gap-4">
                            <div className="flex flex-col md:flex-row items-center md:items-center gap-1 md:gap-3 p-2 md:p-3 rounded-lg bg-slate-50 border border-slate-100 text-center md:text-left">
                                <Archive size={14} className="text-slate-400 md:w-4 md:h-4" />
                                <div>
                                    <p className="text-[9px] md:text-xs text-slate-500">On Shelf</p>
                                    <p className="font-bold text-slate-700 text-sm md:text-base">{onShelfCount}</p>
                                </div>
                            </div>
                            <div className="flex flex-col md:flex-row items-center md:items-center gap-1 md:gap-3 p-2 md:p-3 rounded-lg bg-amber-50 border border-amber-100 text-center md:text-left">
                                <AlertTriangle size={14} className="text-amber-500 md:w-4 md:h-4" />
                                <div>
                                    <p className="text-[9px] md:text-xs text-amber-600">Lent Out</p>
                                    <p className="font-bold text-amber-700 text-sm md:text-base">{lentCount}</p>
                                </div>
                            </div>
                            <div className="flex flex-col md:flex-row items-center md:items-center gap-1 md:gap-3 p-2 md:p-3 rounded-lg bg-red-50 border border-red-100 text-center md:text-left">
                                <AlertTriangle size={14} className="text-red-500 md:w-4 md:h-4" />
                                <div>
                                    <p className="text-[9px] md:text-xs text-red-600">Lost</p>
                                    <p className="font-bold text-red-700 text-sm md:text-base">{lostCount}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Reading Progress */}
                <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                        <PieChart size={20} className="text-indigo-600" />
                        Library Progress
                    </h3>
                    <p className="text-xs text-slate-500 mb-4 -mt-4">Includes Books, Articles & Websites</p>

                    <div className="space-y-6">
                        <div>
                            <div className="flex justify-between text-sm mb-2">
                                <span className="flex items-center gap-2 text-slate-600"><CheckCircle size={14} /> Finished</span>
                                <span className="font-medium">{finishedCount}</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2">
                                <div className="bg-emerald-500 h-2 rounded-full transition-all duration-1000" style={{ width: `${totalReadable ? (finishedCount / totalReadable) * 100 : 0}%` }}></div>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between text-sm mb-2">
                                <span className="flex items-center gap-2 text-slate-600"><BookOpen size={14} /> Reading</span>
                                <span className="font-medium">{readingCount}</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2">
                                <div className="bg-indigo-500 h-2 rounded-full transition-all duration-1000" style={{ width: `${totalReadable ? (readingCount / totalReadable) * 100 : 0}%` }}></div>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between text-sm mb-2">
                                <span className="flex items-center gap-2 text-slate-600"><Clock size={14} /> To Read</span>
                                <span className="font-medium">{toReadCount}</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2">
                                <div className="bg-slate-400 h-2 rounded-full transition-all duration-1000" style={{ width: `${totalReadable ? (toReadCount / totalReadable) * 100 : 0}%` }}></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Category Distribution */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                    <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                        <Archive size={20} className="text-[#CC561E]" />
                        Category
                    </h3>
                    <span className="text-xs font-medium text-slate-500 bg-slate-100 px-2 py-1 rounded-full">
                        {books.length} Total Books
                    </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
                                    <span className="font-semibold text-slate-700 group-hover:text-[#CC561E] transition-colors">{category}</span>
                                    <div className="flex items-center gap-2">
                                        <span className="text-slate-400 text-xs">{percentage.toFixed(0)}%</span>
                                        <span className="font-bold text-slate-900">{count}</span>
                                    </div>
                                </div>
                                <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                                    <div
                                        className="bg-[#CC561E] h-full rounded-full transition-all duration-1000 ease-out opacity-80 group-hover:opacity-100"
                                        style={{ width: `${percentage}%` }}
                                    ></div>
                                </div>
                            </button>
                        );
                    })}
                </div>

                {books.length === 0 && (
                    <div className="py-10 text-center">
                        <p className="text-slate-400 text-sm italic">No books in library to categorize.</p>
                    </div>
                )}
            </div>
        </div>
    );
};
