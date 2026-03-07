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
        <div className={`flex justify-between items-center ${isNote ? 'pt-1' : 'pt-2'} mt-auto`}>
            {!initialData && !isNote && (
                <button
                    type="button"
                    onClick={onBackToSearch}
                    className="text-sm text-slate-500 dark:text-slate-400 hover:text-[#CC561E] dark:hover:text-[#f3a47b] underline decoration-[#CC561E]/30 dark:decoration-[#CC561E]/50 hover:decoration-[#CC561E] dark:hover:decoration-[#CC561E]"
                >
                    Back to Search
                </button>
            )}
            <div className="flex gap-3 ml-auto">
                <button
                    type="button"
                    onClick={onCancel}
                    className="px-5 py-2 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors font-medium"
                >
                    Cancel
                </button>
                <button
                    type="submit"
                    disabled={isIngesting}
                    className="px-5 py-2 bg-[#CC561E] text-white hover:bg-[#b34b1a] rounded-lg shadow-lg shadow-[#CC561E]/20 transition-all font-medium flex items-center gap-2 active:scale-95"
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
