/**
 * Pure data-transformation functions for the Discovery feature.
 *
 * These map raw API responses into the UI-facing DiscoveryCardData shape.
 * All functions are side-effect-free and fully testable in isolation.
 */

import {
  Activity,
  FlaskConical,
  GraduationCap,
  Library,
  ScrollText,
  Sparkles,
  Zap,
} from 'lucide-react';
import type React from 'react';
import type { LibraryItem, PersonalNoteCategory } from '../../types';
import { getPersonalNoteCategory } from '../../lib/personalNotePolicy';
import type {
  DiscoveryPageResponse,
  DiscoveryBoardResponse,
  DiscoveryCard as ExternalDiscoveryCard,
  DiscoveryInnerSpaceCard,
} from '../../services/backendApiService';
import type {
  DiscoveryCardData,
  DiscoveryCardSize,
  DiscoveryTopNode,
  DiscoveryViewMeta,
  ExternalCategoryKey,
  LatestSyncEntry,
  DormantGemEntry,
} from './discovery.types';
import { categoryVisuals, createEmptyPillarState } from './discovery.types';

import fallbackJson from './fallbackCards.json';

// ─── Icon Registry ───────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  GraduationCap,
  Activity,
  ScrollText,
  FlaskConical,
  Library,
  Sparkles,
  Zap,
};

const resolveIcon = (name?: string): React.ComponentType<{ size?: number; className?: string }> =>
  (name ? ICON_MAP[name] : undefined) || Sparkles;

// ─── Category Icon Map ───────────────────────────────────────────────────────

const categoryIcons: Record<ExternalCategoryKey, React.ComponentType<{ size?: number; className?: string }>> = {
  ACADEMIC: GraduationCap,
  RELIGIOUS: ScrollText,
  LITERARY: Library,
  CULTURE_HISTORY: Sparkles,
};

// ─── Static / Fallback Card Builders ─────────────────────────────────────────

export const buildStaticFallbackCards = (): DiscoveryCardData[] =>
  fallbackJson.staticCards.map((raw) => ({
    ...raw,
    icon: resolveIcon(raw.iconName),
  } as DiscoveryCardData));

export const buildFallbackInnerSpaceCards = (): DiscoveryCardData[] =>
  fallbackJson.fallbackInnerSpaceCards.map((raw) => ({
    ...raw,
    icon: resolveIcon(raw.iconName),
  } as DiscoveryCardData));

// ─── Text Helpers ────────────────────────────────────────────────────────────

const DAY_MS = 24 * 60 * 60 * 1000;
const DORMANT_MIN_AGE_MS = 21 * DAY_MS;

export const normalizeDiscoveryTagKey = (value: string): string =>
  value.trim().toLocaleLowerCase('tr-TR');

export const normalizeItemTimestamp = (value?: number): number | null => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  return numeric < 1_000_000_000_000 ? numeric * 1000 : numeric;
};

export const formatRelativeUpdateTime = (value: string | null): string => {
  if (!value) return 'Update unavailable';
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return 'Update unavailable';
  const deltaMs = Date.now() - parsed;
  if (deltaMs < 60_000) return 'Updated just now';
  if (deltaMs < 3_600_000) return `Updated ${Math.max(1, Math.floor(deltaMs / 60_000))}m ago`;
  if (deltaMs < 86_400_000) return `Updated ${Math.max(1, Math.floor(deltaMs / 3_600_000))}h ago`;
  return `Updated ${Math.max(1, Math.floor(deltaMs / 86_400_000))}d ago`;
};

export const formatArchiveAge = (value?: number): string => {
  const timestamp = normalizeItemTimestamp(value);
  if (!timestamp) return 'recently';
  const deltaMs = Math.max(0, Date.now() - timestamp);
  if (deltaMs < DAY_MS) return 'today';
  if (deltaMs < 7 * DAY_MS) return `${Math.max(1, Math.floor(deltaMs / DAY_MS))}d ago`;
  if (deltaMs < 30 * DAY_MS) return `${Math.max(1, Math.floor(deltaMs / (7 * DAY_MS)))}w ago`;
  if (deltaMs < 365 * DAY_MS) return `${Math.max(1, Math.floor(deltaMs / (30 * DAY_MS)))}mo ago`;
  return `${Math.max(1, Math.floor(deltaMs / (365 * DAY_MS)))}y ago`;
};

