export type Layer3ReportMode = 'STANDARD' | 'EXPLORER';

export interface Layer3ReportSource {
  title: string;
  pageNumber?: number | null;
}

export interface Layer3ReportDraftInput {
  question: string;
  answer: string;
  mode: Layer3ReportMode;
  sources?: Layer3ReportSource[];
  timestamp?: string;
}

export interface Layer3ReportDraft {
  title: string;
  htmlContent: string;
  tags: string[];
}

const REPORT_FALLBACK_TITLE = 'Research Report';

const escapeHtml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const normalizeWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();

const sanitizeQuestionForTitle = (question: string): string => {
  const sanitized = normalizeWhitespace(question).replace(/[?!.]+$/g, '');
  if (!sanitized) return REPORT_FALLBACK_TITLE;
  if (sanitized.length <= 72) return sanitized;
  return `${sanitized.slice(0, 69).trimEnd()}...`;
};

const formatTimestamp = (timestamp?: string): string => {
  const date = timestamp ? new Date(timestamp) : new Date();
  if (Number.isNaN(date.getTime())) {
    return new Date().toLocaleString('tr-TR');
  }
  return date.toLocaleString('tr-TR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const flushList = (items: string[], htmlParts: string[]) => {
  if (items.length === 0) return;
  htmlParts.push(`<ul>${items.map((item) => `<li><p>${escapeHtml(item)}</p></li>`).join('')}</ul>`);
  items.length = 0;
};

const formatAnswerHtml = (text: string): string => {
  const htmlParts: string[] = [];
  const listItems: string[] = [];

  text.split('\n').forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList(listItems, htmlParts);
      return;
    }

    const bulletMatch = line.match(/^[-*•]\s+(.+)/);
    if (bulletMatch) {
      listItems.push(bulletMatch[1].trim());
      return;
    }

    flushList(listItems, htmlParts);

    if (line.startsWith('### ')) {
      htmlParts.push(`<h3>${escapeHtml(line.replace(/^###\s+/, ''))}</h3>`);
      return;
    }
    if (line.startsWith('## ')) {
      htmlParts.push(`<h2>${escapeHtml(line.replace(/^##\s+/, ''))}</h2>`);
      return;
    }
    htmlParts.push(`<p>${escapeHtml(line)}</p>`);
  });

  flushList(listItems, htmlParts);
  return htmlParts.join('');
};

export const cleanLayer3Answer = (answer: string): string => {
  if (!answer) return '';
  return answer
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/\[(?:DÜŞÜNCE SÜRECİ|DÃœÅžÃœNCE SÃœRECÄ°)\][\s\S]*?\[\/(?:DÜŞÜNCE SÜRECİ|DÃœÅžÃœNCE SÃœRECÄ°)\]/gi, '')
    .replace(/^##\s*A(?:Ş|Åž)AMA\s*0:.*$/gim, '')
    .replace(/\[ID:\s*\d+\]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
};

export const buildLayer3ReportDraft = ({
  question,
  answer,
  mode,
  sources = [],
  timestamp,
}: Layer3ReportDraftInput): Layer3ReportDraft => {
  const cleanQuestion = normalizeWhitespace(question);
  const cleanAnswer = cleanLayer3Answer(answer);
  const uniqueSources = sources.filter((source, index, allSources) => {
    const signature = `${normalizeWhitespace(source.title)}|${source.pageNumber ?? ''}`;
    return allSources.findIndex((candidate) => `${normalizeWhitespace(candidate.title)}|${candidate.pageNumber ?? ''}` === signature) === index;
  });

  const sourcesHtml = uniqueSources.length > 0
    ? `<h2>Key Sources</h2><ul>${uniqueSources.map((source) => {
      const title = escapeHtml(normalizeWhitespace(source.title) || 'Untitled source');
      const page = Number.isFinite(source.pageNumber ?? NaN) && (source.pageNumber ?? 0) > 0
        ? ` (p. ${source.pageNumber})`
        : '';
      return `<li><p>${title}${escapeHtml(page)}</p></li>`;
    }).join('')}</ul>`
    : `<h2>Key Sources</h2><p></p>`;

  return {
    title: sanitizeQuestionForTitle(cleanQuestion),
    tags: ['report', 'layer3', mode === 'EXPLORER' ? 'explorer' : 'standard'],
    htmlContent: [
      '<h1>Research Report</h1>',
      '<h2>Research Question</h2>',
      `<p>${escapeHtml(cleanQuestion || REPORT_FALLBACK_TITLE)}</p>`,
      '<h2>Mode</h2>',
      `<p>${mode === 'EXPLORER' ? 'Explorer' : 'Standard'}</p>`,
      '<h2>Created At</h2>',
      `<p>${escapeHtml(formatTimestamp(timestamp))}</p>`,
      '<h2>Final Answer</h2>',
      formatAnswerHtml(cleanAnswer),
      sourcesHtml,
      '<h2>Open Questions / Next Steps</h2>',
      '<ul><li><p></p></li></ul>',
    ].join(''),
  };
};
