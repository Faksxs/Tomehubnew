import type { Highlight, LibraryItem } from '../types';

export interface ReaderCaptureDraft {
  text: string;
  pageNumber: string;
  comment: string;
  tags: string;
}

interface BuildBookNoteHtmlInput {
  templateHtml: string;
  bookTitle: string;
  bookAuthor: string;
  quoteText: string;
  pageNumber?: string | number | null;
  comment?: string | null;
}

const escapeHtml = (value: string): string =>
  String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const normalizeLabel = (value: string): string =>
  String(value || '')
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const parseDraftTags = (raw: string): string[] => {
  const seen = new Set<string>();
  const items: string[] = [];
  for (const part of String(raw || '').split(',')) {
    const tag = part.trim();
    if (!tag) continue;
    const key = tag.toLocaleLowerCase('tr-TR');
    if (seen.has(key)) continue;
    seen.add(key);
    items.push(tag);
  }
  return items;
};

export const mergeCaptureTags = (...tagGroups: Array<string[] | undefined>): string[] => {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const group of tagGroups) {
    for (const entry of group || []) {
      const tag = String(entry || '').trim();
      if (!tag) continue;
      const key = tag.toLocaleLowerCase('tr-TR');
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(tag);
    }
  }
  return merged;
};

export const captureDraftTagsToList = (raw: string): string[] => parseDraftTags(raw);

export const createEmptyReaderCaptureDraft = (lastUsedPageNumber = ''): ReaderCaptureDraft => ({
  text: '',
  pageNumber: lastUsedPageNumber,
  comment: '',
  tags: '',
});

const appendFallbackQuoteSection = (
  templateHtml: string,
  quoteLabel: string,
  quoteText: string,
  comment?: string | null,
): string => {
  const quoteBlock = `<h2>${escapeHtml(quoteLabel)}</h2><ul><li><p>${escapeHtml(quoteText)}</p></li></ul>`;
  const commentBlock = comment
    ? `<h2>Ana Fikir</h2><p>${escapeHtml(comment)}</p>`
    : '';
  return `${templateHtml}${commentBlock}${quoteBlock}`;
};

const createHtmlDocument = (html: string): Document | null => {
  if (typeof DOMParser !== 'undefined') {
    return new DOMParser().parseFromString(html, 'text/html');
  }
  if (typeof document !== 'undefined' && document.implementation) {
    const doc = document.implementation.createHTMLDocument('');
    doc.body.innerHTML = html;
    return doc;
  }
  return null;
};

const findHeading = (doc: Document, label: string): HTMLElement | null => {
  const normalizedTarget = normalizeLabel(label);
  const headings = Array.from(doc.body.querySelectorAll('h1, h2, h3, h4, h5, h6'));
  for (const heading of headings) {
    if (normalizeLabel(heading.textContent || '').includes(normalizedTarget)) {
      return heading as HTMLElement;
    }
  }
  return null;
};

const findNextElementByTag = (start: HTMLElement | null, tags: string[]): HTMLElement | null => {
  let node = start?.nextElementSibling || null;
  while (node) {
    if (tags.includes(node.tagName.toUpperCase())) {
      return node as HTMLElement;
    }
    node = node.nextElementSibling;
  }
  return null;
};

const ensureParagraphAfter = (doc: Document, headingLabel: string): HTMLParagraphElement => {
  const heading = findHeading(doc, headingLabel);
  const existing = findNextElementByTag(heading, ['P']);
  if (existing && existing.tagName.toUpperCase() === 'P') {
    return existing as HTMLParagraphElement;
  }

  const fallbackHeading = doc.createElement('h2');
  fallbackHeading.textContent = headingLabel;
  const paragraph = doc.createElement('p');
  doc.body.appendChild(fallbackHeading);
  doc.body.appendChild(paragraph);
  return paragraph;
};

const ensureListAfter = (doc: Document, headingLabel: string): HTMLUListElement | HTMLOListElement => {
  const heading = findHeading(doc, headingLabel);
  const existing = findNextElementByTag(heading, ['UL', 'OL']);
  if (existing && (existing.tagName.toUpperCase() === 'UL' || existing.tagName.toUpperCase() === 'OL')) {
    return existing as HTMLUListElement | HTMLOListElement;
  }

  const fallbackHeading = doc.createElement('h2');
  fallbackHeading.textContent = headingLabel;
  const list = doc.createElement('ul');
  doc.body.appendChild(fallbackHeading);
  doc.body.appendChild(list);
  return list;
};

const setListFieldValue = (list: Element | null, label: string, value: string): void => {
  if (!list) return;
  const normalizedLabel = normalizeLabel(label);
  const items = Array.from(list.querySelectorAll('li'));
  for (const item of items) {
    const paragraph = item.querySelector('p');
    const target = paragraph || item;
    if (normalizeLabel(target.textContent || '').startsWith(normalizedLabel)) {
      target.textContent = `${label}: ${value}`;
      return;
    }
  }

  const li = list.ownerDocument.createElement('li');
  li.textContent = `${label}: ${value}`;
  list.appendChild(li);
};

export const buildBookNoteHtml = ({
  templateHtml,
  bookTitle,
  bookAuthor,
  quoteText,
  pageNumber,
  comment,
}: BuildBookNoteHtmlInput): string => {
  const cleanQuote = String(quoteText || '').trim();
  if (!cleanQuote) {
    return templateHtml;
  }

  const quoteWithPage = pageNumber
    ? `${cleanQuote} (s. ${String(pageNumber).trim()})`
    : cleanQuote;
  const doc = createHtmlDocument(templateHtml);
  if (!doc) {
    return appendFallbackQuoteSection(templateHtml, 'Onemli Alintilar', quoteWithPage, comment);
  }

  const infoHeading = findHeading(doc, 'kitap bilgisi');
  const infoList = findNextElementByTag(infoHeading, ['UL']);
  setListFieldValue(infoList, 'Baslik', bookTitle);
  setListFieldValue(infoList, 'Yazar', bookAuthor);

  if (comment && comment.trim()) {
    const paragraph = ensureParagraphAfter(doc, 'Ana Fikir');
    paragraph.textContent = comment.trim();
  }

  const quoteList = ensureListAfter(doc, 'Onemli Alintilar');
  const li = doc.createElement('li');
  const p = doc.createElement('p');
  p.textContent = quoteWithPage;
  li.appendChild(p);
  quoteList.appendChild(li);

  return doc.body.innerHTML;
};

export const buildCaptureHighlight = (
  draft: ReaderCaptureDraft,
  createdAt: number,
): Highlight => {
  const rawPage = draft.pageNumber.trim();
  const parsedPage = rawPage ? Number(rawPage) : undefined;

  return {
    id: `hl-${createdAt}-${Math.random().toString(36).slice(2, 8)}`,
    text: draft.text.trim(),
    type: 'highlight',
    pageNumber: Number.isFinite(parsedPage) ? parsedPage : undefined,
    comment: draft.comment.trim() || undefined,
    tags: captureDraftTagsToList(draft.tags),
    createdAt,
  };
};

export const buildPersonalNoteItem = ({
  id,
  title,
  htmlContent,
  tags,
  addedAt,
  category,
}: {
  id: string;
  title: string;
  htmlContent: string;
  tags: string[];
  addedAt: number;
  category: LibraryItem['personalNoteCategory'];
}): LibraryItem => ({
  id,
  type: 'PERSONAL_NOTE',
  title,
  author: 'Self',
  status: 'On Shelf',
  readingStatus: 'Finished',
  tags,
  generalNotes: htmlContent,
  personalNoteCategory: category,
  highlights: [],
  addedAt,
});
