import { describe, expect, it } from 'vitest';
import {
    createBookDetailState,
    createListContextReset,
    createPersonalNoteDraftDefaults,
    resolveAppFormInitialType,
    type AppUiSnapshot,
} from './stateHelpers';

const baseState: AppUiSnapshot = {
    view: 'detail',
    selectedBookId: 'book-1',
    openToHighlights: true,
    selectedHighlightId: 'hl-1',
    activeTab: 'PERSONAL_NOTE',
    activeCategoryFilter: 'Philosophy',
    currentPage: 4,
    listSearch: 'Nietzsche',
    listStatusFilter: 'READING',
    listPublisherFilter: 'Penguin',
};

describe('stateHelpers', () => {
    it('resets list context and clears detail-specific state', () => {
        const next = createListContextReset(baseState, 'DASHBOARD');

        expect(next.activeTab).toBe('DASHBOARD');
        expect(next.view).toBe('list');
        expect(next.selectedBookId).toBeNull();
        expect(next.openToHighlights).toBe(false);
        expect(next.selectedHighlightId).toBeNull();
        expect(next.currentPage).toBe(1);
        expect(next.listSearch).toBe('');
        expect(next.listStatusFilter).toBe('ALL');
        expect(next.listPublisherFilter).toBe('');
        expect(next.activeCategoryFilter).toBeNull();
    });

    it('keeps category filter when resetting into BOOK tab', () => {
        const next = createListContextReset(baseState, 'BOOK', 'FINISHED');

        expect(next.activeTab).toBe('BOOK');
        expect(next.activeCategoryFilter).toBe('Philosophy');
        expect(next.listStatusFilter).toBe('FINISHED');
    });

    it('creates detail state for book info and highlights', () => {
        const detail = createBookDetailState(baseState, 'book-9');
        const highlights = createBookDetailState(baseState, 'book-9', 'hl-9');

        expect(detail.view).toBe('detail');
        expect(detail.selectedBookId).toBe('book-9');
        expect(detail.openToHighlights).toBe(false);
        expect(detail.selectedHighlightId).toBeNull();

        expect(highlights.openToHighlights).toBe(true);
        expect(highlights.selectedHighlightId).toBe('hl-9');
    });

    it('builds personal note defaults with DAILY fallback', () => {
        expect(createPersonalNoteDraftDefaults()).toEqual({
            personalNoteCategory: 'DAILY',
            personalFolderId: undefined,
            folderPath: undefined,
        });

        expect(createPersonalNoteDraftDefaults({
            category: 'IDEAS',
            folderId: 'folder-1',
            folderPath: 'Projects',
        })).toEqual({
            personalNoteCategory: 'IDEAS',
            personalFolderId: 'folder-1',
            folderPath: 'Projects',
        });
    });

    it('resolves app form initial type safely for non-resource tabs', () => {
        expect(resolveAppFormInitialType(undefined, 'DASHBOARD')).toBe('BOOK');
        expect(resolveAppFormInitialType(undefined, 'INSIGHTS')).toBe('BOOK');
        expect(resolveAppFormInitialType(undefined, 'PERSONAL_NOTE')).toBe('PERSONAL_NOTE');
        expect(resolveAppFormInitialType('ARTICLE', 'FLOW')).toBe('ARTICLE');
    });
});
