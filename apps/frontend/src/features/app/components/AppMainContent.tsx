import React from 'react';
import { BookList } from '../../../components/BookList';
import { BookDetail } from '../../../components/BookDetail';
import { ProfileView } from '../../../components/ProfileView';
import SmartSearch from '../../../components/SmartSearch';
import { RAGSearch } from '../../../components/RAGSearch';
import { FlowContainer } from '../../../components/FlowContainer';
import InsightsView from '../../../components/InsightsView';
import { Highlight, LibraryItem, PersonalNoteCategory, PersonalNoteFolder, ResourceType } from '../../../types';
import { AppTab, AppView } from '../types';
import { Layer3ReportDraftInput } from '../../../lib/layer3Report';

interface AppMainContentProps {
    activeTab: AppTab;
    view: AppView;
    userId: string;
    userEmail: string | null | undefined;
    onLogout: () => void;
    books: LibraryItem[];
    selectedBook?: LibraryItem;
    openToHighlights: boolean;
    selectedHighlightId: string | null;
    mediaLibraryEnabled: boolean;
    flowVisibleCategories: string[];
    activeCategoryFilter: string | null;
    personalNoteFolders: PersonalNoteFolder[];
    currentPage: number;
    listSearch: string;
    listStatusFilter: string;
    listSortOption: 'date_desc' | 'date_asc' | 'title_asc';
    listPublisherFilter: string;
    isEnriching: boolean;
    enrichmentStats: {
        total: number;
        processed: number;
        success: number;
        failed: number;
        currentBookTitle?: string;
    };
    onStartEnrichment: (books: LibraryItem[]) => void | Promise<void>;
    onStopEnrichment: () => void;
    onBackToDashboard: () => void;
    onSelectBook: (book: LibraryItem) => void;
    onSelectBookWithTab: (book: LibraryItem, tab: 'info' | 'highlights', highlightId?: string) => void;
    onAddBook: () => void;
    onAddPersonalNote: (defaults: { category: PersonalNoteCategory; folderId?: string; folderPath?: string }) => void;
    onQuickCreatePersonalNote: (payload: { title: string; content: string; category: PersonalNoteCategory; folderId?: string; folderPath?: string }) => void;
    onSaveLayer3Report: (payload: Layer3ReportDraftInput) => Promise<boolean>;
    onCreatePersonalFolder: (category: PersonalNoteCategory, name: string) => Promise<PersonalNoteFolder | null>;
    onRenamePersonalFolder: (folderId: string, name: string) => Promise<boolean>;
    onDeletePersonalFolder: (folderId: string) => Promise<boolean>;
    onMovePersonalFolder: (folderId: string, targetCategory: PersonalNoteCategory) => Promise<boolean>;
    onMovePersonalNote: (noteId: string, targetCategory: PersonalNoteCategory, targetFolderId?: string) => Promise<boolean>;
    onMobileMenuClick: () => void;
    onDeleteBook: (id: string) => void;
    onDeleteMultiple?: (ids: string[]) => void;
    onToggleFavorite: (id: string) => void;
    onToggleHighlightFavorite?: (bookId: string, highlightId: string) => void;
    onPageChange: (page: number) => void;
    onSearchChange: (value: string) => void;
    onStatusFilterChange: (value: string) => void;
    onSortOptionChange: (value: 'date_desc' | 'date_asc' | 'title_asc') => void;
    onPublisherFilterChange: (value: string) => void;
    onCategoryFilterChange: (value: string | null) => void;
    onCategoryNavigate: (category: string) => void;
    onStatusNavigate: (status: string) => void;
    onTabChange: (tab: AppTab) => void;
    onBackFromDetail: () => void;
    onEditSelectedBook: () => void;
    onDeleteSelectedBook: () => void;
    onUpdateHighlights: (highlights: Highlight[]) => void;
    onBookUpdated: (updatedBook: LibraryItem) => void;
}

