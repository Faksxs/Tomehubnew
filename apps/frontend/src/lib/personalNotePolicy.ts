import { LibraryItem, PersonalNoteCategory } from '../types';

const DEFAULT_PERSONAL_NOTE_CATEGORY: PersonalNoteCategory = 'PRIVATE';

export function normalizePersonalNoteCategory(value: unknown): PersonalNoteCategory {
  const normalized = typeof value === 'string' ? value.trim().toUpperCase() : '';
  if (normalized === 'DAILY') return 'DAILY';
  if (normalized === 'IDEAS') return 'IDEAS';
  return DEFAULT_PERSONAL_NOTE_CATEGORY;
}

export function isPersonalNote(item: Pick<LibraryItem, 'type'>): boolean {
  return item.type === 'PERSONAL_NOTE';
}

export function getPersonalNoteCategory(item: LibraryItem): PersonalNoteCategory {
  if (!isPersonalNote(item)) return DEFAULT_PERSONAL_NOTE_CATEGORY;
  return normalizePersonalNoteCategory(item.personalNoteCategory);
}

export function shouldSyncPersonalNoteToAI(item: LibraryItem): boolean {
  return isPersonalNote(item) && getPersonalNoteCategory(item) === 'IDEAS';
}

export function getPersonalNoteBackendType(item: LibraryItem): 'INSIGHT' | 'PERSONAL_NOTE' {
  return shouldSyncPersonalNoteToAI(item) ? 'INSIGHT' : 'PERSONAL_NOTE';
}

export function normalizeFolderPath(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim().replace(/\s+/g, ' ');
  return trimmed || undefined;
}

export function normalizePersonalFolderId(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}
