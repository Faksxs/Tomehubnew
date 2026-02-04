import React from 'react';
import { Book, FileText, Globe, StickyNote, Layers } from 'lucide-react';

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
                            className={`w-full flex items-center justify-between px-3 py-3 rounded-xl transition-all duration-300 group relative overflow-hidden ${isActive
                                ? 'bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] border border-[#CC561E]/30 shadow-sm'
                                : 'hover:bg-slate-50 dark:hover:bg-slate-800 border border-transparent'
                                }`}
                        >
                            <div className="flex items-center gap-3 relative z-10">
                                <div className={`p-2 rounded-lg transition-all duration-300 ${isActive ? 'text-[#CC561E] dark:text-[#f3a47b]' : 'text-slate-400 group-hover:text-slate-500 dark:text-slate-500'}`}>
                                    <Icon size={20} />
                                </div>
                                <span className={`text-sm font-medium tracking-tight ${isActive ? 'text-[#CC561E] dark:text-[#f3a47b]' : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:group-hover:text-slate-200'}`}>
                                    {cat.label}
                                </span>
                            </div>
                            {isActive && <div className="w-1.5 h-1.5 bg-[#CC561E] rounded-full animate-pulse mr-1" />}
                        </button>
                    );
                })}
            </div>

            <div className="mt-2" />
        </div>
    );
};

export default SourceNavigator;
