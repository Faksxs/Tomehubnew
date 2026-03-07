import React from 'react';
import { ChevronDown } from 'lucide-react';
import { PersonalNoteEditor } from '../../../components/PersonalNoteEditor';
import { PersonalNoteCategory } from '../../../types';

interface QuickCapturePanelProps {
    isOpen: boolean;
    onToggleOpen: () => void;
    quickCaptureCategory: PersonalNoteCategory;
    onQuickCaptureCategoryChange: (category: PersonalNoteCategory) => void;
    selectedFolderName?: string;
    showSelectedFolder: boolean;
    quickNoteTitle: string;
    onQuickNoteTitleChange: (value: string) => void;
    quickNoteBody: string;
    onQuickNoteBodyChange: (value: string) => void;
    onSave: () => void;
    canSave: boolean;
    autoFocus?: boolean;
}

export const QuickCapturePanel: React.FC<QuickCapturePanelProps> = ({
    isOpen,
    onToggleOpen,
    quickCaptureCategory,
    onQuickCaptureCategoryChange,
    selectedFolderName,
    showSelectedFolder,
    quickNoteTitle,
    onQuickNoteTitleChange,
    quickNoteBody,
    onQuickNoteBodyChange,
    onSave,
    canSave,
    autoFocus = false,
}) => {
    const desktopControlsClass = isOpen ? 'flex' : 'hidden lg:flex';

    return (
        <div className={`bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-2xl overflow-hidden ${!isOpen ? 'hidden lg:block' : 'block'}`}>
            <div
                className={`w-full flex items-center justify-between p-4 md:p-5 transition-colors ${!isOpen ? 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50' : ''}`}
                onClick={() => !isOpen && onToggleOpen()}
            >
                <h4
                    className="hidden lg:flex text-sm md:text-base font-semibold uppercase tracking-[0.12em] text-slate-500 items-center gap-2 cursor-pointer"
                    onClick={(e) => {
                        e.stopPropagation();
                        onToggleOpen();
                    }}
                >
                    <ChevronDown size={16} className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
                    Quick Capture
                </h4>

                <div
                    className={`items-center gap-2 flex-1 lg:flex-none justify-between lg:justify-end ${desktopControlsClass}`}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div
                        className="flex items-center gap-2 flex-1 justify-between lg:justify-end"
                    >
                        <span className="lg:hidden text-[11px] font-bold text-slate-500 uppercase tracking-wider">Quick Capture</span>
                        <div className="flex items-center gap-2">
                            <select
                                value={quickCaptureCategory}
                                onChange={(e) => onQuickCaptureCategoryChange(e.target.value as PersonalNoteCategory)}
                                className="text-[11px] border border-[#E6EAF2] dark:border-slate-700 rounded-md px-2 py-1 bg-white dark:bg-slate-950 text-slate-500 outline-none"
                            >
                                <option value="DAILY">Daily</option>
                                <option value="PRIVATE">Private</option>
                                <option value="IDEAS">Ideas</option>
                            </select>
                            {showSelectedFolder && (
                                <span className="hidden sm:inline text-[11px] text-slate-400">
                                    / {selectedFolderName}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {isOpen && (
                <div className="px-4 pb-4 md:px-5 md:pb-5 pt-0 animate-in slide-in-from-top-2 duration-200">
                    <input
                        value={quickNoteTitle}
                        onChange={(e) => onQuickNoteTitleChange(e.target.value)}
                        placeholder="Note title (optional)"
                        className="w-full mb-3 border border-[#E6EAF2] dark:border-slate-700 rounded-xl px-4 py-3 text-sm md:text-base bg-white dark:bg-slate-950 block"
                    />
                    <div className="w-full">
                        <PersonalNoteEditor
                            key="quick-capture-editor"
                            value={quickNoteBody}
                            onChange={onQuickNoteBodyChange}
                            autoFocus={autoFocus}
                            placeholder="Start writing immediately..."
                            minHeight={242}
                        />
                    </div>
                    <div className="mt-3 flex justify-end w-full">
                        <button
                            onClick={onSave}
                            disabled={!canSave}
                            className="w-full sm:w-auto px-4 py-2.5 rounded-lg bg-[#262D40] text-white text-sm md:text-base disabled:opacity-40"
                        >
                            Save Quick Note
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
