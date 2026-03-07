import React from 'react';
import { DndContext, DragOverlay, type DndContextProps, type DragEndEvent, type DragStartEvent } from '@dnd-kit/core';
import { restrictToWindowEdges } from '@dnd-kit/modifiers';
import { ChevronDown, Folder, ListFilter } from 'lucide-react';
import { LibraryItem, PersonalNoteCategory, PersonalNoteFolder } from '../../../types';
import { getPersonalNoteCategory } from '../../../lib/personalNotePolicy';
import { PersonalNotesNavigator } from './PersonalNotesNavigator';
import { QuickCapturePanel } from './QuickCapturePanel';
import { PersonalNotesGrid } from './PersonalNotesGrid';

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

interface PersonalNotesWorkspaceProps {
    dndSensors: DndContextProps['sensors'];
    collisionDetection: DndContextProps['collisionDetection'];
    onDragStart: (event: DragStartEvent) => void;
    onDragCancel: () => void;
    onDragEnd: (event: DragEndEvent) => void;
    isPersonalPanelOpen: boolean;
    onTogglePersonalPanel: () => void;
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
    isQuickCaptureOpen: boolean;
    onToggleQuickCapture: () => void;
    quickCaptureCategory: PersonalNoteCategory;
    onQuickCaptureCategoryChange: (category: PersonalNoteCategory) => void;
    selectedFolderName?: string;
    showSelectedFolder: boolean;
    quickNoteTitle: string;
    onQuickNoteTitleChange: (value: string) => void;
    quickNoteBody: string;
    onQuickNoteBodyChange: (value: string) => void;
    onSaveQuickNote: () => void;
    canSaveQuickNote: boolean;
    displayedBooks: LibraryItem[];
    activeDraggedNoteId: string | null;
    onNoteClick: (note: LibraryItem) => void;
    onToggleFavorite: (noteId: string) => void;
    onDeleteNote: (noteId: string) => void;
    getResolvedNoteFolderName: (note: LibraryItem) => string | undefined;
    activeDraggedNote: LibraryItem | null;
    activeDraggedFolder: PersonalNoteFolder | null;
}

