import React from 'react';
import { Book, FileText, Globe, StickyNote, Layers, ChevronRight } from 'lucide-react';

export type SourceFilter = 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE' | 'ALL';

interface SourceNavigatorProps {
    activeFilter: SourceFilter;
    onFilterChange: (filter: SourceFilter) => void;
}

const SourceNavigator: React.FC<SourceNavigatorProps> = ({ activeFilter, onFilterChange }) => {
    const categories = [
        { id: 'ALL', label: 'All Notes', icon: Layers, color: 'text-slate-400', bg: 'bg-slate-500/10' },
        { id: 'BOOK', label: 'Books', icon: Book, color: 'text-slate-400', bg: 'bg-slate-500/10' },
        { id: 'ARTICLE', label: 'Articles', icon: FileText, color: 'text-slate-400', bg: 'bg-slate-500/10' },
        { id: 'WEBSITE', label: 'Websites', icon: Globe, color: 'text-slate-400', bg: 'bg-slate-500/10' },
        { id: 'PERSONAL_NOTE', label: 'Personal Notes', icon: StickyNote, color: 'text-slate-400', bg: 'bg-slate-500/10' },
    ];

    return (
        <div className="w-full flex flex-col gap-3 p-6 bg-white/5 backdrop-blur-2xl border border-white/5 rounded-3xl h-full overflow-y-auto">
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4 px-2 flex items-center gap-2">
                <span className="w-1 h-1 bg-[#CC561E] rounded-full"></span>
                Source Navigator
            </h3>

            <div className="space-y-2">
                {categories.map((cat) => {
                    const Icon = cat.icon;
                    const isActive = activeFilter === cat.id;

                    return (
                        <button
                            key={cat.id}
                            onClick={() => onFilterChange(cat.id as SourceFilter)}
                            className={`w-full flex items-center justify-between p-3.5 rounded-2xl transition-all duration-500 group relative overflow-hidden ${isActive
                                ? 'bg-[rgba(204,86,30,0.1)] shadow-[0_0_20px_rgba(204,86,30,0.15)] border border-[#CC561E]/30'
                                : 'hover:bg-white/5 border border-transparent'
                                }`}
                        >
                            {/* Hover/Active Glow */}
                            <div className={`absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent transition-transform duration-1000 translate-x-[-100%] group-hover:translate-x-[100%]`} />

                            <div className="flex items-center gap-4 relative z-10">
                                <div className={`p-2.5 rounded-xl transition-all duration-300 ${isActive ? 'bg-[#CC561E] text-white shadow-lg shadow-[#CC561E]/40' : 'bg-slate-800/50 text-slate-500 group-hover:text-slate-300'}`}>
                                    <Icon className="w-4 h-4" />
                                </div>
                                <span className={`text-sm font-semibold tracking-tight ${isActive ? 'text-[#CC561E] dark:text-white' : 'text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-200'}`}>
                                    {cat.label}
                                </span>
                            </div>
                            {isActive && <div className="w-1.5 h-1.5 bg-[#CC561E] rounded-full animate-pulse mr-1" />}
                        </button>
                    );
                })}
            </div>

            <div className={`mt-8 p-6 rounded-2xl ${activeFilter === 'ALL' ? 'bg-[rgba(204,86,30,0.05)] border-[rgba(204,86,30,0.1)]' : 'bg-slate-500/5 border-slate-500/10'} relative overflow-hidden group`}>
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                    <Layers className="w-12 h-12" />
                </div>
                <p className="text-[11px] text-slate-500 italic leading-relaxed text-center relative z-10 font-medium">
                    Filtering the knowledge stream focuses the AI's "epistemic lens" on selected evidence types.
                </p>
            </div>
        </div>
    );
};

export default SourceNavigator;
