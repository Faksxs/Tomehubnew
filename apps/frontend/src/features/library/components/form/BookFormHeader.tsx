import React from 'react';
import { Search, X } from 'lucide-react';

interface BookFormHeaderProps {
    isNote: boolean;
    mode: 'search' | 'edit';
    searchLabel: string;
    editTitle: string;
    editIcon: React.ReactNode;
    onClose: () => void;
}

export const BookFormHeader: React.FC<BookFormHeaderProps> = ({
    isNote,
    mode,
    searchLabel,
    editTitle,
    editIcon,
    onClose,
}) => {
    return (
        <div className={`${isNote ? 'sticky top-0 px-4 py-3 md:p-4' : 'p-5'} border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-white/95 dark:bg-slate-900/95 backdrop-blur-sm z-20`}>
            <h2 className={`${isNote ? 'text-lg' : 'text-xl'} font-bold text-slate-800 dark:text-white flex items-center gap-2`}>
                {mode === 'search' ? (
                    <>
                        <Search className="text-[#CC561E]" size={24} />
                        {searchLabel}
                    </>
                ) : (
                    <>
                        {editIcon}
                        {editTitle}
                    </>
                )}
            </h2>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors">
                <X size={isNote ? 20 : 24} />
            </button>
        </div>
    );
};
