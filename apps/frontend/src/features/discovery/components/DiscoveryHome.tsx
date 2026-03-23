import React, { useEffect, useState } from 'react';
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
} from 'lucide-react';
import type { AppTab } from '../../app/types';
import type { LibraryItem, PersonalNoteCategory } from '../../../types';
import { getFriendlyApiErrorMessage } from '../../../services/apiClient';
import {
  getDiscoveryBoard,
  getDiscoveryInnerSpace,
  type DiscoveryBoardResponse,
  type DiscoveryCard as ExternalDiscoveryCard,
  type DiscoveryInnerSpaceCard,
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

interface DiscoveryCardData {
  id: string;
  category: DiscoveryCategory;
  family: string;
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
  },
];

const buildFallbackInnerSpaceCards = (): DiscoveryCardData[] => [
  {
    id: 'fallback-continue',
    category: 'Personal',
    family: 'CONTINUE THIS',
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

const CATEGORY_ORDER: ExternalCategoryKey[] = ['ACADEMIC', 'RELIGIOUS', 'LITERARY', 'CULTURE_HISTORY'];

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

const mapBoardResponseToCards = (board: DiscoveryBoardResponse, category: ExternalCategoryKey): DiscoveryCardData[] => {
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
                onClick={() => (card.itemId && onOpen ? onOpen(card) : onAsk(card))}
                className="px-4 py-1.5 rounded-md bg-cyan-500 text-black text-[10px] font-black uppercase tracking-wider hover:bg-cyan-400 transition-colors"
              >
                {card.itemId ? 'OPEN_THREAD' : 'ASK_ARCHIVE'}
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
            onClick={() => (card.itemId && onOpen ? onOpen(card) : onAsk(card))}
            className="opacity-20 group-hover:opacity-100 transition-opacity"
            aria-label={card.itemId ? `Open ${card.title}` : `Ask about ${card.title}`}
          >
            <ArrowUpRight size={14} />
          </button>
        </div>
      </div>
    </motion.article>
  );
};

const InnerSpaceLoadingGrid: React.FC = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 auto-rows-fr">
    {[0, 1, 2, 3].map((index) => (
      <div
        key={index}
        className={`${index === 0 ? 'md:row-span-2 min-h-[420px]' : ''} ${index === 1 ? 'md:col-span-2 md:row-span-2 min-h-[480px]' : 'min-h-[220px]'} rounded-2xl border border-white/5 bg-white/[0.02] animate-pulse`}
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
  const [innerSpaceCards, setInnerSpaceCards] = useState<DiscoveryCardData[]>(() => buildFallbackInnerSpaceCards());
  const [innerSpaceLoading, setInnerSpaceLoading] = useState(true);
  const [innerSpaceError, setInnerSpaceError] = useState<string | null>(null);
  const [pillarCardsByCategory, setPillarCardsByCategory] = useState<Record<ExternalCategoryKey, DiscoveryCardData[]>>({
    ACADEMIC: fallbackPillarsByCategory('ACADEMIC'),
    RELIGIOUS: fallbackPillarsByCategory('RELIGIOUS'),
    LITERARY: fallbackPillarsByCategory('LITERARY'),
    CULTURE_HISTORY: fallbackPillarsByCategory('CULTURE_HISTORY'),
  });
  const [pillarsLoading, setPillarsLoading] = useState(true);
  const [pillarsError, setPillarsError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const loadInnerSpace = async () => {
      if (!userId) {
        if (active) {
          setInnerSpaceCards(buildFallbackInnerSpaceCards());
          setInnerSpaceLoading(false);
        }
        return;
      }

      setInnerSpaceLoading(true);
      setInnerSpaceError(null);
      try {
        const response = await getDiscoveryInnerSpace(userId);
        if (!active) return;
        const mapped = Array.isArray(response.cards) && response.cards.length > 0
          ? response.cards.map(mapInnerSpaceCard)
          : buildFallbackInnerSpaceCards();
        setInnerSpaceCards(mapped);
      } catch (error) {
        if (!active) return;
        setInnerSpaceError(getFriendlyApiErrorMessage(error));
        setInnerSpaceCards(buildFallbackInnerSpaceCards());
      } finally {
        if (active) {
          setInnerSpaceLoading(false);
        }
      }
    };

    loadInnerSpace();
    return () => {
      active = false;
    };
  }, [userId]);

  useEffect(() => {
    let active = true;

    const loadBoards = async () => {
      if (!userId) {
        if (active) {
          setPillarsLoading(false);
        }
        return;
      }

      setPillarsLoading(true);
      setPillarsError(null);
      try {
        const results = await Promise.allSettled(
          CATEGORY_ORDER.map((category) => getDiscoveryBoard(userId, category))
        );
        if (!active) return;

        const nextState: Record<ExternalCategoryKey, DiscoveryCardData[]> = {
          ACADEMIC: fallbackPillarsByCategory('ACADEMIC'),
          RELIGIOUS: fallbackPillarsByCategory('RELIGIOUS'),
          LITERARY: fallbackPillarsByCategory('LITERARY'),
          CULTURE_HISTORY: fallbackPillarsByCategory('CULTURE_HISTORY'),
        };
        let firstError: string | null = null;

        results.forEach((result, index) => {
          const category = CATEGORY_ORDER[index];
          if (result.status === 'fulfilled') {
            const mapped = mapBoardResponseToCards(result.value, category);
            nextState[category] = mapped.length > 0 ? mapped : fallbackPillarsByCategory(category);
            return;
          }
          if (!firstError) {
            firstError = getFriendlyApiErrorMessage(result.reason);
          }
          nextState[category] = fallbackPillarsByCategory(category);
        });

        setPillarCardsByCategory(nextState);
        setPillarsError(firstError);
      } catch (error) {
        if (!active) return;
        setPillarsError(getFriendlyApiErrorMessage(error));
      } finally {
        if (active) {
          setPillarsLoading(false);
        }
      }
    };

    loadBoards();
    return () => {
      active = false;
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
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-[0.03] mix-blend-overlay" />
      </div>

      <div className="relative z-10 max-w-[1700px] mx-auto px-6 lg:px-16 py-8">
        <header className="mb-10">
          <div className="flex flex-col items-center border-b border-white/5 pb-6 text-center">
            <h1 className="text-4xl md:text-5xl font-serif font-light tracking-wide text-white/90 italic">Discovery</h1>
            <div className="mt-6 flex items-center gap-4 text-[10px] font-light tracking-[0.3em] uppercase opacity-30">
              <span>Analytical</span>
              <div className="w-1.5 h-1.5 rounded-full bg-cyan-500/50" />
              <span>Synthesis</span>
              <div className="w-1.5 h-1.5 rounded-full bg-cyan-500/50" />
              <span>Curated</span>
            </div>
          </div>
        </header>

        <main>
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <h2 className="text-3xl font-black uppercase tracking-[0.2em] bg-clip-text text-transparent bg-gradient-to-r from-white to-white/40">Inner Space</h2>
              </div>
            </div>

            {innerSpaceError && (
              <div className="mb-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-100/80">
                {innerSpaceError}
              </div>
            )}

            {innerSpaceLoading ? (
              <InnerSpaceLoadingGrid />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 auto-rows-fr">
                {innerSpaceCards.map((card) => (
                  <CardSurface key={card.id} card={card} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} />
                ))}
              </div>
            )}
          </div>

          <div className="mt-12">
            <div className="flex flex-col items-start mb-8 px-4 border-l-2 border-cyan-500/20 pl-6">
              <span className="text-[10px] font-sans font-light tracking-[0.4em] uppercase opacity-30 mb-2">Fundamental Layer</span>
              <h2 className="text-3xl font-serif italic text-white/80 tracking-tight">The Pillars</h2>
              <div className="mt-4 w-32 h-[1px] bg-gradient-to-r from-white/20 to-transparent" />
            </div>

            {pillarsError && (
              <div className="mb-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-100/80">
                {pillarsError}
              </div>
            )}

            {pillarsLoading ? (
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

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {[literaryHero, cultureHero].map((card) => (
                card ? <CardSurface key={card.id} card={card} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[280px]" /> : null
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {remainingPillarCards.map((card) => (
                <CardSurface key={card.id} card={card} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[220px]" />
              ))}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