export const AppMainContent: React.FC<AppMainContentProps> = ({
    activeTab,
    view,
    userId,
    userEmail,
    onLogout,
    books,
    selectedBook,
    openToHighlights,
    selectedHighlightId,
    mediaLibraryEnabled,
    flowVisibleCategories,
    activeCategoryFilter,
    personalNoteFolders,
    currentPage,
    listSearch,
    listStatusFilter,
    listSortOption,
    listPublisherFilter,
    isEnriching,
    enrichmentStats,
    onStartEnrichment,
    onStopEnrichment,
    onBackToDashboard,
    onSelectBook,
    onSelectBookWithTab,
    onAddBook,
    onAddPersonalNote,
    onQuickCreatePersonalNote,
    onSaveLayer3Report,
    onCreatePersonalFolder,
    onRenamePersonalFolder,
    onDeletePersonalFolder,
    onMovePersonalFolder,
    onMovePersonalNote,
    onMobileMenuClick,
    onDeleteBook,
    onDeleteMultiple,
    onToggleFavorite,
    onToggleHighlightFavorite,
    onPageChange,
    onSearchChange,
    onStatusFilterChange,
    onSortOptionChange,
    onPublisherFilterChange,
    onCategoryFilterChange,
    onCategoryNavigate,
    onStatusNavigate,
    onTabChange,
    onBackFromDetail,
    onEditSelectedBook,
    onDeleteSelectedBook,
    onUpdateHighlights,
    onBookUpdated,
}) => {
    if (activeTab === 'PROFILE') {
        return (
            <ProfileView
                email={userEmail}
                userId={userId}
                onLogout={onLogout}
                onBack={onBackToDashboard}
                books={books}
                onStartEnrichment={onStartEnrichment}
                onStopEnrichment={onStopEnrichment}
                isEnriching={isEnriching}
                enrichmentStats={enrichmentStats}
            />
        );
    }

    if (activeTab === 'SMART_SEARCH') {
        return <SmartSearch userId={userId} onBack={onBackToDashboard} books={books} />;
    }

    if (activeTab === 'RAG_SEARCH') {
        return <RAGSearch userId={userId} userEmail={userEmail} onBack={onBackToDashboard} books={books} onSaveReport={onSaveLayer3Report} />;
    }

    if (activeTab === 'FLOW') {
        return (
            <FlowContainer
                firebaseUid={userId}
                anchorType="topic"
                anchorId="General Discovery"
                categoryOptions={flowVisibleCategories}
                onClose={onBackToDashboard}
            />
        );
    }

    if (activeTab === 'INSIGHTS') {
        return (
            <InsightsView
                items={books}
                onBack={onBackToDashboard}
            />
        );
    }

    if (view === 'list') {
        return (
            <BookList
                books={books}
                activeTab={activeTab}
                mediaLibraryEnabled={mediaLibraryEnabled}
                userId={userId}
                categoryFilter={activeCategoryFilter}
                onCategoryFilterChange={onCategoryFilterChange}
                onCategoryNavigate={onCategoryNavigate}
                onStatusNavigate={onStatusNavigate}
                onSelectBook={onSelectBook}
                onSelectBookWithTab={onSelectBookWithTab}
                onAddBook={onAddBook}
                personalNoteFolders={personalNoteFolders}
                onCreatePersonalFolder={onCreatePersonalFolder}
                onRenamePersonalFolder={onRenamePersonalFolder}
                onDeletePersonalFolder={onDeletePersonalFolder}
                onMovePersonalFolder={onMovePersonalFolder}
                onMovePersonalNote={onMovePersonalNote}
                onAddPersonalNote={onAddPersonalNote}
                onQuickCreatePersonalNote={onQuickCreatePersonalNote}
                onMobileMenuClick={onMobileMenuClick}
                onDeleteBook={onDeleteBook}
                onDeleteMultiple={onDeleteMultiple}
                onToggleFavorite={onToggleFavorite}
                onToggleHighlightFavorite={onToggleHighlightFavorite}
                currentPage={currentPage}
                onPageChange={onPageChange}
                searchQuery={listSearch}
                onSearchChange={onSearchChange}
                statusFilter={listStatusFilter}
                onStatusFilterChange={onStatusFilterChange}
                sortOption={listSortOption}
                onSortOptionChange={onSortOptionChange}
                publisherFilter={listPublisherFilter}
                onPublisherFilterChange={onPublisherFilterChange}
                onTabChange={onTabChange}
            />
        );
    }

    return selectedBook ? (
        <BookDetail
            book={selectedBook}
            initialTab={openToHighlights ? 'highlights' : 'info'}
            autoEditHighlightId={selectedHighlightId || undefined}
            onBack={onBackFromDetail}
            onEdit={onEditSelectedBook}
            onDelete={onDeleteSelectedBook}
            onUpdateHighlights={onUpdateHighlights}
            onBookUpdated={onBookUpdated}
        />
    ) : null;
};
