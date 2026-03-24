import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowUpRight,
  BookmarkPlus,
  GraduationCap,
  MessageSquareText,
  Activity,
  Zap,
  Sparkles,
  FlaskConical,
  ScrollText,
  Library,
  RotateCw,
  Menu,
} from 'lucide-react';
import type { AppTab } from '../../app/types';
import type { LibraryItem, PersonalNoteCategory } from '../../../types';
import { getFriendlyApiErrorMessage } from '../../../services/apiClient';
import { getPersonalNoteCategory } from '../../../lib/personalNotePolicy';
import {
  getDiscoveryPage,
  type DiscoveryPageResponse,
  type DiscoveryCard as ExternalDiscoveryCard,
  type DiscoveryEvidence,
  type DiscoveryInnerSpaceCard,
  type DiscoveryInnerSpaceSlot,
} from '../../../services/backendApiService';
import {
  persistDiscoveryFlowSeed,
  persistDiscoveryPromptSeed,
} from '../discoverySeeds';

interface DiscoveryHomeProps {
  userId: string;
  books: LibraryItem[];
  onMobileMenuClick: () => void;
  onTabChange: (tab: AppTab) => void;
  onQuickCreatePersonalNote: (payload: {
    title: string;
    content: string;
    category: PersonalNoteCategory;
    folderId?: string;
    folderPath?: string;
  }) => void;
  onOpenDiscoveryItem: (item: LibraryItem, focus?: 'info' | 'highlights') => void;
}

type DiscoveryCategory = 'Personal' | 'Academic' | 'Religious' | 'Literary' | 'Culture';
type DiscoveryCardSize = 'hero' | 'detail' | 'wide' | 'tall';
type DiscoveryTone = 'light' | 'dark' | 'green' | 'blue' | 'purple' | 'amber' | 'cyan';

const DISCOVERY_PAGE_CACHE_KEY = 'tomehub:discovery:page-cache:v1';
const DISCOVERY_PAGE_CACHE_TTL_MS = 5 * 60 * 1000;
const DISCOVERY_PAGE_CACHE_MAX_STALE_MS = 30 * 60 * 1000;

interface DiscoveryCardData {
  id: string;
  category: DiscoveryCategory;
  family: string;
  slot?: DiscoveryInnerSpaceSlot;
  title: string;
  summary: string;
  whySeen?: string;
  evidence?: DiscoveryEvidence[];
  sources: string[];
  size: DiscoveryCardSize;
  tone: DiscoveryTone;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  progress?: number;
  syncRate?: string;
  metadata?: string;
  itemId?: string;
  itemType?: string;
  promptSeed?: string;
  focusHint?: 'info' | 'highlights';
  sourceUrl?: string;
  imageUrl?: string;
  flowAnchorId?: string;
  flowAnchorLabel?: string;
}

interface DiscoveryTopNode {
  label: string;
  count: number;
}

interface DiscoveryViewMeta {
  lastUpdatedAt: string | null;
  hasCachedSnapshot: boolean;
  hasPartialErrors: boolean;
  boardErrorCount: number;
}

interface LatestSyncEntry {
  key: string;
  label: string;
  title: string;
  description: string;
  item?: LibraryItem;
}

interface DormantGemEntry {
  key: string;
  label: string;
  title: string;
  reason: string;
  item: LibraryItem;
}

const CARDS: DiscoveryCardData[] = [
  {
    id: 'acad-hero',
    category: 'Academic',
    family: 'THESIS RECON',
    title: 'Architectural Semiotics in High-Density Urbanism',
    summary: 'A deep dive into the subliminal messaging of Brutalist facades in neo-Tokyo environments...',
    sources: ['ArXiv', 'Oxford'],
    size: 'hero',
    tone: 'blue',
    icon: GraduationCap,
    metadata: 'LEVEL: ALPHA',
    sourceUrl: 'https://arxiv.org/search/?query=architectural+semiotics+urbanism&searchtype=all',
  },
  {
    id: 'acad-det-1',
    category: 'Academic',
    family: 'BRIDGE',
    title: 'Neural Mapping of the Void',
    summary: 'Connecting LLM attention maps with traditional cognitive psychology.',
    sources: ['Nature', 'MIT'],
    size: 'detail',
    tone: 'blue',
    icon: Activity,
    metadata: 'SYNC: 0.882',
    sourceUrl: 'https://scholar.google.com/scholar?q=LLM+attention+maps+cognitive+psychology',
  },
  {
    id: 'acad-det-2',
    category: 'Academic',
    family: 'LIT_SCAN',
    title: 'VERSE_X4',
    summary: '01001100 01001111 01010110 01000101',
    sources: ['Project Gutenberg'],
    size: 'detail',
    tone: 'purple',
    icon: ScrollText,
    sourceUrl: 'https://www.gutenberg.org/',
  },
  {
    id: 'rel-hero',
    category: 'Religious',
    family: 'DIGITAL SANCTUM',
    title: 'Interlocking Textual Traditions',
    summary: 'Analyzing the thematic continuity between early manuscript fragments and modern scholarship.',
    sources: ['QuranEnc', 'Diyanet'],
    size: 'hero',
    tone: 'green',
    icon: ScrollText,
    metadata: 'SIGIL_LEVEL: ALPHA',
    sourceUrl: 'https://quranenc.com/en/browse/turkish_rshd',
  },
  {
    id: 'rel-det-1',
    category: 'Religious',
    family: 'AYET_RECON',
    title: 'The Syntax of Light',
    summary: 'A deep dive into the linguistic structure of Surah An-Nur.',
    sources: ['HadeethEnc'],
    size: 'detail',
    tone: 'green',
    icon: ScrollText,
    sourceUrl: 'https://hadeethenc.com/tr/browse/hadith',
  },
  {
    id: 'lit-hero',
    category: 'Literary',
    family: 'NEUROMANCER_REVISITED',
    title: 'The Sky Above The Port',
    summary: 'Tracing the influence of Gibsonian cyberpunk on modern urban semiotics.',
    sources: ['Library', 'Archive'],
    size: 'hero',
    tone: 'purple',
    icon: FlaskConical,
    sourceUrl: 'https://archive.org/search?query=neuromancer+cyberpunk',
  },
  {
    id: 'lit-det-1',
    category: 'Literary',
    family: 'AUTHOR_FEED',
    title: 'Dostoevsky & The Machine',
    summary: 'How existential dread translates to algorithmic uncertainty.',
    sources: ['Local Archive'],
    size: 'detail',
    tone: 'purple',
    icon: Library,
    sourceUrl: 'https://www.gutenberg.org/ebooks/author/314',
  },
  {
    id: 'cul-hero',
    category: 'Culture',
    family: 'TRAFFIC_VOL',
    title: 'Mosaic Feed Sync: Silk Road',
    summary: 'Visualizing the migration of motifs from Persia to East Asia over 3 centuries.',
    sources: ['British Museum', 'UNESCO'],
    size: 'hero',
    tone: 'amber',
    icon: Activity,
    syncRate: '+12.4%',
    sourceUrl: 'https://www.britishmuseum.org/collection/search?keyword=silk+road+mosaic',
  },
  {
    id: 'cul-det-1',
    category: 'Culture',
    family: 'ARCHIVE_SYNC',
    title: 'Lost Tones of the Mediterranean',
    summary: 'Recovered audio artifacts from 19th-century folk music collections.',
    sources: ['Europeana'],
    size: 'detail',
    tone: 'amber',
    icon: Sparkles,
    sourceUrl: 'https://www.europeana.eu/en/search?query=mediterranean+folk+music',
  },
];

