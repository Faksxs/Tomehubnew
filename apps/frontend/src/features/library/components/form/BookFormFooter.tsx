import React from 'react';
import { Loader2 } from 'lucide-react';
import { ResourceType } from '../../../../types';

interface BookFormFooterProps {
    initialData?: { id: string } | undefined;
    isNote: boolean;
    isIngesting: boolean;
    resourceType: ResourceType;
    onBackToSearch: () => void;
    onCancel: () => void;
}

const getSaveLabel = (resourceType: ResourceType) => {
    switch (resourceType) {
        case 'ARTICLE':
            return 'Article';
        case 'PERSONAL_NOTE':
            return 'Note';
        case 'MOVIE':
            return 'Movie';
        case 'SERIES':
            return 'Series';
        default:
            return 'Book';
    }
};

export const BookFormFooter: React.FC<BookFormFooterProps> = ({
    initialData,
    isNote,
    isIngesting,
    resourceType,
    onBackToSearch,
    onCancel,
}) => {
    return (
        <div className={`flex justify-between items-center mt-auto ${isNote ? 'border-t border-[#E6EAF2] bg-white px-5 py-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] dark:border-white/10 dark:bg-slate-900' : 'pt-2'}`}>
            {!initialData && !isNote && (
                <button
                    type="button"
                    onClick={onBackToSearch}
                    className="text-sm text-slate-500 dark:text-slate-400 hover:text-[#CC561E] dark:hover:text-[#f3a47b] underline decoration-[#CC561E]/30 dark:decoration-[#CC561E]/50 hover:decoration-[#CC561E] dark:hover:decoration-[#CC561E]"
                >
                    Back to Search
                </button>
            )}
            <div className={`flex gap-3 ${isNote ? 'w-full justify-end' : 'ml-auto'}`}>
                <button
                    type="button"
                    onClick={onCancel}
                    className={`text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors font-medium ${isNote ? 'px-4 py-2.5' : 'px-5 py-2'}`}
                >
                    Cancel
                </button>
                <button
                    type="submit"
                    disabled={isIngesting}
                    className={`bg-[#CC561E] text-white hover:bg-[#b34b1a] rounded-lg shadow-lg shadow-[#CC561E]/20 transition-all font-medium flex items-center gap-2 active:scale-95 ${isNote ? 'px-4 py-2.5' : 'px-5 py-2'}`}
                >
                    {isIngesting ? (
                        <>
                            <Loader2 size={18} className="animate-spin" />
                            Ingesting PDF...
                        </>
                    ) : (
                        <>Save {getSaveLabel(resourceType)}</>
                    )}
                </button>
            </div>
        </div>
    );
};
