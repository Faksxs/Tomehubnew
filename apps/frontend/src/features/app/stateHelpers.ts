import { PersonalNoteCategory, ResourceType } from '../../types';
import { AppTab, AppView, PersonalNoteDraftDefaults } from './types';

export interface AppUiSnapshot {
    view: AppView;
    selectedBookId: string | null;
    openToHighlights: boolean;
    selectedHighlightId: string | null;
    activeTab: AppTab;
    activeCategoryFilter: string | null;
    currentPage: number;
    listSearch: string;
    listStatusFilter: string;
    listPublisherFilter: string;
}

export const createListContextReset = (
    current: AppUiSnapshot,
    nextTab: AppTab,
    nextStatusFilter: string = 'ALL'
): AppUiSnapshot => {
    return {
        ...current,
        activeTab: nextTab,
        view: 'list',
        selectedBookId: null,
        currentPage: 1,
        listSearch: '',
        listStatusFilter: nextStatusFilter,
        listPublisherFilter: '',
        openToHighlights: false,
        selectedHighlightId: null,
        activeCategoryFilter: nextTab === 'BOOK' ? current.activeCategoryFilter : null,
    };
};

export const createBookDetailState = (
    current: AppUiSnapshot,
    bookId: string,
    highlightId?: string
): AppUiSnapshot => {
    return {
        ...current,
        view: 'detail',
        selectedBookId: bookId,
        openToHighlights: Boolean(highlightId),
        selectedHighlightId: highlightId || null,
    };
};

export const createPersonalNoteDraftDefaults = (
    defaults: {
        category?: PersonalNoteCategory;
        folderId?: string;
        folderPath?: string;
    } = {}
): PersonalNoteDraftDefaults => {
    return {
        personalNoteCategory: defaults.category || 'DAILY',
        personalFolderId: defaults.folderId,
        folderPath: defaults.folderPath,
    };
};

export const resolveAppFormInitialType = (
    editingType: ResourceType | undefined,
    activeTab: AppTab
): ResourceType => {
    if (editingType) return editingType;
    if (
        activeTab === 'NOTES' ||
        activeTab === 'DASHBOARD' ||
        activeTab === 'PROFILE' ||
        activeTab === 'RAG_SEARCH' ||
        activeTab === 'SMART_SEARCH' ||
        activeTab === 'FLOW' ||
        activeTab === 'INSIGHTS' ||
        activeTab === 'INGEST'
    ) {
        return 'BOOK';
    }
    return activeTab as ResourceType;
};