const formatArchiveWindow = (value?: number): string => {
  const timestamp = normalizeItemTimestamp(value);
  if (!timestamp) return 'a while';
  const deltaMs = Math.max(0, Date.now() - timestamp);
  if (deltaMs < DAY_MS) return 'today';
  if (deltaMs < 7 * DAY_MS) return `${Math.max(1, Math.floor(deltaMs / DAY_MS))} days`;
  if (deltaMs < 30 * DAY_MS) return `${Math.max(1, Math.floor(deltaMs / (7 * DAY_MS)))} weeks`;
  if (deltaMs < 365 * DAY_MS) return `${Math.max(1, Math.floor(deltaMs / (30 * DAY_MS)))} months`;
  return `${Math.max(1, Math.floor(deltaMs / (365 * DAY_MS)))} years`;
};

export const compactWhySeen = (value?: string): string | null => {
  const cleaned = String(value || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return null;
  if (cleaned.length <= 110) return cleaned;
  return `${cleaned.slice(0, 107).trimEnd()}...`;
};

export const compactEvidenceValue = (value?: string | null, limit = 320): string | null => {
  const raw = String(value || '');
  let stripped = raw.replace(/<[^>]*>?/gm, '');
  stripped = stripped
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&nbsp;/g, ' ');
  stripped = stripped.replace(/<[^>]*>?/gm, '');
  const cleaned = stripped.replace(/\s+/g, ' ').trim();
  if (!cleaned) return null;
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, limit - 3).trimEnd()}...`;
};

// ─── Card Action Helpers ─────────────────────────────────────────────────────

export const canOpenCard = (card?: DiscoveryCardData): boolean =>
  Boolean(card && (card.sourceUrl || card.itemId || card.flowAnchorLabel));

export const primaryCardActionLabel = (card: DiscoveryCardData): string => {
  if (card.sourceUrl) return 'OPEN_SOURCE';
  if (card.itemId) return 'OPEN_THREAD';
  return 'ASK_ARCHIVE';
};

// ─── Tag Aggregation ─────────────────────────────────────────────────────────

export const buildTopNodesFromLibrary = (items: LibraryItem[]): DiscoveryTopNode[] => {
  const tagMap = new Map<string, DiscoveryTopNode>();
  items.forEach((item) => {
    const uniqueTags = Array.from(new Set((item.tags || []).map((tag) => tag.trim()).filter(Boolean)));
    uniqueTags.forEach((tag) => {
      const key = normalizeDiscoveryTagKey(tag);
      if (!key) return;
      const previous = tagMap.get(key);
      tagMap.set(key, {
        label: previous?.label || tag,
        count: (previous?.count || 0) + 1,
      });
    });
  });
  return Array.from(tagMap.values())
    .sort((left, right) => right.count - left.count)
    .slice(0, 6);
};

// ─── Latest Sync / Dormant Gem Builders ──────────────────────────────────────

const pickMostRecentItem = (
  items: LibraryItem[],
  predicate: (item: LibraryItem) => boolean,
): LibraryItem | undefined =>
  items
    .filter(predicate)
    .sort((left, right) => (normalizeItemTimestamp(right.addedAt) || 0) - (normalizeItemTimestamp(left.addedAt) || 0))[0];

const buildLatestSyncDescription = (item: LibraryItem | undefined, fallbackLabel: string): string => {
  if (!item) return `No ${fallbackLabel.toLocaleLowerCase('en-US')} yet.`;
  const summary = compactEvidenceValue(item.summaryText || item.generalNotes, 118);
  if (summary) return summary;
  const relativeAge = formatArchiveAge(item.addedAt);
  if (item.type === 'BOOK') return `${item.author || 'Unknown author'} · added ${relativeAge}`;
  if (item.type === 'ARTICLE') return `${item.publisher || item.author || 'Saved article'} · added ${relativeAge}`;
  if (item.type === 'PERSONAL_NOTE') {
    const noteCategory = getPersonalNoteCategory(item);
    const noteLabel = noteCategory === 'IDEAS' ? 'Ideas note' : 'Daily note';
    return `${noteLabel} · added ${relativeAge}`;
  }
  const cinemaMeta = [item.originalTitle, item.rating ? `${item.rating}/5 rated` : null]
    .filter(Boolean)
    .join(' · ');
  return `${cinemaMeta || 'Saved title'} · added ${relativeAge}`;
};

export const buildLatestSyncEntries = (items: LibraryItem[]): LatestSyncEntry[] => {
  const latestBook = pickMostRecentItem(items, (item) => item.type === 'BOOK');
  const latestCinema = pickMostRecentItem(items, (item) => item.type === 'MOVIE' || item.type === 'SERIES');
  const latestArticle = pickMostRecentItem(items, (item) => item.type === 'ARTICLE');
  const latestPersonalNote = pickMostRecentItem(
    items,
    (item) => item.type === 'PERSONAL_NOTE' && ['IDEAS', 'DAILY'].includes(getPersonalNoteCategory(item)),
  );
  return [
    { key: 'latest-book', label: 'Latest Book', title: latestBook?.title || 'No recent book', description: buildLatestSyncDescription(latestBook, 'book sync'), item: latestBook },
    { key: 'latest-cinema', label: 'Latest Cinema', title: latestCinema?.title || 'No recent cinema', description: buildLatestSyncDescription(latestCinema, 'cinema sync'), item: latestCinema },
    { key: 'latest-article', label: 'Latest Article', title: latestArticle?.title || 'No recent article', description: buildLatestSyncDescription(latestArticle, 'article sync'), item: latestArticle },
    { key: 'latest-note', label: 'Latest Personal Note', title: latestPersonalNote?.title || 'No recent note', description: buildLatestSyncDescription(latestPersonalNote, 'personal note sync'), item: latestPersonalNote },
  ];
};

const dormantScore = (item: LibraryItem): number => {
  const timestamp = normalizeItemTimestamp(item.addedAt);
  if (!timestamp) return -1;
  const ageMs = Date.now() - timestamp;
  const summaryBonus = item.summaryText || item.generalNotes ? 5 * DAY_MS : 0;
  const highlightBonus = (item.highlights?.length || 0) > 0 ? 10 * DAY_MS : 0;
  const tagBonus = (item.tags?.length || 0) > 0 ? 4 * DAY_MS : 0;
  const ratingBonus = (item.rating || 0) >= 4 ? 7 * DAY_MS : 0;
  return ageMs + summaryBonus + highlightBonus + tagBonus + ratingBonus;
};

const buildDormantReason = (item: LibraryItem): string => {
  const quietWindow = formatArchiveWindow(item.addedAt);
  const highlightCount = item.highlights?.length || 0;
  if (highlightCount > 0) return `${highlightCount} saved highlight${highlightCount === 1 ? '' : 's'} but it has stayed quiet for ${quietWindow}.`;
  if (item.summaryText || item.generalNotes) return `You already captured context for it, but it has stayed buried for ${quietWindow}.`;
  if ((item.tags?.length || 0) > 0) return `Tagged around ${item.tags.slice(0, 2).join(' / ')}, but it has not resurfaced for ${quietWindow}.`;
  if ((item.rating || 0) >= 4) return `A strong-rated archive pick that has been quiet for ${quietWindow}.`;
  return `It has been sitting in the archive for ${quietWindow} without resurfacing.`;
};

export const buildDormantGemEntries = (items: LibraryItem[]): DormantGemEntry[] => {
  const groups: Array<{ key: string; label: string; predicate: (item: LibraryItem) => boolean }> = [
    { key: 'book', label: 'Book', predicate: (item) => item.type === 'BOOK' },
    { key: 'cinema', label: 'Cinema', predicate: (item) => item.type === 'MOVIE' || item.type === 'SERIES' },
    { key: 'article', label: 'Article', predicate: (item) => item.type === 'ARTICLE' },
  ];
  return groups
    .map(({ key, label, predicate }) => {
      const candidate = items
        .filter((item) => {
          const timestamp = normalizeItemTimestamp(item.addedAt);
          return Boolean(timestamp && Date.now() - timestamp >= DORMANT_MIN_AGE_MS && predicate(item));
        })
        .sort((left, right) => dormantScore(right) - dormantScore(left))[0];
      if (!candidate) return null;
      return { key, label, title: candidate.title, reason: buildDormantReason(candidate), item: candidate } satisfies DormantGemEntry;
    })
    .filter((entry): entry is DormantGemEntry => Boolean(entry));
};

// ─── API Response → UI Mapping ───────────────────────────────────────────────

const mapInnerSpaceCard = (card: DiscoveryInnerSpaceCard): DiscoveryCardData => {
  const config: Record<DiscoveryInnerSpaceCard['slot'], Pick<DiscoveryCardData, 'size' | 'tone' | 'icon'>> = {
    continue_this: { size: 'tall', tone: 'amber', icon: Activity },
    latest_sync: { size: 'hero', tone: 'purple', icon: Sparkles },
    dormant_gem: { size: 'detail', tone: 'dark', icon: FlaskConical },
    theme_pulse: { size: 'detail', tone: 'amber', icon: Zap },
  };
  return {
    id: `inner-${card.slot}`,
    category: 'Personal',
    family: card.family,
    slot: card.slot,
    title: card.title,
    summary: card.summary,
    sources: card.sources || [],
    progress: typeof card.progress_percent === 'number' ? card.progress_percent : undefined,
    syncRate: card.badge || undefined,
    metadata: card.metadata || undefined,
    itemId: card.item_id || undefined,
    itemType: card.item_type || undefined,
    promptSeed: card.prompt_seed || undefined,
    focusHint: card.focus_hint || undefined,
    ...config[card.slot],
  };
};

const mapBoardCard = (
  category: ExternalCategoryKey,
  card: ExternalDiscoveryCard,
  size: DiscoveryCardSize,
): DiscoveryCardData => {
  const visual = categoryVisuals[category];
  const askAction = card.actions.find((action) => action.type === 'ask_logoschat');
  const openSourceAction = card.actions.find((action) => action.type === 'open_source');
  const openAnchorAction = card.actions.find((action) => action.type === 'open_anchor');
  const flowAction = card.actions.find((action) => action.type === 'send_to_flux');
  const metadata = [card.primary_source, card.confidence_label].filter(Boolean).join(' / ');
  const syncRate = card.freshness_label || undefined;
  return {
    id: card.id,
    category: visual.category,
    family: card.family,
    title: card.title,
    summary: card.summary,
    whySeen: card.why_seen,
    evidence: Array.isArray(card.evidence) ? card.evidence : [],
    sources: card.source_refs.slice(0, 2).map((ref) => ref.label).filter(Boolean),
    size,
    tone: visual.tone,
    icon: categoryIcons[category],
    syncRate,
    metadata,
    imageUrl: card.image_url || undefined,
    itemId: openAnchorAction?.anchor_id || card.anchor_refs[0]?.item_id || undefined,
    itemType: card.anchor_refs[0]?.item_type || undefined,
    promptSeed: askAction?.prompt_seed || undefined,
    sourceUrl: openSourceAction?.url || card.source_refs.find((ref) => ref.url)?.url || undefined,
    flowAnchorId: flowAction?.anchor_id || card.anchor_refs[0]?.item_id || undefined,
    flowAnchorLabel: card.anchor_refs[0]?.title || card.title,
  };
};

const mapBoardResponseToCards = (
  board: DiscoveryPageResponse['boards']['academic'],
  category: ExternalCategoryKey,
): DiscoveryCardData[] => {
  const cards: DiscoveryCardData[] = [];
  if (board.featured_card) {
    cards.push(mapBoardCard(category, board.featured_card, 'hero'));
  }
  board.family_sections.forEach((section) => {
    section.cards.forEach((card) => {
      cards.push(mapBoardCard(category, card, 'detail'));
    });
  });
  return cards;
};

export const mapDiscoveryBoardPayload = (
  payload: DiscoveryBoardResponse,
): DiscoveryCardData[] => {
  // mapBoardResponseToCards takes board and category
  return mapBoardResponseToCards(payload, payload.category as ExternalCategoryKey);
};

export const mapDiscoveryPagePayload = (payload: DiscoveryPageResponse): {
  innerSpace: DiscoveryCardData[];
  pillars: Record<ExternalCategoryKey, DiscoveryCardData[]>;
  warning: string | null;
  meta: DiscoveryViewMeta;
} => {
  const pillars: Record<ExternalCategoryKey, DiscoveryCardData[]> = {
    ACADEMIC: mapBoardResponseToCards(payload.boards.academic, 'ACADEMIC'),
    RELIGIOUS: mapBoardResponseToCards(payload.boards.religious, 'RELIGIOUS'),
    LITERARY: mapBoardResponseToCards(payload.boards.literary, 'LITERARY'),
    CULTURE_HISTORY: mapBoardResponseToCards(payload.boards.culture_history, 'CULTURE_HISTORY'),
  };
  return {
    innerSpace: Array.isArray(payload.inner_space.cards) && payload.inner_space.cards.length > 0
      ? payload.inner_space.cards.map(mapInnerSpaceCard)
      : buildFallbackInnerSpaceCards(),
    pillars,
    warning: payload.metadata.board_errors.length > 0
      ? 'Some discovery sources were temporarily unavailable. Showing the strongest available cards.'
      : null,
    meta: {
      lastUpdatedAt: payload.metadata.last_updated_at || payload.inner_space.metadata.last_updated_at || null,
      hasCachedSnapshot: false,
      hasPartialErrors: payload.metadata.board_errors.length > 0,
      boardErrorCount: payload.metadata.board_errors.length,
    },
  };
};

export const limitPillarCardsForLayout = (
  pillars: Record<ExternalCategoryKey, DiscoveryCardData[]>,
): Record<ExternalCategoryKey, DiscoveryCardData[]> => ({
  ACADEMIC: pillars.ACADEMIC.slice(0, 3),
  RELIGIOUS: pillars.RELIGIOUS.slice(0, 1),
  LITERARY: pillars.LITERARY.slice(0, 2),
  CULTURE_HISTORY: pillars.CULTURE_HISTORY.slice(0, 2),
});

export const fallbackPillarsByCategory = (category: ExternalCategoryKey): DiscoveryCardData[] =>
  buildStaticFallbackCards().filter((card) => card.category === categoryVisuals[category].category);
