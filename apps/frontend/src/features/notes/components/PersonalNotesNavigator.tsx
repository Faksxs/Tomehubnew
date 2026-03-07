import React from 'react';
import { ChevronDown, Clock3, Folder, FolderPlus, GripVertical, ListFilter, Pencil, Star, Trash2, X } from 'lucide-react';
import { PersonalNoteCategory } from '../../../types';

type DroppableZoneComponent = React.ComponentType<{
    id: string;
    children: (isOver: boolean) => React.ReactNode;
}>;

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

type FolderSummary = {
    id: string;
    name: string;
    count: number;
};

type TopTagEntry = {
    key: string;
    label: string;
    count: number;
};

interface PersonalNotesNavigatorProps {
    isOpen: boolean;
    onClose: () => void;
    allNotesVisibleCount: number;
    favoriteNotesVisibleCount: number;
    recentNotesVisibleCount: number;
    noteCategoryFilter: 'ALL' | PersonalNoteCategory;
    noteFolderFilter: 'ALL' | '__ROOT__' | string;
    noteSmartFilter: 'NONE' | 'FAVORITES' | 'RECENT';
    noteTagFilter: string | null;
    isTopTagsOpen: boolean;
    onToggleTopTags: () => void;
    topTagEntries: TopTagEntry[];
    noteCategoryCounts: Record<PersonalNoteCategory, number>;
    rootNoteCounts: Record<PersonalNoteCategory, number>;
    categoryFolderMap: Record<PersonalNoteCategory, FolderSummary[]>;
    collapsedFolderCategories: Record<PersonalNoteCategory, boolean>;
    visibleFolderCounts: Record<PersonalNoteCategory, number>;
    onSelectAllNotes: () => void;
    onSelectFavorites: () => void;
    onSelectRecent: () => void;
    onClearTagFilter: () => void;
    onSelectTag: (tagKey: string) => void;
    onSelectCategory: (category: PersonalNoteCategory) => void;
    onCreateFolder: (category: PersonalNoteCategory) => void;
    onSelectUnfiled: (category: PersonalNoteCategory) => void;
    onToggleCategoryCollapse: (category: PersonalNoteCategory) => void;
    onLoadMoreFolders: (category: PersonalNoteCategory) => void;
    onSelectFolder: (category: PersonalNoteCategory, folderId: string) => void;
    onRenameFolder: (folderId: string, currentName: string) => void;
    onDeleteFolder: (folderId: string) => void;
    categoryLabel: (category: PersonalNoteCategory) => string;
    DroppableZone: DroppableZoneComponent;
    DraggableWrapper: DraggableWrapperComponent;
}

const NOTE_CATEGORIES: PersonalNoteCategory[] = ['PRIVATE', 'DAILY', 'IDEAS'];

