import { LibraryItem } from "../types";

export type WikiResolutionState = "resolved" | "ambiguous" | "unresolved";

export interface NoteLinkTarget {
  id: string;
  title: string;
}

export interface ParsedWikiToken {
  start: number;
  end: number;
  raw: string;
  label: string;
  noteId?: string;
}

export interface ResolvedWikiToken {
  state: WikiResolutionState;
  label: string;
  noteId?: string;
  candidates?: NoteLinkTarget[];
}

export interface CanonicalizeWikiResult {
  content: string;
  convertedCount: number;
  ambiguousCount: number;
  unresolvedCount: number;
}

export interface BacklinkItem {
  sourceId: string;
  sourceTitle: string;
}

const normalizeTitle = (value: string): string =>
  String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("tr-TR");

export function parseWikiTokens(input: string): ParsedWikiToken[] {
  const text = String(input || "");
  const out: ParsedWikiToken[] = [];

  let i = 0;
  while (i < text.length - 1) {
    if (text[i] !== "[" || text[i + 1] !== "[") {
      i += 1;
      continue;
    }

    const start = i;
    let close = -1;
    let j = i + 2;
    while (j < text.length - 1) {
      if (text[j] === "]" && text[j + 1] === "]") {
        close = j;
        break;
      }
      j += 1;
    }
    if (close < 0) {
      break;
    }

    const raw = text.slice(start, close + 2);
    const inner = text.slice(start + 2, close).trim();
    if (inner) {
      const barIndex = inner.lastIndexOf("|");
      if (barIndex >= 0) {
        const label = inner.slice(0, barIndex).trim();
        const noteId = inner.slice(barIndex + 1).trim();
        if (label) {
          out.push({
            start,
            end: close + 2,
            raw,
            label,
            noteId: noteId || undefined,
          });
        }
      } else {
        out.push({
          start,
          end: close + 2,
          raw,
          label: inner,
        });
      }
    }

    i = close + 2;
  }

  return out;
}

export function buildNoteLinkTargets(items: LibraryItem[]): NoteLinkTarget[] {
  return items
    .filter((item) => item.type === "PERSONAL_NOTE")
    .map((item) => ({
      id: item.id,
      title: (item.title || "").trim() || "Untitled",
    }));
}

function buildTitleIndex(targets: NoteLinkTarget[]): Map<string, NoteLinkTarget[]> {
  const index = new Map<string, NoteLinkTarget[]>();
  for (const target of targets) {
    const key = normalizeTitle(target.title);
    if (!key) continue;
    const existing = index.get(key);
    if (existing) {
      existing.push(target);
      continue;
    }
    index.set(key, [target]);
  }
  return index;
}

export function createWikiResolver(targets: NoteLinkTarget[]) {
  const titleIndex = buildTitleIndex(targets);
  const idSet = new Set(targets.map((target) => target.id));

  return (label: string, noteId?: string): ResolvedWikiToken => {
    const cleanLabel = String(label || "").trim();
    const cleanId = String(noteId || "").trim();
    if (!cleanLabel) {
      return { state: "unresolved", label: "" };
    }

    if (cleanId) {
      if (idSet.has(cleanId)) {
        return { state: "resolved", label: cleanLabel, noteId: cleanId };
      }
      return { state: "unresolved", label: cleanLabel };
    }

    const candidates = titleIndex.get(normalizeTitle(cleanLabel)) || [];
    if (candidates.length === 1) {
      return { state: "resolved", label: cleanLabel, noteId: candidates[0].id };
    }
    if (candidates.length > 1) {
      return { state: "ambiguous", label: cleanLabel, candidates };
    }
    return { state: "unresolved", label: cleanLabel };
  };
}

export function canonicalizeWikiLinks(
  rawContent: string,
  resolver: (label: string, noteId?: string) => ResolvedWikiToken
): CanonicalizeWikiResult {
  const text = String(rawContent || "");
  const tokens = parseWikiTokens(text);
  if (tokens.length === 0) {
    return {
      content: text,
      convertedCount: 0,
      ambiguousCount: 0,
      unresolvedCount: 0,
    };
  }

  let cursor = 0;
  let output = "";
  let convertedCount = 0;
  let ambiguousCount = 0;
  let unresolvedCount = 0;

  for (const token of tokens) {
    output += text.slice(cursor, token.start);
    let replacement = token.raw;
    if (!token.noteId) {
      const resolution = resolver(token.label, undefined);
      if (resolution.state === "resolved" && resolution.noteId) {
        replacement = `[[${token.label}|${resolution.noteId}]]`;
        convertedCount += 1;
      } else if (resolution.state === "ambiguous") {
        ambiguousCount += 1;
      } else {
        unresolvedCount += 1;
      }
    }
    output += replacement;
    cursor = token.end;
  }

  output += text.slice(cursor);
  return {
    content: output,
    convertedCount,
    ambiguousCount,
    unresolvedCount,
  };
}

export function buildBacklinks(
  notes: LibraryItem[],
  resolver: (label: string, noteId?: string) => ResolvedWikiToken
): Map<string, BacklinkItem[]> {
  const backlinks = new Map<string, BacklinkItem[]>();
  const dedupe = new Set<string>();
  const personalNotes = notes.filter((item) => item.type === "PERSONAL_NOTE");

  for (const source of personalNotes) {
    const content = String(source.generalNotes || "");
    const tokens = parseWikiTokens(content);
    for (const token of tokens) {
      const resolution = resolver(token.label, token.noteId);
      if (resolution.state !== "resolved" || !resolution.noteId) continue;
      if (resolution.noteId === source.id) continue;

      const dedupeKey = `${source.id}::${resolution.noteId}`;
      if (dedupe.has(dedupeKey)) continue;
      dedupe.add(dedupeKey);

      const list = backlinks.get(resolution.noteId) || [];
      list.push({
        sourceId: source.id,
        sourceTitle: (source.title || "").trim() || "Untitled",
      });
      backlinks.set(resolution.noteId, list);
    }
  }

  for (const [targetId, list] of backlinks.entries()) {
    list.sort((a, b) => a.sourceTitle.localeCompare(b.sourceTitle, "tr"));
    backlinks.set(targetId, list);
  }

  return backlinks;
}
