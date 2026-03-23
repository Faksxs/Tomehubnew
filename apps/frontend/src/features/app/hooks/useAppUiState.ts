import { useCallback, useState } from 'react';
import { PersonalNoteCategory } from '../../../types';
import { AppTab, AppView, LibrarySortOption, PersonalNoteDraftDefaults } from '../types';
import { createBookDetailState, createListContextReset, createPersonalNoteDraftDefaults } from '../stateHelpers';

interface OpenPersonalNoteFormDefaults {
    category?: PersonalNoteCategory;
    folderId?: string;
    folderPath?: string;
}

export const useAppUiState = () => {
    const [view, setView] = useState<AppView>('list');
    const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
    const [isFormOpen, setIsFormOpen] = useState(false);
    const [editingBookId, setEditingBookId] = useState<string | null>(null);
    const [openToHighlights, setOpenToHighlights] = useState(false);
    const [selectedHighlightId, setSelectedHighlightId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<AppTab>('DISCOVERY');
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [activeCategoryFilter, setActiveCategoryFilter] = useState<string | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [listSearch, setListSearch] = useState('');
    const [listStatusFilter, setListStatusFilter] = useState<string>('ALL');
    const [listSortOption, setListSortOption] = useState<LibrarySortOption>('date_desc');
    const [listPublisherFilter, setListPublisherFilter] = useState('');
    const [personalNoteDraftDefaults, setPersonalNoteDraftDefaults] = useState<PersonalNoteDraftDefaults>({});

    const resetListContext = useCallback((nextTab: AppTab, nextStatusFilter: string = 'ALL') => {
        const nextState = createListContextReset({
            view,
            selectedBookId,
            openToHighlights,
            selectedHighlightId,
            activeTab,
            activeCategoryFilter,
            currentPage,
            listSearch,
            listStatusFilter,
            listPublisherFilter,
        }, nextTab, nextStatusFilter);
        setActiveTab(nextState.activeTab);
        setView(nextState.view);
        setSelectedBookId(nextState.selectedBookId);
        setCurrentPage(nextState.currentPage);
        setListSearch(nextState.listSearch);
        setListStatusFilter(nextState.listStatusFilter);
        setListPublisherFilter(nextState.listPublisherFilter);
        setOpenToHighlights(nextState.openToHighlights);
        setSelectedHighlightId(nextState.selectedHighlightId);
        setActiveCategoryFilter(nextState.activeCategoryFilter);
    }, [activeCategoryFilter, activeTab, currentPage, listPublisherFilter, listSearch, listStatusFilter, openToHighlights, selectedBookId, selectedHighlightId, view]);

    const handleTabChange = useCallback((newTab: AppTab) => {
        resetListContext(newTab);
    }, [resetListContext]);

    const handleNavigateToBooksWithCategory = useCallback((category: string) => {
        setActiveCategoryFilter(category);
        resetListContext('BOOK');
    }, [resetListContext]);

    const handleNavigateToBooksWithStatus = useCallback((status: string) => {
        setActiveCategoryFilter(null);
        resetListContext('BOOK', status);
    }, [resetListContext]);

    const openBookDetail = useCallback((bookId: string) => {
        const nextState = createBookDetailState({
            view,
            selectedBookId,
            openToHighlights,
            selectedHighlightId,
            activeTab,
            activeCategoryFilter,
            currentPage,
            listSearch,
            listStatusFilter,
            listPublisherFilter,
        }, bookId);
        setSelectedBookId(nextState.selectedBookId);
        setOpenToHighlights(nextState.openToHighlights);
        setSelectedHighlightId(nextState.selectedHighlightId);
        setView(nextState.view);
    }, [activeCategoryFilter, activeTab, currentPage, listPublisherFilter, listSearch, listStatusFilter, openToHighlights, selectedBookId, selectedHighlightId, view]);

    const openBookHighlights = useCallback((bookId: string, highlightId?: string) => {
        const nextState = createBookDetailState({
            view,
            selectedBookId,
            openToHighlights,
            selectedHighlightId,
            activeTab,
            activeCategoryFilter,
            currentPage,
            listSearch,
            listStatusFilter,
            listPublisherFilter,
        }, bookId, highlightId);
        setSelectedBookId(nextState.selectedBookId);
        setOpenToHighlights(nextState.openToHighlights);
        setSelectedHighlightId(nextState.selectedHighlightId);
        setView(nextState.view);
    }, [activeCategoryFilter, activeTab, currentPage, listPublisherFilter, listSearch, listStatusFilter, openToHighlights, selectedBookId, selectedHighlightId, view]);

    const goBackFromDetail = useCallback(() => {
        setSelectedBookId(null);
        setOpenToHighlights(false);
        setSelectedHighlightId(null);
        setView('list');
    }, []);

    const openCreateBookForm = useCallback(() => {
        setPersonalNoteDraftDefaults({});
        setEditingBookId(null);
        setIsFormOpen(true);
    }, []);

    const openPersonalNoteForm = useCallback((defaults: OpenPersonalNoteFormDefaults = {}) => {
        setPersonalNoteDraftDefaults(createPersonalNoteDraftDefaults(defaults));
        setEditingBookId(null);
        setIsFormOpen(true);
    }, []);

    const openEditForm = useCallback((bookId: string) => {
        setEditingBookId(bookId);
        setIsFormOpen(true);
    }, []);

    const closeForm = useCallback(() => {
        setIsFormOpen(false);
        setEditingBookId(null);
        setPersonalNoteDraftDefaults({});
    }, []);

    return {
        view,
        setView,
        selectedBookId,
        setSelectedBookId,
        isFormOpen,
        setIsFormOpen,
        editingBookId,
        setEditingBookId,
        openToHighlights,
        setOpenToHighlights,
        selectedHighlightId,
        setSelectedHighlightId,
        activeTab,
        setActiveTab,
        isSidebarOpen,
        setIsSidebarOpen,
        activeCategoryFilter,
        setActiveCategoryFilter,
        currentPage,
        setCurrentPage,
        listSearch,
        setListSearch,
        listStatusFilter,
        setListStatusFilter,
        listSortOption,
        setListSortOption,
        listPublisherFilter,
        setListPublisherFilter,
        personalNoteDraftDefaults,
        setPersonalNoteDraftDefaults,
        handleTabChange,
        handleNavigateToBooksWithCategory,
        handleNavigateToBooksWithStatus,
        openBookDetail,
        openBookHighlights,
        goBackFromDetail,
        openCreateBookForm,
        openPersonalNoteForm,
        openEditForm,
        closeForm,
    };
};