const buildFallbackInnerSpaceCards = (): DiscoveryCardData[] => [
  {
    id: 'fallback-continue',
    category: 'Personal',
    family: 'CONTINUE THIS',
    slot: 'continue_this',
    title: 'Your archive is ready for a first thread',
    summary: 'Add a book, article, note, or film to start building an active continuation lane here.',
    sources: ['Local Library'],
    size: 'tall',
    tone: 'cyan',
    icon: Activity,
    promptSeed: 'Suggest the best next item to add to my archive so Discovery can start connecting themes.',
  },
  {
    id: 'fallback-latest',
    category: 'Personal',
    family: 'LATEST SYNC',
    slot: 'latest_sync',
    title: 'No recent sync yet',
    summary: 'As soon as new library activity lands, the freshest thread will appear here with direct context.',
    sources: ['Recent Activity'],
    size: 'hero',
    tone: 'purple',
    icon: Sparkles,
    promptSeed: 'Show me the most recent meaningful changes in my archive.',
  },
  {
    id: 'fallback-dormant',
    category: 'Personal',
    family: 'DORMANT GEM',
    slot: 'dormant_gem',
    title: 'Dormant links will surface here',
    summary: 'Once older material accumulates, Discovery will recover overlooked items that still fit your current themes.',
    sources: ['Archive Vault'],
    size: 'detail',
    tone: 'dark',
    icon: FlaskConical,
    promptSeed: 'Find an older item in my archive that is still worth resurfacing.',
  },
  {
    id: 'fallback-pulse',
    category: 'Personal',
    family: 'THEME PULSE',
    slot: 'theme_pulse',
    title: 'THEME_PULSE',
    summary: 'Theme pulse will strengthen as more tagged material and memory profile signals accumulate.',
    sources: ['Recent Archive'],
    size: 'detail',
    tone: 'cyan',
    icon: Zap,
    promptSeed: 'Map the strongest active themes in my recent archive and show the best next connections.',
  },
];

