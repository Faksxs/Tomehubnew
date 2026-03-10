import { describe, expect, it } from 'vitest';
import { buildLayer3ReportDraft, cleanLayer3Answer } from './layer3Report';
import { findPersonalNoteTemplate } from './personalNoteTemplates';

describe('layer3Report', () => {
  it('removes internal tags and citation markers from answers', () => {
    const answer = [
      '<think>hidden</think>',
      '## AŞAMA 0: internal',
      'Visible line [ID: 4]',
    ].join('\n');

    expect(cleanLayer3Answer(answer)).toBe('Visible line');
  });

  it('builds a structured report draft with deduplicated sources', () => {
    const draft = buildLayer3ReportDraft({
      question: 'How does layer 3 reporting work?',
      answer: '## Summary\nClear answer\n- Point A',
      mode: 'EXPLORER',
      sources: [
        { title: 'Source One', pageNumber: 3 },
        { title: 'Source One', pageNumber: 3 },
      ],
      timestamp: '2026-03-10T09:15:00.000Z',
    });

    expect(draft.title).toContain('How does layer 3 reporting work');
    expect(draft.tags).toEqual(['report', 'layer3', 'explorer']);
    expect(draft.htmlContent).toContain('<h2>Research Question</h2>');
    expect(draft.htmlContent).toContain('<h2>Final Answer</h2>');
    expect(draft.htmlContent).toContain('<h2>Summary</h2>');
    expect(draft.htmlContent).toContain('Source One');
    expect(draft.htmlContent.match(/Source One/g)?.length).toBe(1);
  });

  it('exposes a manual report template for personal notes', () => {
    const template = findPersonalNoteTemplate('report_note');

    expect(template?.defaultCategory).toBe('IDEAS');
    expect(template?.htmlContent).toContain('Research Question');
    expect(template?.htmlContent).toContain('Next Steps');
  });
});