export const PersonalNotesWorkspace: React.FC<PersonalNotesWorkspaceProps> = ({
    dndSensors,
    collisionDetection,
    onDragStart,
    onDragCancel,
    onDragEnd,
    isPersonalPanelOpen,
    onTogglePersonalPanel,
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
    isQuickCaptureOpen,
    onToggleQuickCapture,
    quickCaptureCategory,
    onQuickCaptureCategoryChange,
    selectedFolderName,
    showSelectedFolder,
    quickNoteTitle,
    onQuickNoteTitleChange,
    quickNoteBody,
    onQuickNoteBodyChange,
    onSaveQuickNote,
    canSaveQuickNote,
    displayedBooks,
    activeDraggedNoteId,
    onNoteClick,
    onToggleFavorite,
    onDeleteNote,
    getResolvedNoteFolderName,
    activeDraggedNote,
    activeDraggedFolder,
}) => {
    return (
        <DndContext
            sensors={dndSensors}
            collisionDetection={collisionDetection}
            modifiers={[restrictToWindowEdges]}
            onDragStart={onDragStart}
            onDragCancel={onDragCancel}
            onDragEnd={onDragEnd}
        >
            <div className="grid grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)] gap-4 md:gap-6">
                <PersonalNotesNavigator
                    isOpen={isPersonalPanelOpen}
                    onClose={onTogglePersonalPanel}
                    allNotesVisibleCount={allNotesVisibleCount}
                    favoriteNotesVisibleCount={favoriteNotesVisibleCount}
                    recentNotesVisibleCount={recentNotesVisibleCount}
                    noteCategoryFilter={noteCategoryFilter}
                    noteFolderFilter={noteFolderFilter}
                    noteSmartFilter={noteSmartFilter}
                    noteTagFilter={noteTagFilter}
                    isTopTagsOpen={isTopTagsOpen}
                    onToggleTopTags={onToggleTopTags}
                    topTagEntries={topTagEntries}
                    noteCategoryCounts={noteCategoryCounts}
                    rootNoteCounts={rootNoteCounts}
                    categoryFolderMap={categoryFolderMap}
                    collapsedFolderCategories={collapsedFolderCategories}
                    visibleFolderCounts={visibleFolderCounts}
                    onSelectAllNotes={onSelectAllNotes}
                    onSelectFavorites={onSelectFavorites}
                    onSelectRecent={onSelectRecent}
                    onClearTagFilter={onClearTagFilter}
                    onSelectTag={onSelectTag}
                    onSelectCategory={onSelectCategory}
                    onCreateFolder={onCreateFolder}
                    onSelectUnfiled={onSelectUnfiled}
                    onToggleCategoryCollapse={onToggleCategoryCollapse}
                    onLoadMoreFolders={onLoadMoreFolders}
                    onSelectFolder={onSelectFolder}
                    onRenameFolder={onRenameFolder}
                    onDeleteFolder={onDeleteFolder}
                    categoryLabel={categoryLabel}
                    DroppableZone={DroppableZone}
                    DraggableWrapper={DraggableWrapper}
                />

                <div className="space-y-3">
                    <div className="lg:hidden flex gap-2 px-3 md:px-0">
                        <button
                            onClick={onTogglePersonalPanel}
                            className="flex-1 px-3 py-2.5 bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-xl flex items-center justify-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400 shadow-sm active:scale-95 transition-all"
                        >
                            <ListFilter size={14} />
                            Navigator
                        </button>
                        <button
                            onClick={onToggleQuickCapture}
                            className={`flex-1 px-3 py-2.5 border rounded-xl flex items-center justify-center gap-2 text-[11px] font-bold uppercase tracking-wider transition-all shadow-sm active:scale-95 ${isQuickCaptureOpen ? 'bg-[#CC561E]/10 border-[#CC561E]/30 text-[#CC561E]' : 'bg-white dark:bg-slate-900 border-[#E6EAF2] dark:border-slate-800 text-slate-600 dark:text-slate-400'}`}
                        >
                            <ChevronDown size={14} className={`transition-transform duration-200 ${isQuickCaptureOpen ? 'rotate-180' : ''}`} />
                            Capture
                        </button>
                    </div>

                    <div className="px-3 md:px-0">
                        <QuickCapturePanel
                            isOpen={isQuickCaptureOpen}
                            onToggleOpen={onToggleQuickCapture}
                            quickCaptureCategory={quickCaptureCategory}
                            onQuickCaptureCategoryChange={onQuickCaptureCategoryChange}
                            selectedFolderName={selectedFolderName}
                            showSelectedFolder={showSelectedFolder}
                            quickNoteTitle={quickNoteTitle}
                            onQuickNoteTitleChange={onQuickNoteTitleChange}
                            quickNoteBody={quickNoteBody}
                            onQuickNoteBodyChange={onQuickNoteBodyChange}
                            onSave={onSaveQuickNote}
                            canSave={canSaveQuickNote}
                            autoFocus
                        />
                    </div>

                    <PersonalNotesGrid
                        notes={displayedBooks}
                        activeDraggedNoteId={activeDraggedNoteId}
                        onNoteClick={onNoteClick}
                        onToggleFavorite={onToggleFavorite}
                        onDeleteNote={onDeleteNote}
                        getResolvedNoteFolderName={getResolvedNoteFolderName}
                        DraggableWrapper={DraggableWrapper}
                    />
                </div>
            </div>

            <DragOverlay modifiers={[restrictToWindowEdges]}>
                {activeDraggedNote ? (
                    <div className="w-[320px] max-w-[80vw] bg-white dark:bg-slate-800 p-3 rounded-xl border border-[#CC561E]/35 shadow-xl cursor-grabbing">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{activeDraggedNote.title}</p>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-300 truncate">{categoryLabel(getPersonalNoteCategory(activeDraggedNote))}</p>
                    </div>
                ) : activeDraggedFolder ? (
                    <div className="w-[220px] max-w-[70vw] bg-white dark:bg-slate-900 px-3 py-2 rounded-lg border border-[#CC561E]/35 shadow-xl cursor-grabbing flex items-center gap-2">
                        <Folder size={13} className="text-slate-500" />
                        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{activeDraggedFolder.name}</span>
                    </div>
                ) : null}
            </DragOverlay>
        </DndContext>
    );
};
