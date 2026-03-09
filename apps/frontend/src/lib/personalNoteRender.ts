const HTML_TAG_RE = /<\/?[a-z][\s\S]*>/i;

const looksLikeHtml = (raw: string): boolean => HTML_TAG_RE.test(raw);

const escapeHtml = (text: string): string =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const applyInlineFormatting = (text: string): string => {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<u>$1</u>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="px-1 py-0.5 rounded bg-slate-100 text-slate-700">$1</code>');
};

const sanitizeRichHtml = (raw: string): string => {
  if (typeof window === 'undefined') {
    return raw;
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, 'text/html');

  doc.querySelectorAll('script,style,iframe,object,embed').forEach((node) => node.remove());
  doc.body.querySelectorAll('*').forEach((el) => {
    [...el.attributes].forEach((attr) => {
      const name = attr.name.toLowerCase();
      const value = attr.value.toLowerCase();
      if (name.startsWith('on')) el.removeAttribute(attr.name);
      if ((name === 'href' || name === 'src') && value.startsWith('javascript:')) {
        el.removeAttribute(attr.name);
      }
    });
  });

  return doc.body.innerHTML;
};

type PreviewLine =
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'bullet'; text: string }
  | { kind: 'check'; text: string; checked: boolean }
  | { kind: 'quote'; text: string };

const normalizePreviewText = (text: string): string =>
  text
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s+\n/g, '\n')
    .trim();

const pushPreviewLine = (target: PreviewLine[], line: PreviewLine, maxLines: number) => {
  const text = normalizePreviewText(line.text);
  if (!text || target.length >= maxLines) return;
  target.push({ ...line, text } as PreviewLine);
};

const extractTablePreviewLines = (table: Element, target: PreviewLine[], maxLines: number) => {
  const rows = Array.from(table.querySelectorAll('tr'));
  rows.forEach((row) => {
    if (target.length >= maxLines) return;
    const cells = Array.from(row.querySelectorAll('th, td'));
    const pieces = cells
      .map((cell) => normalizePreviewText(cell.textContent || ''))
      .filter(Boolean);
    if (pieces.length === 0) return;
    pushPreviewLine(target, { kind: 'paragraph', text: pieces.join(' ') }, maxLines);
  });
};

const extractHtmlPreviewLines = (raw: string, maxLines: number): PreviewLine[] => {
  if (typeof window === 'undefined') {
    return extractPlainPreviewLines(extractPersonalNoteText(raw), maxLines);
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, 'text/html');
  const lines: PreviewLine[] = [];
  const blockTags = new Set(['P', 'DIV', 'LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE']);

  const visit = (node: Element) => {
    if (lines.length >= maxLines) return;

    const tag = node.tagName.toUpperCase();

    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'IFRAME' || tag === 'OBJECT' || tag === 'EMBED') {
      return;
    }

    if (tag === 'TABLE') {
      extractTablePreviewLines(node, lines, maxLines);
      return;
    }

    if (tag === 'UL' || tag === 'OL') {
      Array.from(node.children).forEach((child) => {
        if (lines.length >= maxLines) return;
        if (!(child instanceof Element) || child.tagName.toUpperCase() !== 'LI') return;
        const checkbox = child.querySelector('input[type="checkbox"]') as HTMLInputElement | null;
        const text = normalizePreviewText(child.textContent || '');
        if (!text) return;
        if (checkbox) {
          pushPreviewLine(lines, { kind: 'check', text, checked: checkbox.checked }, maxLines);
        } else {
          pushPreviewLine(lines, { kind: 'bullet', text }, maxLines);
        }
      });
      return;
    }

    if (blockTags.has(tag)) {
      const text = normalizePreviewText(node.textContent || '');
      if (!text) return;
      if (tag.startsWith('H')) {
        pushPreviewLine(lines, { kind: 'heading', text }, maxLines);
      } else if (tag === 'BLOCKQUOTE') {
        pushPreviewLine(lines, { kind: 'quote', text }, maxLines);
      } else {
        const checkbox = node.querySelector('input[type="checkbox"]') as HTMLInputElement | null;
        if (checkbox) {
          pushPreviewLine(lines, { kind: 'check', text, checked: checkbox.checked }, maxLines);
        } else {
          pushPreviewLine(lines, { kind: 'paragraph', text }, maxLines);
        }
      }
      return;
    }

    Array.from(node.children).forEach((child) => {
      if (child instanceof Element) visit(child);
    });
  };

  Array.from(doc.body.children).forEach((child) => {
    if (child instanceof Element) visit(child);
  });

  return lines;
};

