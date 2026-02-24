
export type PhysicalStatus = 'On Shelf' | 'Lent Out' | 'Lost';
export type ReadingStatus = 'To Read' | 'Reading' | 'Finished';
export type PersonalNoteCategory = 'PRIVATE' | 'DAILY' | 'IDEAS';

export type ResourceType = 'BOOK' | 'ARTICLE' | 'WEBSITE' | 'PERSONAL_NOTE';
export type ContentLanguageMode = 'AUTO' | 'TR' | 'EN';
export type ContentLanguageResolved = 'tr' | 'en';

export interface Highlight {
  id: string;
  text: string;
  // Canonical: highlight|insight. Legacy firebase records may still contain "note".
  type?: 'highlight' | 'insight' | 'note';
  pageNumber?: number;
  paragraphNumber?: number; // or line/position
  chapterTitle?: string;
  comment?: string; // "Why is this important" or context (used primarily for highlights)
  createdAt: number;
  tags?: string[];
  isFavorite?: boolean;
}

export interface LentInfo {
  borrowerName: string;
  lentDate: string;
}

export interface LibraryItem {
  id: string;
  type: ResourceType;
  title: string;
  author: string; // or "Site Name" for websites if author unavailable
  translator?: string;
  publisher?: string; // Used as Journal Name for Articles
  publicationYear?: string; // Specific for Articles
  isbn?: string;
  url?: string; // Specific for Websites
  code?: string; // Shelf code
  status: PhysicalStatus; // Inventory Status
  readingStatus: ReadingStatus; // Progress Status
  tags: string[];
  generalNotes?: string;
  summaryText?: string;
  contentLanguageMode?: ContentLanguageMode;
  contentLanguageResolved?: ContentLanguageResolved;
  sourceLanguageHint?: string;
  languageDecisionReason?: string;
  languageDecisionConfidence?: number;
  personalNoteCategory?: PersonalNoteCategory;
  personalFolderId?: string;
  folderPath?: string;
  coverUrl?: string; // Optional placeholder
  lentInfo?: LentInfo;
  highlights: Highlight[];
  addedAt: number;
  isFavorite?: boolean; // Favorite status
  isIngested?: boolean; // AI library status
  pageCount?: number;
}

export interface PersonalNoteFolder {
  id: string;
  category: PersonalNoteCategory;
  name: string;
  order: number;
  createdAt: number;
  updatedAt: number;
}

export type SortOption = 'title' | 'author' | 'addedAt';
