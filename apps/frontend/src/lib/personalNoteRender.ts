import { parseWikiTokens, ResolvedWikiToken } from './personalNoteWiki';

const HTML_TAG_RE = /<\/?[a-z][\s\S]*>/i;

const looksLikeHtml = (raw: string): boolean => HTML_TAG_RE.test(raw);

const escapeHtml = (text: string): string =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const escapeAttr = (text: string): string =>
  String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

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
    .replace(/^\s*-\s\[(?: |x|X)\]\s+/gm, '')
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

export type WikiLinkResolver = (label: string, noteId?: string) => ResolvedWikiToken;

export interface WikiRenderWarning {
  label: string;
  state: 'ambiguous' | 'unresolved';
  candidateCount?: number;
}

export const toPersonalNotePreviewHtmlWithWiki = (
  raw: string,
  resolver?: WikiLinkResolver
): { html: string; warnings: WikiRenderWarning[] } => {
  const baseHtml = toPersonalNotePreviewHtml(raw);
  if (!resolver || !baseHtml.includes('[[')) {
    return { html: baseHtml, warnings: [] };
  }
  if (typeof window === 'undefined') {
    return { html: baseHtml, warnings: [] };
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(baseHtml, 'text/html');
  const warnings: WikiRenderWarning[] = [];
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let current = walker.nextNode();
  while (current) {
    nodes.push(current as Text);
    current = walker.nextNode();
  }

  for (const textNode of nodes) {
    const value = textNode.nodeValue || '';
    if (!value.includes('[[')) continue;
    const tokens = parseWikiTokens(value);
    if (tokens.length === 0) continue;

    const fragments: string[] = [];
    let cursor = 0;
    for (const token of tokens) {
      const plain = value.slice(cursor, token.start);
      if (plain) {
        fragments.push(escapeHtml(plain));
      }

      const resolved = resolver(token.label, token.noteId);
      if (resolved.state === 'resolved' && resolved.noteId) {
        const label = escapeHtml(token.label);
        const noteId = escapeAttr(resolved.noteId);
        fragments.push(
          `<a href="#" data-note-id="${noteId}" class="wiki-link-resolved text-[#CC561E] underline decoration-dotted">${label}</a>`
        );
      } else if (resolved.state === 'ambiguous') {
        warnings.push({
          label: token.label,
          state: 'ambiguous',
          candidateCount: resolved.candidates?.length || 0,
        });
        fragments.push(
          `<span class="wiki-link-ambiguous border-b border-dashed border-amber-400 text-amber-600" title="Ayni baslikta birden fazla not var.">${escapeHtml(token.label)}</span>`
        );
      } else {
        warnings.push({
          label: token.label,
          state: 'unresolved',
        });
        fragments.push(
          `<span class="wiki-link-unresolved border-b border-dashed border-slate-400 text-slate-500" title="Link cozulemedi.">${escapeHtml(token.label)}</span>`
        );
      }
      cursor = token.end;
    }

    const tail = value.slice(cursor);
    if (tail) {
      fragments.push(escapeHtml(tail));
    }

    const span = doc.createElement('span');
    span.innerHTML = fragments.join('');
    textNode.parentNode?.replaceChild(span, textNode);
  }

  return { html: doc.body.innerHTML, warnings };
};