const mapInnerSpaceCard = (card: DiscoveryInnerSpaceCard): DiscoveryCardData => {
  const config: Record<DiscoveryInnerSpaceCard['slot'], Pick<DiscoveryCardData, 'size' | 'tone' | 'icon'>> = {
    continue_this: { size: 'tall', tone: 'cyan', icon: Activity },
    latest_sync: { size: 'hero', tone: 'purple', icon: Sparkles },
    dormant_gem: { size: 'detail', tone: 'dark', icon: FlaskConical },
    theme_pulse: { size: 'detail', tone: 'cyan', icon: Zap },
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

type ExternalCategoryKey = 'ACADEMIC' | 'RELIGIOUS' | 'LITERARY' | 'CULTURE_HISTORY';

interface DiscoveryPageCacheEntry {
  userId: string;
  fetchedAt: number;
  payload: DiscoveryPageResponse;
}

const categoryVisuals: Record<ExternalCategoryKey, Pick<DiscoveryCardData, 'category' | 'tone'>> = {
  ACADEMIC: { category: 'Academic', tone: 'blue' },
  RELIGIOUS: { category: 'Religious', tone: 'green' },
  LITERARY: { category: 'Literary', tone: 'purple' },
  CULTURE_HISTORY: { category: 'Culture', tone: 'amber' },
};

const categoryIcons: Record<ExternalCategoryKey, React.ComponentType<{ size?: number; className?: string }>> = {
  ACADEMIC: GraduationCap,
  RELIGIOUS: ScrollText,
  LITERARY: Library,
  CULTURE_HISTORY: Sparkles,
};

const fallbackPillarsByCategory = (category: ExternalCategoryKey): DiscoveryCardData[] =>
  CARDS.filter((card) => card.category === categoryVisuals[category].category);

const createEmptyPillarState = (): Record<ExternalCategoryKey, DiscoveryCardData[]> => ({
  ACADEMIC: [],
  RELIGIOUS: [],
  LITERARY: [],
  CULTURE_HISTORY: [],
});

let discoveryPageMemoryCache: DiscoveryPageCacheEntry | null = null;

const readDiscoveryPageCache = (userId: string): DiscoveryPageCacheEntry | null => {
  if (discoveryPageMemoryCache?.userId === userId) {
    return discoveryPageMemoryCache;
  }
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(DISCOVERY_PAGE_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DiscoveryPageCacheEntry;
    if (!parsed || parsed.userId !== userId || !parsed.payload || !parsed.fetchedAt) {
      return null;
    }
    const ageMs = Date.now() - parsed.fetchedAt;
    if (ageMs > DISCOVERY_PAGE_CACHE_MAX_STALE_MS) {
      window.sessionStorage.removeItem(DISCOVERY_PAGE_CACHE_KEY);
      return null;
    }
    discoveryPageMemoryCache = parsed;
    return parsed;
  } catch {
    return null;
  }
};

const writeDiscoveryPageCache = (entry: DiscoveryPageCacheEntry): void => {
  discoveryPageMemoryCache = entry;
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(DISCOVERY_PAGE_CACHE_KEY, JSON.stringify(entry));
  } catch {
    // ignore cache write failures
  }
};

const normalizeDiscoveryTagKey = (value: string): string => value.trim().toLocaleLowerCase('tr-TR');

const buildTopNodesFromLibrary = (items: LibraryItem[]): DiscoveryTopNode[] => {
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

const formatRelativeUpdateTime = (value: string | null): string => {
  if (!value) return 'Update unavailable';
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return 'Update unavailable';
  const deltaMs = Date.now() - parsed;
  if (deltaMs < 60_000) return 'Updated just now';
  if (deltaMs < 3_600_000) return `Updated ${Math.max(1, Math.floor(deltaMs / 60_000))}m ago`;
  if (deltaMs < 86_400_000) return `Updated ${Math.max(1, Math.floor(deltaMs / 3_600_000))}h ago`;
  return `Updated ${Math.max(1, Math.floor(deltaMs / 86_400_000))}d ago`;
};

const compactWhySeen = (value?: string): string | null => {
  const cleaned = String(value || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return null;
  if (cleaned.length <= 110) return cleaned;
  return `${cleaned.slice(0, 107).trimEnd()}...`;
};

const compactEvidenceValue = (value?: string | null, limit = 260): string | null => {
  const cleaned = String(value || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return null;
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, limit - 3).trimEnd()}...`;
};

const DAY_MS = 24 * 60 * 60 * 1000;
const DORMANT_MIN_AGE_MS = 21 * DAY_MS;

const normalizeItemTimestamp = (value?: number): number | null => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  return numeric < 1_000_000_000_000 ? numeric * 1000 : numeric;
};

const formatArchiveAge = (value?: number): string => {
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

  if (item.type === 'BOOK') {
    return `${item.author || 'Unknown author'} · added ${relativeAge}`;
  }

  if (item.type === 'ARTICLE') {
    return `${item.publisher || item.author || 'Saved article'} · added ${relativeAge}`;
  }

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

const buildLatestSyncEntries = (items: LibraryItem[]): LatestSyncEntry[] => {
  const latestBook = pickMostRecentItem(items, (item) => item.type === 'BOOK');
  const latestCinema = pickMostRecentItem(items, (item) => item.type === 'MOVIE' || item.type === 'SERIES');
  const latestArticle = pickMostRecentItem(items, (item) => item.type === 'ARTICLE');
  const latestPersonalNote = pickMostRecentItem(
    items,
    (item) => item.type === 'PERSONAL_NOTE' && ['IDEAS', 'DAILY'].includes(getPersonalNoteCategory(item)),
  );

  return [
    {
      key: 'latest-book',
      label: 'Latest Book',
      title: latestBook?.title || 'No recent book',
      description: buildLatestSyncDescription(latestBook, 'book sync'),
      item: latestBook,
    },
    {
      key: 'latest-cinema',
      label: 'Latest Cinema',
      title: latestCinema?.title || 'No recent cinema',
      description: buildLatestSyncDescription(latestCinema, 'cinema sync'),
      item: latestCinema,
    },
    {
      key: 'latest-article',
      label: 'Latest Article',
      title: latestArticle?.title || 'No recent article',
      description: buildLatestSyncDescription(latestArticle, 'article sync'),
      item: latestArticle,
    },
    {
      key: 'latest-note',
      label: 'Latest Personal Note',
      title: latestPersonalNote?.title || 'No recent note',
      description: buildLatestSyncDescription(latestPersonalNote, 'personal note sync'),
      item: latestPersonalNote,
    },
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
  if (highlightCount > 0) {
    return `${highlightCount} saved highlight${highlightCount === 1 ? '' : 's'} but it has stayed quiet for ${quietWindow}.`;
  }

  if (item.summaryText || item.generalNotes) {
    return `You already captured context for it, but it has stayed buried for ${quietWindow}.`;
  }

  if ((item.tags?.length || 0) > 0) {
    return `Tagged around ${item.tags.slice(0, 2).join(' / ')}, but it has not resurfaced for ${quietWindow}.`;
  }

  if ((item.rating || 0) >= 4) {
    return `A strong-rated archive pick that has been quiet for ${quietWindow}.`;
  }

  return `It has been sitting in the archive for ${quietWindow} without resurfacing.`;
};

const buildDormantGemEntries = (items: LibraryItem[]): DormantGemEntry[] => {
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

      return {
        key,
        label,
        title: candidate.title,
        reason: buildDormantReason(candidate),
        item: candidate,
      } satisfies DormantGemEntry;
    })
    .filter((entry): entry is DormantGemEntry => Boolean(entry));
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

const mapBoardResponseToCards = (board: DiscoveryPageResponse['boards']['academic'], category: ExternalCategoryKey): DiscoveryCardData[] => {
  const cards: DiscoveryCardData[] = [];
  if (board.featured_card) {
    cards.push(mapBoardCard(category, board.featured_card, 'hero'));
  }
  board.family_sections.forEach((section, sectionIndex) => {
    section.cards.forEach((card, cardIndex) => {
      const size: DiscoveryCardSize = sectionIndex === 0 && cardIndex === 0 ? 'detail' : 'detail';
      cards.push(mapBoardCard(category, card, size));
    });
  });
  return cards;
};

const mapDiscoveryPagePayload = (payload: DiscoveryPageResponse): {
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

const limitPillarCardsForLayout = (
  pillars: Record<ExternalCategoryKey, DiscoveryCardData[]>,
): Record<ExternalCategoryKey, DiscoveryCardData[]> => ({
  ACADEMIC: pillars.ACADEMIC.slice(0, 3),
  RELIGIOUS: pillars.RELIGIOUS.slice(0, 1),
  LITERARY: pillars.LITERARY.slice(0, 2),
  CULTURE_HISTORY: pillars.CULTURE_HISTORY.slice(0, 2),
});

const cardStyles = (tone: DiscoveryTone) => {
  switch (tone) {
    case 'blue': return 'bg-blue-600/5 dark:bg-blue-600/5 border-blue-500/10 dark:border-blue-500/10 text-slate-900 dark:text-blue-50 shadow-[0_4px_24px_-10px_rgba(59,130,246,0.1)] backdrop-blur-md';
    case 'green': return 'bg-emerald-600/5 dark:bg-emerald-600/5 border-emerald-500/10 dark:border-emerald-500/10 text-slate-900 dark:text-emerald-50 shadow-[0_4px_24px_-10px_rgba(16,185,129,0.1)] backdrop-blur-md';
    case 'purple': return 'bg-purple-600/5 dark:bg-purple-600/5 border-purple-500/10 dark:border-purple-500/10 text-slate-900 dark:text-purple-50 shadow-[0_4px_24px_-10px_rgba(168,85,247,0.1)] backdrop-blur-md';
    case 'amber': return 'bg-amber-600/5 dark:bg-amber-600/5 border-amber-500/10 dark:border-amber-500/10 text-slate-900 dark:text-amber-50 shadow-[0_4px_24px_-10px_rgba(245,158,11,0.1)] backdrop-blur-md';
    case 'cyan': return 'bg-cyan-600/5 dark:bg-cyan-600/5 border-cyan-500/10 dark:border-cyan-500/10 text-slate-900 dark:text-cyan-50 shadow-[0_4px_24px_-10px_rgba(6,182,212,0.1)] backdrop-blur-md';
    case 'dark': return 'bg-white/40 dark:bg-slate-900/40 border-black/5 dark:border-white/5 text-slate-900 dark:text-slate-100 shadow-xl backdrop-blur-2xl';
    default: return 'bg-white/40 dark:bg-white/[0.03] border-black/5 dark:border-white/5 text-slate-900 dark:text-white backdrop-blur-sm';
  }
};

const canOpenCard = (card?: DiscoveryCardData): boolean => Boolean(card && (card.sourceUrl || card.itemId || card.flowAnchorLabel));

const primaryCardActionLabel = (card: DiscoveryCardData): string => {
  if (card.sourceUrl) return 'OPEN_SOURCE';
  if (card.itemId) return 'OPEN_THREAD';
  return 'ASK_ARCHIVE';
};

const CardSurface: React.FC<{
  card: DiscoveryCardData;
  onAsk: (card: DiscoveryCardData) => void;
  onSave: (card: DiscoveryCardData) => void;
  onOpen?: (card: DiscoveryCardData) => void;
  className?: string;
}> = ({ card, onAsk, onSave, onOpen, className }) => {
  const isHero = card.size === 'hero';
  const isTall = card.size === 'tall';
  const isWide = card.size === 'wide';
  const isDormant = card.family === 'DORMANT GEM';
  const canOpen = canOpenCard(card);
  const showHeroMedia = isHero && card.category !== 'Religious';
  const showWhySeen = (card.category === 'Academic' || card.category === 'Literary' || card.category === 'Culture') && !card.slot;
  const whySeen = showWhySeen ? compactWhySeen(card.whySeen) : null;
  const RELIGIOUS_NO_TRUNCATE = new Set(['Tefsir', 'Meal']);
  const religiousEvidence = card.category === 'Religious'
    ? ['Arabic', 'Okunus', 'Meal', 'Tefsir']
        .map((label) => ({
          label,
          value: RELIGIOUS_NO_TRUNCATE.has(label)
            ? (card.evidence?.find((item) => item.label === label)?.value?.replace(/\s+/g, ' ').trim() || null)
            : compactEvidenceValue(
                card.evidence?.find((item) => item.label === label)?.value,
                label === 'Arabic' ? 420 : 260,
              ),
        }))
        .filter((item): item is { label: string; value: string } => Boolean(item.value))
    : [];
  const cultureEvidence = card.category === 'Culture'
    ? ['Collection', 'Artist', 'Creator', 'Country', 'Type', 'Context', 'Part of']
        .map((label) => ({
          label,
          value: compactEvidenceValue(card.evidence?.find((item) => item.label === label)?.value, 120),
        }))
        .filter((item): item is { label: string; value: string } => Boolean(item.value))
        .slice(0, 3)
    : [];

  const gridClasses = className || `
    ${isHero ? 'md:col-span-2 md:row-span-2 min-h-[480px]' : ''}
    ${isTall ? 'md:row-span-2 min-h-[420px]' : ''}
    ${isWide ? 'md:col-span-2 min-h-[220px]' : ''}
    ${card.size === 'detail' ? 'min-h-[220px]' : ''}
  `;

  return (
    <motion.article
      whileHover={{ scale: 1.01, y: -2 }}
      className={`relative group flex flex-col p-5 rounded-2xl border transition-all duration-300 ${cardStyles(card.tone)} ${gridClasses}`}
    >
      {isDormant && (
        <div className="absolute inset-0 bg-white/[0.02] backdrop-blur-[2px] z-0 pointer-events-none group-hover:backdrop-blur-none transition-all duration-500" />
      )}

      {isHero && (
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none z-0">
          <div className="absolute top-0 right-0 w-64 h-64 border-t border-r border-white/40 translate-x-12 -translate-y-12" />
          <div className="absolute bottom-0 left-0 w-32 h-32 border-b border-l border-white/40 -translate-x-8 translate-y-8" />
        </div>
      )}

      <div className="relative z-10 flex flex-col h-full">
        <div className="flex justify-between items-start mb-6">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-bold tracking-[0.25em] uppercase text-cyan-500 dark:text-cyan-300">
              {card.category}
            </span>
            <span className="text-[10px] font-light italic text-slate-500 dark:text-white/70">
              {card.family}
            </span>
          </div>
          {card.syncRate && (
            <div className="px-2 py-0.5 rounded-full bg-cyan-600/10 dark:bg-cyan-500/10 border border-cyan-600/20 dark:border-cyan-500/20 text-[9px] font-mono text-cyan-700 dark:text-cyan-400">
              {card.syncRate}
            </div>
          )}
        </div>

        {card.imageUrl && (
          <div className="w-full aspect-[21/9] rounded-lg overflow-hidden mb-5 bg-white/[0.02] border border-white/5 relative group-hover:border-white/10 transition-colors">
            <img src={card.imageUrl} alt={card.title} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/60 to-transparent pointer-events-none" />
          </div>
        )}

        <div className="flex-1">
          <h2 className={`font-serif leading-tight mb-4 ${isHero ? 'text-2xl md:text-3xl font-normal text-slate-900 dark:text-white/90' : 'text-lg font-normal text-slate-900 dark:text-white/80'}`}>
            {card.title}
          </h2>
          <p className={isHero ? 'text-sm text-slate-600 dark:text-white/70 leading-relaxed max-w-[48ch] mb-6' : 'text-xs text-slate-600 dark:text-white/70 leading-relaxed max-w-[48ch] mb-6'}>
            {card.summary}
          </p>

          {whySeen && (
            <div className="mb-5 rounded-xl border border-black/5 dark:border-white/6 bg-black/[0.03] dark:bg-white/[0.025] px-3 py-2">
              <p className="text-[10px] leading-relaxed text-slate-600 dark:text-white/75">
                <span className="mr-1 uppercase tracking-[0.18em] text-cyan-600 dark:text-cyan-400">Why:</span>
                {whySeen}
              </p>
            </div>
          )}

          {religiousEvidence.length > 0 && (
            <div className="mb-5 space-y-3">
              {religiousEvidence.map((item) => (
                <div
                  key={item.label}
                  className={`rounded-xl border px-3 py-2 ${
                    item.label === 'Tefsir'
                      ? 'border-emerald-300/14 bg-emerald-500/[0.07] md:px-4 md:py-3'
                      : 'border-emerald-400/10 bg-emerald-500/[0.04]'
                  }`}
                >
                  <div className="mb-1 text-[9px] uppercase tracking-[0.18em] text-emerald-800/70 dark:text-emerald-300/70">
                    {item.label}
                  </div>
                  <p
                    dir={item.label === 'Arabic' ? 'rtl' : undefined}
                    className={
                      item.label === 'Arabic'
                        ? `${isHero ? 'text-lg md:text-xl leading-10' : 'text-sm leading-8'} text-right text-emerald-900/95 dark:text-emerald-50/95`
                        : item.label === 'Tefsir'
                          ? `${isHero ? 'text-sm md:text-[15px]' : 'text-[11px]'} leading-7 text-slate-800 dark:text-white/72`
                          : `${isHero ? 'text-sm' : 'text-[11px]'} leading-relaxed text-slate-700 dark:text-white/62`
                    }
                  >
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          )}

          {cultureEvidence.length > 0 && (
            <div className="mb-5 flex flex-wrap gap-2">
              {cultureEvidence.map((item) => (
                <div key={item.label} className="rounded-full border border-amber-300/12 bg-amber-500/[0.06] px-3 py-1.5">
                  <span className="mr-2 text-[9px] uppercase tracking-[0.18em] text-amber-800/80 dark:text-amber-200/55">{item.label}</span>
                  <span className="text-[11px] text-slate-800 dark:text-white/70">{item.value}</span>
                </div>
              ))}
            </div>
          )}

          {card.progress !== undefined && (
            <div className="relative w-20 h-20 mb-6">
              <svg className="w-full h-full transform -rotate-90">
                <circle cx="40" cy="40" r="36" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-black/5 dark:text-white/5" />
                <circle
                  cx="40"
                  cy="40"
                  r="36"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="transparent"
                  strokeDasharray={226.08}
                  strokeDashoffset={226.08 - (226.08 * card.progress) / 100}
                  className="text-cyan-400 transition-all duration-1000"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-xs font-bold">{card.progress}%</span>
              </div>
            </div>
          )}




        </div>
 
        <div className="mt-auto pt-4 flex items-center justify-between border-t border-black/5 dark:border-white/5">
          <div className="flex items-center gap-4">
            <button onClick={() => onAsk(card)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest hover:text-cyan-400 transition-colors">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button onClick={() => onSave(card)} className="opacity-40 hover:opacity-100 transition-opacity">
              <BookmarkPlus size={14} />
            </button>
          </div>

          {card.metadata && (
            <div className="text-[9px] uppercase tracking-[0.2em] font-medium text-cyan-700/60 dark:text-cyan-400/40 italic">
              {card.metadata}
            </div>
          )}
          <button
            type="button"
            onClick={() => (onOpen ? onOpen(card) : onAsk(card))}
            disabled={!canOpen}
            className={`transition-opacity ${canOpen ? 'opacity-20 group-hover:opacity-100' : 'opacity-10 cursor-not-allowed'}`}
            aria-label={
              card.sourceUrl
                ? `Open source for ${card.title}`
                : card.itemId
                  ? `Open ${card.title}`
                  : card.flowAnchorLabel
                    ? `Open related flow for ${card.title}`
                    : `Ask about ${card.title}`
            }
          >
            <ArrowUpRight size={14} />
          </button>
        </div>
      </div>
    </motion.article>
  );
};

const InnerSpaceMiniCard: React.FC<{
  card: DiscoveryCardData;
  dormantEntries?: DormantGemEntry[];
  onAsk: (card: DiscoveryCardData) => void;
  onOpen: (card: DiscoveryCardData) => void;
  onOpenItem: (item: LibraryItem) => void;
}> = ({ card, dormantEntries = [], onAsk, onOpen, onOpenItem }) => {
  const canOpen = canOpenCard(card);
  const isDormant = card.slot === 'dormant_gem';

  return (
    <div className="rounded-2xl border border-black/5 dark:border-white/6 bg-white/40 dark:bg-white/[0.025] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[9px] uppercase tracking-[0.24em] text-cyan-700 dark:text-cyan-400">{card.family}</p>
          <p className="mt-2 text-base font-serif text-slate-900 dark:text-white/90">{card.title}</p>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-white/75">{card.summary}</p>
          {isDormant && dormantEntries.length > 0 ? (
            <div className="mt-4 space-y-3">
              {dormantEntries.map((entry) => (
                <div key={entry.key} className="rounded-xl border border-black/5 dark:border-white/6 bg-black/5 dark:bg-black/10 px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[9px] uppercase tracking-[0.22em] text-amber-800 dark:text-amber-300">{entry.label}</p>
                      <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white/85">{entry.title}</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-slate-600 dark:text-white/75">{entry.reason}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onOpenItem(entry.item)}
                      className="shrink-0 rounded-full border border-black/10 dark:border-white/10 px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500 dark:text-white/60 transition hover:border-cyan-500/30 dark:hover:border-cyan-400/30 hover:text-cyan-600 dark:hover:text-cyan-300"
                    >
                      Open
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {card.metadata ? (
            <p className="mt-3 text-[9px] uppercase tracking-[0.22em] text-slate-500 dark:text-white/25">{card.metadata}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => (canOpen ? onOpen(card) : onAsk(card))}
          className={`shrink-0 rounded-full border px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.18em] transition ${
            canOpen
              ? 'border-black/10 dark:border-white/10 text-slate-500 dark:text-white/55 hover:border-cyan-500/30 dark:hover:border-cyan-400/30 hover:text-cyan-600 dark:hover:text-cyan-300'
              : 'border-black/5 dark:border-white/5 text-slate-400 dark:text-white/25 hover:text-slate-600 dark:hover:text-white/45'
          }`}
        >
          {canOpen ? 'Open' : 'Ask'}
        </button>
      </div>
    </div>
  );
};

const InnerSpaceCluster: React.FC<{
  latestCard: DiscoveryCardData;
  dormantCard?: DiscoveryCardData;
  themePulseCard?: DiscoveryCardData;
  topNodes: DiscoveryTopNode[];
  latestEntries: LatestSyncEntry[];
  dormantEntries: DormantGemEntry[];
  onAsk: (card: DiscoveryCardData) => void;
  onSave: (card: DiscoveryCardData) => void;
  onOpen: (card: DiscoveryCardData) => void;
  onOpenItem: (item: LibraryItem) => void;
}> = ({
  latestCard,
  dormantCard,
  themePulseCard,
  topNodes,
  latestEntries,
  dormantEntries,
  onAsk,
  onSave,
  onOpen,
  onOpenItem,
}) => {
  const latestCanOpen = canOpenCard(latestCard);
  const pulseBadge = topNodes.length > 0
    ? `${topNodes.length} top node${topNodes.length === 1 ? '' : 's'}`
    : themePulseCard?.syncRate;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.8fr] gap-4 auto-rows-fr">
      <motion.article
        whileHover={{ scale: 1.005, y: -2 }}
        className={`relative flex min-h-[420px] flex-col rounded-2xl border p-5 transition-all duration-300 ${cardStyles('purple')}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-cyan-600 dark:text-cyan-300">{latestCard.family}</p>
            {latestCard.sources.length > 0 ? (
              <p className="mt-2 text-[10px] italic text-slate-500 dark:text-white/75">{latestCard.sources.join(' // ')}</p>
            ) : null}
          </div>
          {latestCard.progress !== undefined ? (
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-cyan-400/20 bg-cyan-500/5 text-sm font-bold text-cyan-300">
              {latestCard.progress}%
            </div>
          ) : null}
        </div>







        <div className="mt-8 grid grid-cols-1 gap-3 xl:grid-cols-2">
          {latestEntries.map((entry) => (
            <div key={entry.key} className="rounded-2xl border border-white/6 bg-white/[0.025] px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[9px] uppercase tracking-[0.24em] text-cyan-600 dark:text-cyan-300">{entry.label}</p>
                  <p className="mt-2 text-base font-serif text-slate-900 dark:text-white/90">{entry.title}</p>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-white/75">{entry.description}</p>
                </div>
                {entry.item ? (
                  <button
                    type="button"
                    onClick={() => onOpenItem(entry.item)}
                    className="shrink-0 rounded-full border border-black/10 dark:border-white/10 px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500 dark:text-white/60 transition hover:border-cyan-500/30 dark:hover:border-cyan-400/30 hover:text-cyan-600 dark:hover:text-cyan-300"
                  >
                    Open
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>

        {dormantCard ? (
          <div className="mt-4">
            <InnerSpaceMiniCard
              card={dormantCard}
              dormantEntries={dormantEntries}
              onAsk={onAsk}
              onOpen={onOpen}
              onOpenItem={onOpenItem}
            />
          </div>
        ) : null}

        <div className="mt-auto flex items-center justify-between border-t border-white/5 pt-4">
          <div className="flex items-center gap-3">
            <button onClick={() => onAsk(latestCard)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest transition-colors hover:text-cyan-400">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button onClick={() => onSave(latestCard)} className="opacity-40 transition-opacity hover:opacity-100 text-slate-900 dark:text-white">
              <BookmarkPlus size={14} />
            </button>
          </div>
          <button
            type="button"
            onClick={() => (latestCanOpen ? onOpen(latestCard) : onAsk(latestCard))}
            className={`rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] transition ${
              latestCanOpen
                ? 'border-cyan-400/25 bg-cyan-500/90 dark:bg-cyan-500 text-white dark:text-black hover:bg-cyan-600 dark:hover:bg-cyan-400 shadow-lg shadow-cyan-500/20'
                : 'border-black/8 dark:border-white/8 bg-black/5 dark:bg-white/5 text-slate-600 dark:text-white/55 hover:bg-black/10 dark:hover:bg-white/10'
            }`}
          >
            {primaryCardActionLabel(latestCard)}
          </button>
        </div>
      </motion.article>

      {themePulseCard ? (
        <motion.article
          whileHover={{ scale: 1.005, y: -2 }}
          className={`relative flex min-h-[420px] flex-col rounded-2xl border p-5 transition-all duration-300 ${cardStyles('dark')}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-cyan-400/80">{themePulseCard.family}</p>
              <p className="text-[10px] italic text-slate-500 dark:text-white/40">
                {topNodes.length > 0 ? 'Dashboard // Top Nodes' : themePulseCard.sources.join(' // ')}
              </p>
            </div>
            {pulseBadge ? (
              <div className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-mono text-cyan-400">
                {pulseBadge}
              </div>
            ) : null}
          </div>

          <div className="mt-6">
            <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500 dark:text-white/24">Personal</p>
            <h3 className="mt-2 font-serif text-2xl leading-tight text-slate-900/92 dark:text-white/92">Top Nodes</h3>
          </div>

          {topNodes.length > 0 ? (
            <div className="mt-6 space-y-3">
              {topNodes.map((node) => (
                <div key={node.label} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-800 dark:text-white/75">
                    <span className="truncate">{node.label}</span>
                    <span className="shrink-0 text-slate-500 dark:text-white/35">{node.count}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-black/5 dark:bg-white/5">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(node.count / topNodes[0].count) * 100}%` }}
                      className="h-full bg-cyan-400/70"
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-6 text-sm leading-relaxed text-slate-700 dark:text-white/45">{themePulseCard.summary}</p>
          )}

          {themePulseCard.metadata ? (
            <p className="mt-6 text-[10px] uppercase tracking-[0.24em] text-slate-500 dark:text-white/22">{themePulseCard.metadata}</p>
          ) : null}

          <div className="mt-auto flex items-center justify-between border-t border-black/5 dark:border-white/5 pt-4">
            <button onClick={() => onAsk(themePulseCard)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest transition-colors hover:text-cyan-400">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button
              type="button"
              onClick={() => onAsk(themePulseCard)}
              className="rounded-full border border-black/10 dark:border-white/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500 dark:text-white/70 transition hover:border-cyan-500/25 dark:hover:border-cyan-400/25 hover:text-cyan-600 dark:hover:text-cyan-300"
            >
              Focus Map
            </button>
          </div>
        </motion.article>
      ) : null}
    </div>
  );
};

const InnerSpaceLoadingGrid: React.FC = () => (
  <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.8fr] gap-4 auto-rows-fr">
    {[0, 1].map((index) => (
      <div
        key={index}
        className={`${index === 0 ? 'min-h-[420px]' : 'min-h-[420px]'} rounded-2xl border border-black/5 dark:border-white/5 bg-black/[0.02] dark:bg-white/[0.02] animate-pulse`}
      />
    ))}
  </div>
);

export const DiscoveryHome: React.FC<DiscoveryHomeProps> = ({
  userId,
  books,
  onTabChange,
  onQuickCreatePersonalNote,
  onOpenDiscoveryItem,
  onMobileMenuClick,
}) => {
  const [innerSpaceCards, setInnerSpaceCards] = useState<DiscoveryCardData[]>([]);
  const [pillarCardsByCategory, setPillarCardsByCategory] = useState<Record<ExternalCategoryKey, DiscoveryCardData[]>>(
    () => createEmptyPillarState(),
  );
  const [pageLoading, setPageLoading] = useState(true);
  const [pageWarning, setPageWarning] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [viewMeta, setViewMeta] = useState<DiscoveryViewMeta>({
    lastUpdatedAt: null,
    hasCachedSnapshot: false,
    hasPartialErrors: false,
    boardErrorCount: 0,
  });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const forceRefreshRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const lastAutoRefreshAtRef = useRef(0);
  const topNodes = useMemo(() => buildTopNodesFromLibrary(books), [books]);
  const latestSyncEntries = useMemo(() => buildLatestSyncEntries(books), [books]);
  const dormantGemEntries = useMemo(() => buildDormantGemEntries(books), [books]);

  const triggerRefresh = (force = false) => {
    if (!userId || requestInFlightRef.current) {
      return;
    }
    forceRefreshRef.current = force;
    setIsRefreshing(true);
    setRefreshNonce((value) => value + 1);
  };

  useEffect(() => {
    let active = true;

    const loadPage = async () => {
      // Avoid overlapping requests in the same component lifecycle
      if (requestInFlightRef.current) return;
      
      requestInFlightRef.current = true;
      const forceRefresh = forceRefreshRef.current;
      forceRefreshRef.current = false;

      if (!userId) {
        if (active) {
          setPageLoading(false);
          setPageWarning(null);
          setPageError(null);
          setIsRefreshing(false);
          setInnerSpaceCards([]);
          setPillarCardsByCategory(createEmptyPillarState());
        }
        requestInFlightRef.current = false;
        return;
      }

      // 1. Snapshot/Cache Recovery
      const cached = readDiscoveryPageCache(userId);
      const cacheIsFresh = !forceRefresh && Boolean(cached && (Date.now() - cached.fetchedAt) < DISCOVERY_PAGE_CACHE_TTL_MS);
      
      if (cached && active && !forceRefresh) {
        const mapped = mapDiscoveryPagePayload(cached.payload);
        setInnerSpaceCards(mapped.innerSpace);
        setPillarCardsByCategory(limitPillarCardsForLayout(mapped.pillars));
        setPageWarning(mapped.warning);
        setViewMeta({
          ...mapped.meta,
          hasCachedSnapshot: true,
        });
        setPageLoading(false);
      } else if (active) {
        setPageLoading(true);
      }

      // 2. Short-circuit if cache is still fresh enough for this view
      if (cacheIsFresh) {
        setPageError(null);
        setIsRefreshing(false);
        requestInFlightRef.current = false;
        return;
      }

      // 3. Live Fetch Cycle
      try {
        const payload = await getDiscoveryPage(
          userId,
          forceRefresh,
          forceRefresh ? String(Date.now()) : undefined,
        );
        if (!active) return;

        writeDiscoveryPageCache({
          userId,
          fetchedAt: Date.now(),
          payload,
        });

        const mapped = mapDiscoveryPagePayload(payload);
        setInnerSpaceCards(mapped.innerSpace);
        setPillarCardsByCategory(limitPillarCardsForLayout(mapped.pillars));
        setPageWarning(mapped.warning);
        setViewMeta(mapped.meta);
        setPageError(null);
      } catch (error) {
        if (!active) return;
        const message = getFriendlyApiErrorMessage(error);
        
        if (cached) {
          setPageWarning('Showing the last successful discovery snapshot while live refresh is unavailable.');
          setViewMeta((prev) => ({
            ...prev,
            hasCachedSnapshot: true,
          }));
          setPageError(null);
        } else {
          setPageError(message);
          setPageWarning(null);
          setInnerSpaceCards([]);
          setPillarCardsByCategory(createEmptyPillarState());
          setViewMeta({
            lastUpdatedAt: null,
            hasCachedSnapshot: false,
            hasPartialErrors: false,
            boardErrorCount: 0,
          });
        }
      } finally {
        requestInFlightRef.current = false;
        if (active) {
          setPageLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    loadPage();
    return () => {
      active = false;
      // Note: We don't reset requestInFlightRef here because if a new component 
      // mounts it gets its own ref. Only global state would need careful reset.
    };
  }, [userId, refreshNonce]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return;
    }

    const handleFocusRefresh = () => {
      if (document.visibilityState === 'hidden' || requestInFlightRef.current) {
        return;
      }

      const cached = userId ? readDiscoveryPageCache(userId) : null;
      if (!cached) return;
      const ageMs = Date.now() - cached.fetchedAt;
      const now = Date.now();
      if (ageMs >= DISCOVERY_PAGE_CACHE_TTL_MS && (now - lastAutoRefreshAtRef.current) >= 15_000) {
        lastAutoRefreshAtRef.current = now;
        triggerRefresh(false);
      }
    };

    window.addEventListener('focus', handleFocusRefresh);
    document.addEventListener('visibilitychange', handleFocusRefresh);
    return () => {
      window.removeEventListener('focus', handleFocusRefresh);
      document.removeEventListener('visibilitychange', handleFocusRefresh);
    };
  }, [userId]);

  const handleAsk = (card: DiscoveryCardData) => {
    if (card.promptSeed) {
      persistDiscoveryPromptSeed(card.promptSeed);
    }
    onTabChange('RAG_SEARCH');
  };

  const handleSave = (card: DiscoveryCardData) => {
    const noteBody = [
      card.summary,
      card.sources.length > 0 ? `Sources: ${card.sources.join(' / ')}` : null,
      card.metadata ? `Context: ${card.metadata}` : null,
    ].filter(Boolean).join('\n\n');

    onQuickCreatePersonalNote({
      title: `Discovery: ${card.title}`,
      content: noteBody,
      category: 'IDEAS',
    });
  };

  const handleOpen = (card: DiscoveryCardData) => {
    if (card.sourceUrl) {
      window.open(card.sourceUrl, '_blank', 'noopener,noreferrer');
      return;
    }

    if (card.itemId) {
      const item = books.find((entry) => entry.id === card.itemId);
      if (item) {
        onOpenDiscoveryItem(item, card.focusHint || 'info');
        return;
      }
    }

    if (card.flowAnchorLabel) {
      persistDiscoveryFlowSeed({
        anchorId: card.flowAnchorId || card.title,
        anchorLabel: card.flowAnchorLabel,
      });
      onTabChange('FLOW');
      return;
    }

    handleAsk(card);
  };

  const handleOpenLibraryItem = (item: LibraryItem) => {
    onOpenDiscoveryItem(item, 'info');
  };

  const academicCards = pillarCardsByCategory.ACADEMIC;
  const religiousCards = pillarCardsByCategory.RELIGIOUS;
  const literaryCards = pillarCardsByCategory.LITERARY;
  const cultureCards = pillarCardsByCategory.CULTURE_HISTORY;

  const academicHero = academicCards[0];
  const academicDetail = academicCards[1];
  const religiousHero = religiousCards[0];
  const literaryHero = literaryCards[0];
  const literaryDetail = literaryCards[1];
  const cultureHero = cultureCards[0];
  const cultureDetail = cultureCards[1];
  const hasAnyPillarCards = [academicCards, religiousCards, literaryCards, cultureCards].some((cards) => cards.length > 0);
  const continueCard = innerSpaceCards.find((card) => card.slot === 'continue_this') || innerSpaceCards[0];
  const latestSyncCard = innerSpaceCards.find((card) => card.slot === 'latest_sync');
  const dormantGemCard = innerSpaceCards.find((card) => card.slot === 'dormant_gem');
  const themePulseCard = innerSpaceCards.find((card) => card.slot === 'theme_pulse');
  const primaryInnerSpaceCard = useMemo(() => {
    const baseCard = latestSyncCard || continueCard;
    if (!baseCard) return undefined;

    const hasAnyLatestItem = latestSyncEntries.some((entry) => Boolean(entry.item));

    return {
      ...baseCard,
      family: 'LATEST SYNC',
      slot: 'latest_sync' as const,
      title: hasAnyLatestItem ? 'Latest archive sync' : 'No recent sync yet',
      summary: hasAnyLatestItem
        ? 'Fresh signals across book, cinema, article, and personal note lanes.'
        : 'As soon as new library activity lands, the freshest thread will appear here with direct context.',
    };
  }, [continueCard, latestSyncCard, latestSyncEntries]);
  const usedAcademicCount = academicCards.length >= 2 ? 2 : academicCards.length;
  const usedReligiousCount = religiousCards.length >= 1 ? 1 : religiousCards.length;
  const usedLiteraryCount = literaryCards.length >= 2 ? 2 : literaryCards.length;
  const usedCultureCount = cultureCards.length >= 2 ? 2 : cultureCards.length;

  const remainingPillarCards: DiscoveryCardData[] = []; // Enforce strict 2-card limit per pillar

  return (
    <div className="relative min-h-screen bg-[#F7F8FB] dark:bg-[#020408] text-slate-900 dark:text-white overflow-y-auto selection:bg-cyan-500/30">
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 right-0 w-full h-[600px] bg-gradient-to-b from-blue-900/5 dark:from-blue-900/10 via-transparent to-transparent" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(0,0,0,0.05)_1px,transparent_0)] dark:bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.045)_1px,transparent_0)] bg-[size:24px_24px] opacity-[0.07] dark:opacity-[0.07]" />
      </div>

      <div className="relative z-10 max-w-[1700px] mx-auto px-6 lg:px-16 py-8">
        <header className="mb-10">
          <div className="flex flex-col items-center border-b border-black/5 dark:border-white/5 pb-8 text-center relative">
            {/* Mobile Menu Trigger */}
            <button
              onClick={onMobileMenuClick}
              className="lg:hidden absolute left-0 top-1/2 -translate-y-1/2 p-2 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              <Menu size={24} />
            </button>

            <h1 className="text-4xl md:text-5xl font-serif font-light tracking-wide text-slate-900 dark:text-white/90 italic">Discovery</h1>
          </div>
        </header>

        <main>
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <h2 className="text-3xl font-black uppercase tracking-[0.2em] bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-500 dark:from-white dark:to-white/40">Inner Space</h2>
              </div>
            </div>

            {pageError && (
              <div className="mb-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-100/80">
                {pageError}
              </div>
            )}

            {pageWarning && (
              <div className="mb-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-sm text-cyan-100/80">
                {pageWarning}
              </div>
            )}

            {pageLoading && innerSpaceCards.length === 0 ? (
              <InnerSpaceLoadingGrid />
            ) : innerSpaceCards.length > 0 && primaryInnerSpaceCard ? (
              <InnerSpaceCluster
                latestCard={primaryInnerSpaceCard}
                dormantCard={dormantGemCard}
                themePulseCard={themePulseCard}
                topNodes={topNodes}
                latestEntries={latestSyncEntries}
                dormantEntries={dormantGemEntries}
                onAsk={handleAsk}
                onSave={handleSave}
                onOpen={handleOpen}
                onOpenItem={handleOpenLibraryItem}
              />
            ) : (
              <div className="rounded-2xl border border-black/5 dark:border-white/5 bg-white/40 dark:bg-white/[0.02] px-5 py-6 text-sm text-slate-500 dark:text-white/50">
                Discovery could not load inner archive signals yet.
              </div>
            )}
          </div>

          <div className="mt-12">
            <div className="mb-8 flex flex-col gap-4 px-4 pl-6 md:flex-row md:items-end md:justify-between md:border-l-2 md:border-cyan-500/20">
              <div className="flex flex-col items-start">
                <span className="mb-2 text-[10px] font-sans font-light uppercase tracking-[0.4em] text-slate-500 dark:text-white/30 italic">Fundamental Layer</span>
                <h2 className="text-3xl font-serif italic tracking-tight text-slate-800 dark:text-white/80">The Pillars</h2>
                <div className="mt-4 h-[1px] w-32 bg-gradient-to-r from-slate-400/20 dark:from-white/20 to-transparent" />
              </div>
              <div className="flex items-center gap-3">
                <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 dark:text-white/30">
                  {formatRelativeUpdateTime(viewMeta.lastUpdatedAt)}
                </div>
                <button
                  type="button"
                  onClick={() => triggerRefresh(true)}
                  disabled={isRefreshing}
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] transition ${
                    isRefreshing
                      ? 'cursor-wait border-cyan-500/15 dark:border-cyan-400/15 bg-cyan-500/5 dark:bg-cyan-500/10 text-cyan-600 dark:text-cyan-200/60'
                      : 'border-cyan-500/20 dark:border-cyan-400/25 bg-cyan-500/10 dark:bg-cyan-500/15 text-cyan-700 dark:text-cyan-100 hover:border-cyan-500/40 dark:hover:border-cyan-300/40 hover:bg-cyan-500/20 dark:hover:bg-cyan-500/25'
                  }`}
                >
                  <RotateCw size={12} className={isRefreshing ? 'animate-spin' : ''} />
                  {isRefreshing ? 'Refreshing' : 'Refresh Pillars'}
                </button>
              </div>
            </div>

            {pageLoading && !hasAnyPillarCards ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="md:col-span-2 min-h-[280px] rounded-2xl border border-white/5 bg-white/[0.02] animate-pulse" />
                <div className="md:col-span-1 min-h-[280px] rounded-2xl border border-white/5 bg-white/[0.02] animate-pulse" />
              </div>
            ) : null}

            {academicHero && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <CardSurface
                  card={academicHero}
                  onAsk={handleAsk}
                  onSave={handleSave}
                  onOpen={handleOpen}
                  className={`${academicDetail ? "md:col-span-2" : "md:col-span-full"} min-h-[280px]`}
                />
                {academicDetail && (
                  <CardSurface
                    card={academicDetail}
                    onAsk={handleAsk}
                    onSave={handleSave}
                    onOpen={handleOpen}
                    className="md:col-span-1 min-h-[280px]"
                  />
                )}
              </div>
            )}

            {religiousHero && (
              <div className="grid grid-cols-1 gap-4 mb-4">
                <CardSurface
                  card={religiousHero}
                  onAsk={handleAsk}
                  onSave={handleSave}
                  onOpen={handleOpen}
                  className="md:col-span-full min-h-[360px]"
                />
              </div>
            )}

            {literaryHero && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <CardSurface
                  card={literaryHero}
                  onAsk={handleAsk}
                  onSave={handleSave}
                  onOpen={handleOpen}
                  className={`${literaryDetail ? "md:col-span-1" : "md:col-span-full"} min-h-[280px]`}
                />
                {literaryDetail && (
                  <CardSurface
                    card={literaryDetail}
                    onAsk={handleAsk}
                    onSave={handleSave}
                    onOpen={handleOpen}
                    className="md:col-span-1 min-h-[280px]"
                  />
                )}
              </div>
            )}

            {cultureHero && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <CardSurface
                  card={cultureHero}
                  onAsk={handleAsk}
                  onSave={handleSave}
                  onOpen={handleOpen}
                  className={`${cultureDetail ? "md:col-span-1" : "md:col-span-full"} min-h-[280px]`}
                />
                {cultureDetail && (
                  <CardSurface
                    card={cultureDetail}
                    onAsk={handleAsk}
                    onSave={handleSave}
                    onOpen={handleOpen}
                    className="md:col-span-1 min-h-[280px]"
                  />
                )}
              </div>
            )}

            {remainingPillarCards.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {remainingPillarCards.map((card) => (
                  <CardSurface key={card.id} card={card} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[220px]" />
                ))}
              </div>
            ) : null}

            {!pageLoading && !hasAnyPillarCards ? (
              <div className="rounded-2xl border border-black/5 dark:border-white/5 bg-white/40 dark:bg-white/[0.02] px-5 py-6 text-sm text-slate-500 dark:text-white/50">
                Pillars could not load external source cards right now.
              </div>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
};