export const PersonalNotesNavigator: React.FC<PersonalNotesNavigatorProps> = ({
    isOpen,
    onClose,
    allNotesVisibleCount,
    favoriteNotesVisibleCount,
    recentNotesVisibleCount,
    noteCategoryFilter,
    noteFolderFilter,
    noteSmartFilter,
    noteTagFilter,
    isTopTagsOpen,
    onToggleTopTags,
    topTagEntries,
    noteCategoryCounts,
    rootNoteCounts,
    categoryFolderMap,
    collapsedFolderCategories,
    visibleFolderCounts,
    onSelectAllNotes,
    onSelectFavorites,
    onSelectRecent,
    onClearTagFilter,
    onSelectTag,
    onSelectCategory,
    onCreateFolder,
    onSelectUnfiled,
    onToggleCategoryCollapse,
    onLoadMoreFolders,
    onSelectFolder,
    onRenameFolder,
    onDeleteFolder,
    categoryLabel,
    DroppableZone,
    DraggableWrapper,
}) => {
    return (
        <>
        <div
            className={`fixed inset-0 z-30 bg-slate-950/35 backdrop-blur-[1px] transition-opacity duration-200 lg:hidden ${isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
            onClick={onClose}
            aria-hidden={!isOpen}
        />
        <aside className={`fixed inset-y-0 left-0 z-40 w-[min(88vw,340px)] overflow-y-auto border-r border-[#E6EAF2] bg-white p-3 shadow-2xl transition-transform duration-200 dark:border-white/10 dark:bg-slate-900 lg:static lg:z-auto lg:w-auto lg:translate-x-0 lg:overflow-visible lg:rounded-xl lg:border lg:p-4 lg:shadow-none ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'} ${!isOpen ? 'pointer-events-none lg:pointer-events-auto' : ''}`}>
            <div className="sticky top-0 -mx-3 mb-3 flex items-center justify-between border-b border-[#E6EAF2] bg-white px-3 py-3 dark:border-white/10 dark:bg-slate-900 lg:static lg:mx-0 lg:border-b-0 lg:px-0 lg:py-0">
                <h3 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500 flex items-center gap-2">
                    <ListFilter size={14} />
                    Note Space
                </h3>
                <button
                    onClick={onClose}
                    className="lg:hidden text-slate-400 hover:text-slate-700"
                >
                    <X size={16} />
                </button>
            </div>

            <div className="space-y-2">
                <button
                    onClick={onSelectAllNotes}
                    className={`w-full text-left px-2.5 py-2 rounded-lg text-sm transition-colors ${noteCategoryFilter === 'ALL' && noteFolderFilter === 'ALL' && noteSmartFilter === 'NONE' && !noteTagFilter ? 'bg-[#262D40]/20 text-[#262D40] dark:text-white font-semibold' : 'hover:bg-[#F3F5FA] dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300'}`}
                >
                    All Notes ({allNotesVisibleCount})
                </button>

                <div className="rounded-lg border border-[#E6EAF2] dark:border-slate-800 p-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-1">Smart Folders</p>
                    <button
                        onClick={onSelectFavorites}
                        className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors flex items-center justify-between ${noteSmartFilter === 'FAVORITES' ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                    >
                        <span className="inline-flex items-center gap-1.5">
                            <Star size={12} />
                            Favorites
                        </span>
                        <span className="text-[10px] opacity-70">{favoriteNotesVisibleCount}</span>
                    </button>
                    <button
                        onClick={onSelectRecent}
                        className={`mt-1 w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors flex items-center justify-between ${noteSmartFilter === 'RECENT' ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                    >
                        <span className="inline-flex items-center gap-1.5">
                            <Clock3 size={12} />
                            Recent Notes
                        </span>
                        <span className="text-[10px] opacity-70">{recentNotesVisibleCount}</span>
                    </button>
                    <div className="mt-2 border-t border-[#E6EAF2] dark:border-slate-800 pt-2">
                        <div className="flex items-center justify-between mb-1">
                            <button
                                onClick={onToggleTopTags}
                                className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 inline-flex items-center gap-1 hover:text-slate-700 dark:hover:text-slate-300"
                            >
                                <ChevronDown size={11} className={`transition-transform ${isTopTagsOpen ? 'rotate-180' : ''}`} />
                                Top Tags
                            </button>
                            {noteTagFilter && (
                                <button
                                    onClick={onClearTagFilter}
                                    className="text-[10px] text-[#CC561E] hover:underline"
                                >
                                    Clear tag filter
                                </button>
                            )}
                        </div>
                        {isTopTagsOpen && (
                            topTagEntries.length === 0 ? (
                                <p className="text-[11px] text-slate-400 px-1 py-1">No tags yet</p>
                            ) : (
                                <div className="space-y-1">
                                    {topTagEntries.map((tag) => (
                                        <button
                                            key={tag.key}
                                            onClick={() => onSelectTag(tag.key)}
                                            className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors flex items-center justify-between ${noteTagFilter === tag.key ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                                        >
                                            <span className="truncate">#{tag.label}</span>
                                            <span className="text-[10px] opacity-70">{tag.count}</span>
                                        </button>
                                    ))}
                                </div>
                            )
                        )}
                    </div>
                </div>

                {NOTE_CATEGORIES.map((category) => (
                    <DroppableZone key={category} id={`cat-group:${category}`}>
                        {(isOverCategory) => (
                            <div className={`rounded-lg border p-2 ${isOverCategory ? 'border-[#CC561E]/40 bg-[#CC561E]/5' : 'border-[#E6EAF2] dark:border-slate-800'}`}>
                                <div className="flex items-center justify-between mb-1">
                                    <button
                                        onClick={() => onSelectCategory(category)}
                                        className={`text-xs font-semibold uppercase tracking-wide ${noteCategoryFilter === category && noteFolderFilter === 'ALL' && noteSmartFilter === 'NONE' && !noteTagFilter ? 'text-[#CC561E]' : 'text-slate-600 dark:text-slate-300'}`}
                                    >
                                        {categoryLabel(category)} ({noteCategoryCounts[category]})
                                    </button>
                                    <button
                                        onClick={() => onCreateFolder(category)}
                                        className="text-[11px] text-[#CC561E] hover:underline inline-flex items-center gap-1"
                                    >
                                        <FolderPlus size={11} />
                                        Folder
                                    </button>
                                </div>

                                <DroppableZone id={`cat-root:${category}`}>
                                    {(isOver) => (
                                        <button
                                            onClick={() => onSelectUnfiled(category)}
                                            className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm transition-colors ${isOver ? 'bg-[#CC561E]/15 border border-[#CC561E]/30' : 'border border-transparent'} ${noteCategoryFilter === category && noteFolderFilter === '__ROOT__' && noteSmartFilter === 'NONE' && !noteTagFilter ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'}`}
                                        >
                                            Unfiled ({rootNoteCounts[category]})
                                        </button>
                                    )}
                                </DroppableZone>

                                <div className="mt-1">
                                    <button
                                        onClick={() => onToggleCategoryCollapse(category)}
                                        className="w-full text-left px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 inline-flex items-center gap-1"
                                    >
                                        <ChevronDown size={11} className={`transition-transform ${collapsedFolderCategories[category] ? '' : 'rotate-180'}`} />
                                        Folders ({categoryFolderMap[category].length})
                                    </button>

                                    {!collapsedFolderCategories[category] && (
                                        <div className="mt-1 space-y-1">
                                            {categoryFolderMap[category].length === 0 ? (
                                                <p className="text-[11px] text-slate-400 px-1 py-1">No folders yet</p>
                                            ) : (
                                                categoryFolderMap[category].slice(0, visibleFolderCounts[category]).map((folder) => (
                                                    <DroppableZone key={folder.id} id={`folder:${folder.id}`}>
                                                        {(isOver) => (
                                                            <DraggableWrapper id={`folder-item:${folder.id}`}>
                                                                {({ setNodeRef, style, isDragging, attributes, listeners }) => (
                                                                    <div
                                                                        ref={setNodeRef}
                                                                        style={isDragging ? undefined : style}
                                                                        className={`w-full text-left px-2 py-1.5 rounded-md text-xs md:text-sm flex items-center gap-2 ${isOver ? 'bg-[#CC561E]/15 border border-[#CC561E]/30' : 'border border-transparent'} ${noteCategoryFilter === category && noteFolderFilter === folder.id && noteSmartFilter === 'NONE' && !noteTagFilter ? 'bg-[#CC561E]/10 text-[#CC561E] font-semibold' : 'text-slate-500 hover:bg-[#F3F5FA] dark:hover:bg-slate-800'} ${isDragging ? 'opacity-60 ring-2 ring-[#CC561E]/40' : ''}`}
                                                                    >
                                                                        <button
                                                                            {...attributes}
                                                                            {...listeners}
                                                                            onClick={(e) => e.stopPropagation()}
                                                                            className="p-1 rounded text-slate-400 hover:text-slate-700 cursor-grab active:cursor-grabbing"
                                                                            title="Move folder"
                                                                        >
                                                                            <GripVertical size={12} />
                                                                        </button>
                                                                        <button
                                                                            onClick={() => onSelectFolder(category, folder.id)}
                                                                            className="flex items-center gap-2 flex-1 min-w-0"
                                                                        >
                                                                            <Folder size={12} />
                                                                            <span className="truncate">{folder.name}</span>
                                                                        </button>
                                                                        <span className="text-[10px] opacity-70">{folder.count}</span>
                                                                        <button
                                                                            onClick={() => onRenameFolder(folder.id, folder.name)}
                                                                            className="text-slate-400 hover:text-slate-700"
                                                                            title="Rename folder"
                                                                        >
                                                                            <Pencil size={12} />
                                                                        </button>
                                                                        <button
                                                                            onClick={() => onDeleteFolder(folder.id)}
                                                                            className="text-slate-400 hover:text-red-500"
                                                                            title="Delete folder"
                                                                        >
                                                                            <Trash2 size={12} />
                                                                        </button>
                                                                    </div>
                                                                )}
                                                            </DraggableWrapper>
                                                        )}
                                                    </DroppableZone>
                                                ))
                                            )}

                                            {categoryFolderMap[category].length > visibleFolderCounts[category] && (
                                                <button
                                                    onClick={() => onLoadMoreFolders(category)}
                                                    className="w-full text-left px-2 py-1.5 rounded-md text-[11px] font-semibold text-[#CC561E] hover:bg-[#CC561E]/10"
                                                >
                                                    Load more ({categoryFolderMap[category].length - visibleFolderCounts[category]} left)
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </DroppableZone>
                ))}
            </div>
        </aside>
        </>
    );
};