const extractPlainPreviewLines = (raw: string, maxLines: number): PreviewLine[] => {
  const lines: PreviewLine[] = [];
  const rawLines = raw.split('\n');

  for (const rawLine of rawLines) {
    if (lines.length >= maxLines) break;
    const line = rawLine.trim();
    if (!line) continue;

    const heading = line.match(/^#{1,6}\s+(.+)/);
    const checklist = line.match(/^\s*-\s\[( |x|X)\]\s+(.+)/);
    const bullet = line.match(/^\s*[-*+]\s+(.+)/);
    const quote = line.match(/^\s*>\s+(.+)/);
    const numbered = line.match(/^\s*\d+\.\s+(.+)/);

    if (heading) {
      pushPreviewLine(lines, { kind: 'heading', text: heading[1] }, maxLines);
      continue;
    }
    if (checklist) {
      pushPreviewLine(lines, { kind: 'check', text: checklist[2], checked: checklist[1].toLowerCase() === 'x' }, maxLines);
      continue;
    }
    if (bullet) {
      pushPreviewLine(lines, { kind: 'bullet', text: bullet[1] }, maxLines);
      continue;
    }
    if (quote) {
      pushPreviewLine(lines, { kind: 'quote', text: quote[1] }, maxLines);
      continue;
    }
    if (numbered) {
      pushPreviewLine(lines, { kind: 'bullet', text: numbered[1] }, maxLines);
      continue;
    }
    pushPreviewLine(lines, { kind: 'paragraph', text: line }, maxLines);
  }

  return lines;
};

const renderPreviewLinesHtml = (lines: PreviewLine[]): string => {
  if (lines.length === 0) {
    return '<p class="text-slate-400 italic">No content added.</p>';
  }

  let html = '';
  let currentList: 'ul' | null = null;

  const closeList = () => {
    if (currentList) {
      html += `</${currentList}>`;
      currentList = null;
    }
  };

  for (const line of lines) {
    if (line.kind === 'bullet' || line.kind === 'check') {
      if (currentList !== 'ul') {
        closeList();
        currentList = 'ul';
        html += '<ul class="space-y-1.5 my-1">';
      }
      const prefix = line.kind === 'check' ? (line.checked ? '&#9745;' : '&#9744;') : '&bull;';
      html += `<li class="flex items-start gap-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300"><span class="mt-0.5 text-slate-400 shrink-0">${prefix}</span><span>${applyInlineFormatting(escapeHtml(line.text))}</span></li>`;
      continue;
    }

    closeList();
    if (line.kind === 'heading') {
      html += `<p class="text-[13px] md:text-sm font-semibold text-slate-800 dark:text-slate-100 mt-1.5 first:mt-0">${applyInlineFormatting(escapeHtml(line.text))}</p>`;
      continue;
    }
    if (line.kind === 'quote') {
      html += `<blockquote class="my-1 border-l-2 border-[#CC561E]/30 pl-3 text-xs md:text-sm italic text-slate-500 dark:text-slate-400">${applyInlineFormatting(escapeHtml(line.text))}</blockquote>`;
      continue;
    }
    html += `<p class="text-xs md:text-sm leading-relaxed text-slate-600 dark:text-slate-300 my-1">${applyInlineFormatting(escapeHtml(line.text))}</p>`;
  }

  closeList();
  return html;
};

export const extractPersonalNoteText = (raw: string): string => {
  if (!raw) return '';

  if (looksLikeHtml(raw)) {
    const htmlWithBreakHints = raw
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|li|h1|h2|h3|h4|h5|h6|blockquote|pre|tr|td|th|ul|ol)>/gi, '\n');

    if (typeof window !== 'undefined') {
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlWithBreakHints, 'text/html');
      return (doc.body.textContent || '')
        .replace(/\r\n/g, '\n')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    }
    return htmlWithBreakHints
      .replace(/<[^>]*>/g, ' ')
      .replace(/\r\n/g, '\n')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/[ \t]{2,}/g, ' ')
      .trim();
  }

  return raw
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*-\s\[( |x|X)\]\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/_(.*?)_/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .replace(/\s+\n/g, '\n')
    .trim();
};

export const hasMeaningfulPersonalNoteContent = (raw: string): boolean =>
  extractPersonalNoteText(raw).trim().length > 0;

export interface BookmarkPreviewData {
  url: string;
  domain: string;
  note: string;
}

