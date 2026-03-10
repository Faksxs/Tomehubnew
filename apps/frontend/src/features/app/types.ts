import { PersonalNoteCategory, ResourceType } from '../../types';

export type AppTab =
    | ResourceType
    | 'NOTES'
    | 'DASHBOARD'
    | 'PROFILE'
    | 'RAG_SEARCH'
    | 'SMART_SEARCH'
    | 'FLOW'
    | 'INSIGHTS'
    | 'TODO'
    | 'INGEST';

export type AppView = 'list' | 'detail';

export type LibrarySortOption = 'date_desc' | 'date_asc' | 'title_asc';

export interface PersonalNoteDraftDefaults {
    personalNoteCategory?: PersonalNoteCategory;
    personalFolderId?: string;
    folderPath?: string;
}
