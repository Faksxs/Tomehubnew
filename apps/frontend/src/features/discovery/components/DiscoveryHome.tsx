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
} from 'lucide-react';
import type { AppTab } from '../../app/types';
import type { LibraryItem, PersonalNoteCategory } from '../../../types';
import { getFriendlyApiErrorMessage } from '../../../services/apiClient';
import {
  getDiscoveryPage,
  type DiscoveryPageResponse,
  type DiscoveryCard as ExternalDiscoveryCard,
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
  const metadata = [card.primary_source, card.confidence_label].filter(Boolean).join(' · ');
  const syncRate = card.freshness_label || undefined;

  return {
    id: card.id,
    category: visual.category,
    family: card.family,
    title: card.title,
    summary: card.summary,
    sources: card.source_refs.slice(0, 2).map((ref) => ref.label).filter(Boolean),
    size,
    tone: visual.tone,
    icon: categoryIcons[category],
    syncRate,
    metadata,
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
  RELIGIOUS: pillars.RELIGIOUS.slice(0, 2),
  LITERARY: pillars.LITERARY.slice(0, 2),
  CULTURE_HISTORY: pillars.CULTURE_HISTORY.slice(0, 2),
});

const cardStyles = (tone: DiscoveryTone) => {
  switch (tone) {
    case 'blue': return 'bg-blue-600/5 border-blue-500/10 text-blue-50 shadow-[0_4px_24px_-10px_rgba(59,130,246,0.1)] backdrop-blur-md';
    case 'green': return 'bg-emerald-600/5 border-emerald-500/10 text-emerald-50 shadow-[0_4px_24px_-10px_rgba(16,185,129,0.1)] backdrop-blur-md';
    case 'purple': return 'bg-purple-600/5 border-purple-500/10 text-purple-50 shadow-[0_4px_24px_-10px_rgba(168,85,247,0.1)] backdrop-blur-md';
    case 'amber': return 'bg-amber-600/5 border-amber-500/10 text-amber-50 shadow-[0_4px_24px_-10px_rgba(245,158,11,0.1)] backdrop-blur-md';
    case 'cyan': return 'bg-cyan-600/5 border-cyan-500/10 text-cyan-50 shadow-[0_4px_24px_-10px_rgba(6,182,212,0.1)] backdrop-blur-md';
    case 'dark': return 'bg-slate-900/40 border-white/5 text-slate-100 shadow-xl backdrop-blur-2xl';
    default: return 'bg-white/[0.03] border-white/5 text-white backdrop-blur-sm';
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
            <span className="text-[10px] font-medium tracking-[0.2em] uppercase opacity-40 text-cyan-400">
              {card.family}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-light opacity-50 italic">
                {card.sources.join(' // ')}
              </span>
            </div>
          </div>
          {card.syncRate && (
            <div className="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[9px] font-mono text-cyan-400">
              {card.syncRate}
            </div>
          )}
        </div>

        {isHero && (
          <div className="w-full aspect-[21/9] rounded-lg overflow-hidden mb-3 bg-white/[0.02] border border-white/5 relative group-hover:border-white/10 transition-colors">
            <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-50" />
            <div className="absolute inset-0 flex items-center justify-center opacity-10 transform scale-110 rotate-3 group-hover:rotate-0 transition-transform duration-700">
              <card.icon size={40} />
            </div>
          </div>
        )}

        <div className="flex-1">
          <h2 className={`font-serif leading-tight mb-4 ${isHero ? 'text-2xl md:text-3xl font-normal text-white/90' : 'text-lg font-normal text-white/80'}`}>
            <span className="opacity-30 font-sans text-xs italic font-light tracking-wide block mb-1 uppercase">{card.category}</span>
            {card.title}
          </h2>
          <p className={isHero ? 'text-sm text-white/40 leading-relaxed max-w-[48ch] mb-6' : 'text-xs text-white/40 leading-relaxed max-w-[48ch] mb-6'}>
            {card.summary}
          </p>

          {card.progress !== undefined && (
            <div className="relative w-20 h-20 mb-6">
              <svg className="w-full h-full transform -rotate-90">
                <circle cx="40" cy="40" r="36" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-white/5" />
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

          {card.metadata && (
            <div className="mb-6 text-[10px] uppercase tracking-[0.25em] text-white/25">
              {card.metadata}
            </div>
          )}

          {isHero && (
            <div className="mt-8 flex gap-2">
              <button
                onClick={() => (onOpen ? onOpen(card) : onAsk(card))}
                className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase tracking-wider transition-colors ${canOpen ? 'bg-cyan-500 text-black hover:bg-cyan-400' : 'bg-white/10 text-white/50 hover:bg-white/10'}`}
              >
                {primaryCardActionLabel(card)}
              </button>
            </div>
          )}
        </div>

        <div className="mt-auto pt-4 flex items-center justify-between border-t border-white/5">
          <div className="flex items-center gap-3">
            <button onClick={() => onAsk(card)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest hover:text-cyan-400 transition-colors">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button onClick={() => onSave(card)} className="opacity-40 hover:opacity-100 transition-opacity">
              <BookmarkPlus size={14} />
            </button>
          </div>
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
  onAsk: (card: DiscoveryCardData) => void;
  onOpen: (card: DiscoveryCardData) => void;
}> = ({ card, onAsk, onOpen }) => {
  const canOpen = canOpenCard(card);

  return (
    <div className="rounded-2xl border border-white/6 bg-white/[0.025] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[9px] uppercase tracking-[0.24em] text-cyan-400/70">{card.family}</p>
          <p className="mt-2 text-base font-serif text-white/90">{card.title}</p>
          <p className="mt-2 text-[11px] leading-relaxed text-white/45">{card.summary}</p>
          {card.metadata ? (
            <p className="mt-3 text-[9px] uppercase tracking-[0.22em] text-white/25">{card.metadata}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => (canOpen ? onOpen(card) : onAsk(card))}
          className={`shrink-0 rounded-full border px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.18em] transition ${
            canOpen
              ? 'border-white/10 text-white/55 hover:border-cyan-400/30 hover:text-cyan-300'
              : 'border-white/5 text-white/25 hover:text-white/45'
          }`}
        >
          {canOpen ? 'Open' : 'Ask'}
        </button>
      </div>
    </div>
  );
};

const InnerSpaceCluster: React.FC<{
  continueCard: DiscoveryCardData;
  latestCard?: DiscoveryCardData;
  dormantCard?: DiscoveryCardData;
  themePulseCard?: DiscoveryCardData;
  topNodes: DiscoveryTopNode[];
  onAsk: (card: DiscoveryCardData) => void;
  onSave: (card: DiscoveryCardData) => void;
  onOpen: (card: DiscoveryCardData) => void;
}> = ({
  continueCard,
  latestCard,
  dormantCard,
  themePulseCard,
  topNodes,
  onAsk,
  onSave,
  onOpen,
}) => {
  const continueCanOpen = canOpenCard(continueCard);
  const pulseBadge = topNodes.length > 0
    ? `${topNodes.length} top node${topNodes.length === 1 ? '' : 's'}`
    : themePulseCard?.syncRate;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.8fr] gap-4 auto-rows-fr">
      <motion.article
        whileHover={{ scale: 1.005, y: -2 }}
        className={`relative flex min-h-[420px] flex-col rounded-2xl border p-5 transition-all duration-300 ${cardStyles('cyan')}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-cyan-400/80">{continueCard.family}</p>
            {continueCard.sources.length > 0 ? (
              <p className="mt-2 text-[10px] italic text-white/40">{continueCard.sources.join(' // ')}</p>
            ) : null}
          </div>
          {continueCard.progress !== undefined ? (
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-cyan-400/20 bg-cyan-500/5 text-sm font-bold text-cyan-300">
              {continueCard.progress}%
            </div>
          ) : null}
        </div>

        <div className="mt-6">
          <p className="text-[10px] uppercase tracking-[0.24em] text-white/24">Personal</p>
          <h3 className="mt-2 font-serif text-3xl leading-tight text-white/92">{continueCard.title}</h3>
          <p className="mt-4 max-w-[58ch] text-sm leading-relaxed text-white/48">{continueCard.summary}</p>
          {continueCard.metadata ? (
            <p className="mt-5 text-[10px] uppercase tracking-[0.24em] text-white/24">{continueCard.metadata}</p>
          ) : null}
        </div>

        {(latestCard || dormantCard) ? (
          <div className="mt-8 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {latestCard ? <InnerSpaceMiniCard card={latestCard} onAsk={onAsk} onOpen={onOpen} /> : null}
            {dormantCard ? <InnerSpaceMiniCard card={dormantCard} onAsk={onAsk} onOpen={onOpen} /> : null}
          </div>
        ) : null}

        <div className="mt-auto flex items-center justify-between border-t border-white/5 pt-4">
          <div className="flex items-center gap-3">
            <button onClick={() => onAsk(continueCard)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest transition-colors hover:text-cyan-400">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button onClick={() => onSave(continueCard)} className="opacity-40 transition-opacity hover:opacity-100">
              <BookmarkPlus size={14} />
            </button>
          </div>
          <button
            type="button"
            onClick={() => (continueCanOpen ? onOpen(continueCard) : onAsk(continueCard))}
            className={`rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] transition ${
              continueCanOpen
                ? 'border-cyan-400/25 bg-cyan-500 text-black hover:bg-cyan-400'
                : 'border-white/8 bg-white/5 text-white/55 hover:bg-white/10'
            }`}
          >
            {primaryCardActionLabel(continueCard)}
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
              <p className="mt-2 text-[10px] italic text-white/40">
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
            <p className="text-[10px] uppercase tracking-[0.24em] text-white/24">Personal</p>
            <h3 className="mt-2 font-serif text-2xl leading-tight text-white/92">Top Nodes</h3>
          </div>

          {topNodes.length > 0 ? (
            <div className="mt-6 space-y-3">
              {topNodes.map((node) => (
                <div key={node.label} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3 text-[11px] font-bold uppercase tracking-[0.14em] text-white/75">
                    <span className="truncate">{node.label}</span>
                    <span className="shrink-0 text-white/35">{node.count}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
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
            <p className="mt-6 text-sm leading-relaxed text-white/45">{themePulseCard.summary}</p>
          )}

          {themePulseCard.metadata ? (
            <p className="mt-6 text-[10px] uppercase tracking-[0.24em] text-white/22">{themePulseCard.metadata}</p>
          ) : null}

          <div className="mt-auto flex items-center justify-between border-t border-white/5 pt-4">
            <button onClick={() => onAsk(themePulseCard)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest transition-colors hover:text-cyan-400">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button
              type="button"
              onClick={() => onAsk(themePulseCard)}
              className="rounded-full border border-white/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-white/70 transition hover:border-cyan-400/25 hover:text-cyan-300"
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
        className={`${index === 0 ? 'min-h-[420px]' : 'min-h-[420px]'} rounded-2xl border border-white/5 bg-white/[0.02] animate-pulse`}
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
      
      if (cached && active) {
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
        const payload = await getDiscoveryPage(userId, forceRefresh);
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

  const academicCards = pillarCardsByCategory.ACADEMIC;
  const religiousCards = pillarCardsByCategory.RELIGIOUS;
  const literaryCards = pillarCardsByCategory.LITERARY;
  const cultureCards = pillarCardsByCategory.CULTURE_HISTORY;

  const academicHero = academicCards[0];
  const academicDetail = academicCards[1];
  const religiousHero = religiousCards[0];
  const religiousDetail = religiousCards[1];
  const literaryHero = literaryCards[0];
  const cultureHero = cultureCards[0];
  const hasAnyPillarCards = [academicCards, religiousCards, literaryCards, cultureCards].some((cards) => cards.length > 0);
  const continueCard = innerSpaceCards.find((card) => card.slot === 'continue_this') || innerSpaceCards[0];
  const latestSyncCard = innerSpaceCards.find((card) => card.slot === 'latest_sync');
  const dormantGemCard = innerSpaceCards.find((card) => card.slot === 'dormant_gem');
  const themePulseCard = innerSpaceCards.find((card) => card.slot === 'theme_pulse');
  const remainingPillarCards = [
    ...academicCards.slice(2),
    ...religiousCards.slice(2),
    ...literaryCards.slice(1),
    ...cultureCards.slice(1),
  ];

  return (
    <div className="relative min-h-screen bg-[#020408] text-white overflow-y-auto selection:bg-cyan-500/30">
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 right-0 w-full h-[600px] bg-gradient-to-b from-blue-900/10 via-transparent to-transparent" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.045)_1px,transparent_0)] bg-[size:24px_24px] opacity-[0.07]" />
      </div>

      <div className="relative z-10 max-w-[1700px] mx-auto px-6 lg:px-16 py-8">
        <header className="mb-10">
          <div className="flex flex-col items-center border-b border-white/5 pb-8 text-center">
            <h1 className="text-4xl md:text-5xl font-serif font-light tracking-wide text-white/90 italic">Discovery</h1>
          </div>
        </header>

        <main>
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <h2 className="text-3xl font-black uppercase tracking-[0.2em] bg-clip-text text-transparent bg-gradient-to-r from-white to-white/40">Inner Space</h2>
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
            ) : innerSpaceCards.length > 0 && continueCard ? (
              <InnerSpaceCluster
                continueCard={continueCard}
                latestCard={latestSyncCard}
                dormantCard={dormantGemCard}
                themePulseCard={themePulseCard}
                topNodes={topNodes}
                onAsk={handleAsk}
                onSave={handleSave}
                onOpen={handleOpen}
              />
            ) : (
              <div className="rounded-2xl border border-white/5 bg-white/[0.02] px-5 py-6 text-sm text-white/50">
                Discovery could not load inner archive signals yet.
              </div>
            )}
          </div>

          <div className="mt-12">
            <div className="flex flex-col items-start mb-8 px-4 border-l-2 border-cyan-500/20 pl-6">
              <span className="text-[10px] font-sans font-light tracking-[0.4em] uppercase opacity-30 mb-2">Fundamental Layer</span>
              <h2 className="text-3xl font-serif italic text-white/80 tracking-tight">The Pillars</h2>
              <div className="mt-4 w-32 h-[1px] bg-gradient-to-r from-white/20 to-transparent" />
            </div>

            {pageLoading && !hasAnyPillarCards ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="md:col-span-2 min-h-[280px] rounded-2xl border border-white/5 bg-white/[0.02] animate-pulse" />
                <div className="md:col-span-1 min-h-[280px] rounded-2xl border border-white/5 bg-white/[0.02] animate-pulse" />
              </div>
            ) : null}

            {academicHero && academicDetail && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <CardSurface card={academicHero} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-2 min-h-[280px]" />
                <CardSurface card={academicDetail} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[280px]" />
              </div>
            )}

            {religiousHero && religiousDetail && (
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
                <CardSurface card={religiousHero} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-3 min-h-[280px]" />
                <CardSurface card={religiousDetail} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-2 min-h-[280px]" />
              </div>
            )}

            {literaryHero || cultureHero ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                {[literaryHero, cultureHero].map((card) => (
                  card ? <CardSurface key={card.id} card={card} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[280px]" /> : null
                ))}
              </div>
            ) : null}

            {remainingPillarCards.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {remainingPillarCards.map((card) => (
                  <CardSurface key={card.id} card={card} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[220px]" />
                ))}
              </div>
            ) : null}

            {!pageLoading && !hasAnyPillarCards ? (
              <div className="rounded-2xl border border-white/5 bg-white/[0.02] px-5 py-6 text-sm text-white/50">
                Pillars could not load external source cards right now.
              </div>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
};
