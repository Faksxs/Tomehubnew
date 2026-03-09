import React from 'react';
import { Hash, Quote, Star, StickyNote } from 'lucide-react';
import { ArticlesLogo } from '../../../components/ui/FeatureLogos';
import { PaginationControls } from '../../../components/library/PaginationControls';
import { EmptyStatePanel } from '../../../components/library/EmptyStatePanel';
import { isInsightType } from '../../../lib/highlightType';
import { Highlight, LibraryItem } from '../../../types';

type HighlightItem = Highlight & {
    source: LibraryItem;
};

interface NotesHighlightsViewProps {
    highlights: HighlightItem[];
    searchQuery: string;
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
    onSelectHighlight: (highlight: HighlightItem) => void;
    onToggleHighlightFavorite?: (sourceId: string, highlightId: string) => void;
}

export const NotesHighlightsView: React.FC<NotesHighlightsViewProps> = ({
    highlights,
    searchQuery,
    currentPage,
    totalPages,
    onPageChange,
    onSelectHighlight,
    onToggleHighlightFavorite,
}) => {
    if (highlights.length === 0) {
        return (
            <EmptyStatePanel
                icon={<StickyNote size={24} className="text-slate-300 dark:text-slate-600 md:w-8 md:h-8" />}
                title="No highlights found"
                message={searchQuery ? 'Try a different search term.' : 'Highlights added to books appear here.'}
            />
        );
    }

    return (
        <div className="pb-10 md:pb-20">
            <div className="columns-2 sm:columns-2 lg:columns-3 gap-2 md:gap-6 space-y-2 md:space-y-6">
                {highlights.map((highlight, idx) => {
                    const isNote = isInsightType(highlight.type);

                    return (
                        <div
                            key={`${highlight.id}-${idx}`}
                            onClick={() => onSelectHighlight(highlight)}
                            className={`break-inside-avoid p-2 md:p-6 rounded-xl border hover:shadow-md transition-all group cursor-pointer relative flex flex-col active:scale-[0.99] ${isNote
                                ? 'bg-white dark:bg-slate-800 border-[#E6EAF2] dark:border-slate-700 hover:border-[#262D40]/12 dark:hover:border-[#262D40]/30'
                                : 'bg-white dark:bg-slate-800 border-[#E6EAF2] dark:border-slate-700 hover:border-[#262D40]/12 dark:hover:border-[#262D40]/30'
                                }`}
                        >
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onToggleHighlightFavorite?.(highlight.source.id, highlight.id);
                                }}
                                className={`absolute top-2 right-2 p-1.5 rounded-full transition-all shadow-sm z-10 ${highlight.isFavorite
                                    ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-500 dark:text-orange-400 opacity-100'
                                    : 'bg-white/80 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500 hover:text-orange-500 dark:hover:text-orange-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                    }`}
                                title={highlight.isFavorite ? 'Remove from Favorites' : 'Add to Favorites'}
                            >
                                <Star size={14} fill={highlight.isFavorite ? 'currentColor' : 'none'} />
                            </button>
                            <div className="mb-2 md:mb-3">
                                {isNote ? (
                                    <StickyNote className="text-[#CC561E] fill-[#CC561E]/10 w-4 h-4 md:w-6 md:h-6" />
                                ) : highlight.source?.type === 'ARTICLE' ? (
                                    <ArticlesLogo size={18} className="text-[#262D40]/85 md:w-6 md:h-6" />
                                ) : (
                                    <Quote className="text-[#262D40]/82 fill-[#262D40]/85 w-4 h-4 md:w-6 md:h-6" />
                                )}
                            </div>
                            <p className={`text-[10px] md:text-base leading-relaxed mb-2 md:mb-4 whitespace-pre-wrap line-clamp-[8] md:line-clamp-none font-lora ${isNote ? 'text-slate-700 dark:text-slate-300' : 'text-slate-900 dark:text-slate-200'}`}>
                                {highlight.text}
                            </p>

                            {highlight.tags && highlight.tags.length > 0 && (
                                <div className="flex flex-wrap gap-1 mb-2 md:mb-3">
                                    {highlight.tags.map((tag, i) => (
                                        <span key={i} className="px-1.5 md:px-2 py-0.5 md:py-1 bg-[#F3F5FA] dark:bg-slate-700/50 border border-[#E6EAF2] dark:border-white/10 rounded text-[10px] md:text-xs text-slate-500 dark:text-slate-400 flex items-center gap-0.5">
                                            <Hash size={10} className="md:w-3 md:h-3" /> {tag}
                                        </span>
                                    ))}
                                </div>
                            )}

                            <div className={`pt-2 md:pt-4 mt-auto flex items-center justify-between border-t ${isNote ? 'border-[#E6EAF2] dark:border-white/10' : 'border-[#262D40]/50 dark:border-white/10'}`}>
                                <div className="flex-1 min-w-0">
                                    <h4 className="text-xs md:text-sm font-bold text-slate-900 dark:text-white truncate">{highlight.source.title}</h4>
                                    <div className="flex items-center gap-1 md:gap-2 text-[10px] md:text-xs text-slate-500 dark:text-slate-400">
                                        <span className="truncate max-w-[50%]">{highlight.source.author}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            <PaginationControls
                currentPage={currentPage}
                totalPages={totalPages}
                onPageChange={onPageChange}
            />
        </div>
    );
};
