import { describe, expect, it } from 'vitest';

import {
  buildBookNoteHtml,
  buildCaptureHighlight,
  captureDraftTagsToList,
  mergeCaptureTags,
} from './pdfReaderCapture';

describe('pdfReaderCapture', () => {
  it('dedupes and merges tags in stable order', () => {
    expect(
      mergeCaptureTags(['kitap', 'quote'], ['Quote', 'reading'], captureDraftTagsToList('ethics, quote')),
    ).toEqual(['kitap', 'quote', 'reading', 'ethics']);
  });

  it('builds highlight payload with numeric page and parsed tags', () => {
    const result = buildCaptureHighlight(
      {
        text: 'A copied passage',
        pageNumber: '42',
        comment: 'Important',
        tags: 'ethics, quote',
      },
      1700000000000,
    );

    expect(result.text).toBe('A copied passage');
    expect(result.pageNumber).toBe(42);
    expect(result.tags).toEqual(['ethics', 'quote']);
    expect(result.comment).toBe('Important');
  });

  it('escapes clipboard text when building book note html', () => {
    const result = buildBookNoteHtml({
      templateHtml: '<h2>Kitap Bilgisi</h2><ul><li>Baslik: </li><li>Yazar: </li></ul>',
      bookTitle: 'Irony',
      bookAuthor: 'Kierkegaard',
      quoteText: '<script>alert(1)</script>',
      pageNumber: '12',
      comment: 'Keep this safe',
    });

    expect(result).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(result).not.toContain('<script>alert(1)</script>');
  });
});