export const extractBookmarkPreviewData = (raw: string): BookmarkPreviewData => {
  const text = extractPersonalNoteText(raw);
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);

  let url = "";
  let note = "";
  let inNote = false;
  const noteLines: string[] = [];

  for (const line of lines) {
    const lower = line.toLowerCase();
    if (lower.startsWith("url:")) {
      url = line.slice(line.indexOf(":") + 1).trim();
      inNote = false;
      continue;
    }
    if (lower.startsWith("note:")) {
      const initialNote = line.slice(line.indexOf(":") + 1).trim();
      if (initialNote) noteLines.push(initialNote);
      inNote = true;
      continue;
    }
    if (inNote) {
      noteLines.push(line);
    }
  }

  note = noteLines.join(" ").trim();

  let domain = "";
  if (url) {
    try {
      const normalizedUrl = /^https?:\/\//i.test(url) ? url : `https://${url}`;
      domain = new URL(normalizedUrl).hostname.replace(/^www\./i, "");
    } catch {
      domain = "";
    }
  }

  return { url, domain, note };
};

export const toPersonalNoteCardPreviewHtml = (raw: string, maxLines = 6): string => {
  if (!hasMeaningfulPersonalNoteContent(raw)) {
    return '<p class="text-slate-400 italic">No content added.</p>';
  }

  const lines = looksLikeHtml(raw)
    ? extractHtmlPreviewLines(raw, maxLines)
    : extractPlainPreviewLines(raw, maxLines);

  return renderPreviewLinesHtml(lines);
};

export const toPersonalNotePreviewHtml = (raw: string): string => {
  if (!hasMeaningfulPersonalNoteContent(raw)) {
    return '<p class="text-slate-400 italic">No content added.</p>';
  }

  if (looksLikeHtml(raw)) {
    return sanitizeRichHtml(raw);
  }

  const lines = raw.split('\n');
  let html = '';
  let currentList: 'ul' | 'ol' | null = null;

  const closeList = () => {
    if (currentList) {
      html += `</${currentList}>`;
      currentList = null;
    }
  };

  for (const line of lines) {
    if (!line.trim()) {
      closeList();
      html += '<div class="h-2"></div>';
      continue;
    }

    const heading1 = line.match(/^\s*#\s+(.+)/);
    const heading2 = line.match(/^\s*##\s+(.+)/);
    const checklist = line.match(/^\s*-\s\[( |x|X)\]\s+(.+)/);
    const bullet = line.match(/^\s*-\s+(.+)/);
    const numbered = line.match(/^\s*\d+\.\s+(.+)/);
    const quote = line.match(/^\s*>\s+(.+)/);

    if (heading1) {
      closeList();
      html += `<h1 class="text-xl font-bold mt-3 mb-1.5">${applyInlineFormatting(escapeHtml(heading1[1]))}</h1>`;
      continue;
    }
    if (heading2) {
      closeList();
      html += `<h2 class="text-lg font-semibold mt-3 mb-1.5">${applyInlineFormatting(escapeHtml(heading2[1]))}</h2>`;
      continue;
    }
    if (quote) {
      closeList();
      html += `<blockquote class="border-l-2 border-[#CC561E]/40 pl-3 italic text-slate-600 my-1">${applyInlineFormatting(escapeHtml(quote[1]))}</blockquote>`;
      continue;
    }
    if (checklist) {
      if (currentList !== 'ul') {
        closeList();
        currentList = 'ul';
        html += '<ul class="space-y-1 my-1">';
      }
      const checked = checklist[1].toLowerCase() === 'x';
      html += `<li class="text-sm flex items-start gap-2"><span class="mt-0.5">${checked ? '&#9745;' : '&#9744;'}</span><span>${applyInlineFormatting(escapeHtml(checklist[2]))}</span></li>`;
      continue;
    }
    if (bullet) {
      if (currentList !== 'ul') {
        closeList();
        currentList = 'ul';
        html += '<ul class="list-disc pl-5 space-y-1 my-1">';
      }
      html += `<li class="text-sm">${applyInlineFormatting(escapeHtml(bullet[1]))}</li>`;
      continue;
    }
    if (numbered) {
      if (currentList !== 'ol') {
        closeList();
        currentList = 'ol';
        html += '<ol class="list-decimal pl-5 space-y-1 my-1">';
      }
      html += `<li class="text-sm">${applyInlineFormatting(escapeHtml(numbered[1]))}</li>`;
      continue;
    }

    closeList();
    html += `<p class="text-sm leading-relaxed my-1">${applyInlineFormatting(escapeHtml(line.trim()))}</p>`;
  }

  closeList();
  return html;
};
