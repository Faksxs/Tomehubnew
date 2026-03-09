import React from 'react';
import { Calendar, GripVertical, Link2, PenTool, Star, Trash2 } from 'lucide-react';
import { LibraryItem } from '../../../types';
import { extractBookmarkPreviewData, toPersonalNoteCardPreviewHtml } from '../../../lib/personalNoteRender';
import { getPersonalNoteCategory } from '../../../lib/personalNotePolicy';

type DraggableWrapperComponent = React.ComponentType<{
    id: string;
    children: (props: {
        setNodeRef: (element: HTMLElement | null) => void;
        style: React.CSSProperties;
        isDragging: boolean;
        attributes: any;
        listeners: any;
    }) => React.ReactNode;
}>;

interface PersonalNotesGridProps {
    notes: LibraryItem[];
    activeDraggedNoteId: string | null;
    onNoteClick: (note: LibraryItem) => void;
    onToggleFavorite: (noteId: string) => void;
    onDeleteNote: (noteId: string) => void;
    getResolvedNoteFolderName: (note: LibraryItem) => string | undefined;
    DraggableWrapper: DraggableWrapperComponent;
}

export const PersonalNotesGrid: React.FC<PersonalNotesGridProps> = ({
    notes,
    activeDraggedNoteId,
    onNoteClick,
    onToggleFavorite,
    onDeleteNote,
    getResolvedNoteFolderName,
    DraggableWrapper,
}) => {
    if (notes.length === 0) {
        return (
            <div className="text-center py-10 bg-white dark:bg-slate-900 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700">
                <PenTool size={26} className="mx-auto mb-2 text-slate-300" />
                <h3 className="text-base font-medium text-slate-900 dark:text-white">No notes matched this filter</h3>
                <p className="text-xs md:text-sm text-slate-500 mt-1">Change category/folder filter or create a new note.</p>
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 md:gap-4">
            {notes.map((note) => {
                const noteCategory = getPersonalNoteCategory(note);
                const isBookmark = noteCategory === 'BOOKMARK';
                const notePreviewHtml = toPersonalNoteCardPreviewHtml(note.generalNotes || (note.highlights && note.highlights.length > 0 ? note.highlights[0].text : ''));
                const bookmarkPreview = isBookmark ? extractBookmarkPreviewData(note.generalNotes || '') : null;
                const resolvedFolderName = getResolvedNoteFolderName(note);

                return (
                    <DraggableWrapper key={note.id} id={`note:${note.id}`}>
                        {({ setNodeRef, style, isDragging, attributes, listeners }) => (
                            <div
                                ref={setNodeRef}
                                style={isDragging ? undefined : style}
                                onClick={() => onNoteClick(note)}
                                className={`bg-white dark:bg-slate-800 p-4 md:p-5 rounded-none md:rounded-xl border-y md:border border-[#E6EAF2] dark:border-white/10 hover:border-[#262D40]/20 dark:hover:border-white/20 hover:shadow-md transition-all cursor-pointer flex flex-col group relative active:scale-[0.99] ${isDragging || activeDraggedNoteId === note.id ? 'opacity-60 ring-2 ring-[#CC561E]/40' : ''}`}
                            >
                                <div className="absolute top-2 left-2 z-10">
                                    <button
                                        {...attributes}
                                        {...listeners}
                                        onClick={(e) => e.stopPropagation()}
                                        className="p-1.5 rounded-full bg-white/85 dark:bg-slate-800/85 text-slate-400 hover:text-slate-700 shadow-sm"
                                        title="Drag note"
                                    >
                                        <GripVertical size={13} />
                                    </button>
                                </div>
                                <div className="absolute top-2 right-2 flex gap-1 z-10">
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onToggleFavorite(note.id);
                                        }}
                                        className={`p-1.5 rounded-full transition-all shadow-sm ${note.isFavorite
                                            ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-500 dark:text-orange-400 opacity-100'
                                            : 'bg-white/80 dark:bg-slate-800/80 text-slate-400 dark:text-slate-500 hover:text-orange-500 dark:hover:text-orange-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                                            }`}
                                        title={note.isFavorite ? 'Remove from Favorites' : 'Add to Favorites'}
                                    >
                                        <Star size={14} fill={note.isFavorite ? 'currentColor' : 'none'} />
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onDeleteNote(note.id);
                                        }}
                                        className="p-1.5 bg-white/80 dark:bg-slate-800/80 hover:bg-[#F3F5FA] dark:hover:bg-slate-700 text-slate-400 dark:text-slate-500 hover:text-slate-900 dark:hover:text-white rounded-full transition-all opacity-0 group-hover:opacity-100 focus:opacity-100 shadow-sm"
                                        title="Delete Note"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>

                                <h3 className="font-bold text-sm md:text-base text-slate-900 dark:text-white mb-2 leading-tight pl-8 pr-8">{note.title}</h3>
                                {isBookmark ? (
                                    <div className="mb-3 space-y-2">
                                        {(bookmarkPreview?.domain || bookmarkPreview?.url) && (
                                            <div className="rounded-lg border border-[#E6EAF2] dark:border-white/10 bg-[#F8FAFC] dark:bg-slate-900/70 px-3 py-2">
                                                {bookmarkPreview?.domain && (
                                                    <p className="text-[11px] md:text-xs font-semibold uppercase tracking-[0.14em] text-slate-400 mb-1">
                                                        {bookmarkPreview.domain}
                                                    </p>
                                                )}
                                                {bookmarkPreview?.url ? (
                                                    <div className="flex items-start gap-2 text-xs md:text-sm text-slate-600 dark:text-slate-300">
                                                        <Link2 size={13} className="mt-0.5 shrink-0 text-slate-400" />
                                                        <p className="break-all leading-relaxed">{bookmarkPreview.url}</p>
                                                    </div>
                                                ) : (
                                                    <p className="italic text-slate-400 dark:text-slate-500 text-xs md:text-sm">No URL added</p>
                                                )}
                                            </div>
                                        )}
                                        {bookmarkPreview?.note && (
                                            <div className="text-slate-600 dark:text-slate-300 text-xs md:text-sm whitespace-pre-wrap leading-relaxed max-h-[96px] overflow-hidden relative font-lora">
                                                <p>{bookmarkPreview.note}</p>
                                                {bookmarkPreview.note.length > 120 && (
                                                    <div className="absolute bottom-0 inset-x-0 h-8 bg-gradient-to-t from-white dark:from-slate-800 to-transparent" />
                                                )}
                                            </div>
                                        )}
                                        {!bookmarkPreview?.url && !bookmarkPreview?.note && (
                                            <span className="italic text-slate-400 dark:text-slate-500 text-xs md:text-sm">No content added</span>
                                        )}
                                    </div>
                                ) : (
                                    <div className="relative mb-3 overflow-hidden max-h-[180px]">
                                        <div
                                            className="text-slate-600 dark:text-slate-300 [&_ul]:pl-0 [&_li]:list-none [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_blockquote:last-child]:mb-0"
                                            dangerouslySetInnerHTML={{ __html: notePreviewHtml }}
                                        />
                                        <div className="pointer-events-none absolute bottom-0 inset-x-0 h-10 bg-gradient-to-t from-white dark:from-slate-800 to-transparent" />
                                    </div>
                                )}

                                <div className="mt-auto pt-2 flex flex-wrap gap-1.5 border-t border-slate-100 dark:border-white/10 items-center">
                                    <span className="px-2 py-0.5 bg-[#CC561E]/10 text-[#CC561E] text-[10px] md:text-xs rounded border border-[#CC561E]/20 font-semibold">
                                        {noteCategory}
                                    </span>
                                    {resolvedFolderName && (
                                        <span className="px-2 py-0.5 bg-[#F3F5FA] dark:bg-slate-800 text-slate-500 dark:text-slate-400 text-[10px] md:text-xs rounded border border-[#E6EAF2] dark:border-slate-700 truncate max-w-[150px]">
                                            {resolvedFolderName}
                                        </span>
                                    )}
                                    <span className="ml-auto text-[10px] md:text-xs text-slate-400 flex items-center gap-1">
                                        <Calendar size={10} className="md:w-3 md:h-3" />
                                        {new Date(note.addedAt).toLocaleDateString()}
                                    </span>
                                </div>
                            </div>
                        )}
                    </DraggableWrapper>
                );
            })}
        </div>
    );
};
