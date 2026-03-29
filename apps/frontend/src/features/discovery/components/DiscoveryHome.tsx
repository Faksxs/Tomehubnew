/**
 * DiscoveryHome — the main Discovery page orchestrator.
 *
 * This component was refactored from a 1638-line God component into a slim
 * orchestrator (~300 lines) that delegates to focused modules:
 *
 *   - discovery.types.ts        → shared types, constants, visual config
 *   - fallbackCards.json        → static/fallback card data
 *   - discoveryMappers.ts       → pure data transformation functions
 *   - useDiscoveryPage.ts       → data-fetching, caching, and refresh hook
 *   - CardSurface.tsx           → individual Discovery card component
 *   - InnerSpaceCluster.tsx     → personal/archive section components
 *
 * No behavioral changes were made during this refactoring.
 */

import React, { useMemo } from 'react';
import {
  Menu,
  RotateCw,
  Sparkles,
} from 'lucide-react';
import type { AppTab } from '../../app/types';
import type { LibraryItem, PersonalNoteCategory } from '../../../types';
import {
  persistDiscoveryFlowSeed,
  persistDiscoveryPromptSeed,
} from '../discoverySeeds';

import type { DiscoveryCardData } from '../discovery.types';
import { formatRelativeUpdateTime } from '../discoveryMappers';
import { useDiscoveryPage } from '../useDiscoveryPage';
import { CardSurface } from './CardSurface';
import { InnerSpaceCluster, InnerSpaceLoadingGrid } from './InnerSpaceCluster';

// ─── Props ───────────────────────────────────────────────────────────────────

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

// ─── Component ───────────────────────────────────────────────────────────────

export const DiscoveryHome: React.FC<DiscoveryHomeProps> = ({
  userId,
  books,
  onTabChange,
  onQuickCreatePersonalNote,
  onOpenDiscoveryItem,
  onMobileMenuClick,
}) => {
  const {
    innerSpaceCards,
    pillarCardsByCategory,
    pageLoading,
    pageWarning,
    pageError,
    viewMeta,
    isRefreshing,
    topNodes,
    latestSyncEntries,
    dormantGemEntries,
    triggerRefresh,
  } = useDiscoveryPage(userId, books);

  // ─── Derived State ───────────────────────────────────────────────────

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
    
    // We only override labels/summary for the 'latest_sync' visual if it's actually the latest_sync slot
    if (baseCard.slot === 'latest_sync') {
      const hasAnyLatestItem = latestSyncEntries.some((entry) => Boolean(entry.item));
      return {
        ...baseCard,
        family: 'LATEST SYNC',
        title: hasAnyLatestItem ? 'Latest archive sync' : 'No recent sync yet',
        summary: hasAnyLatestItem
          ? 'Fresh signals across book, cinema, article, and personal note lanes.'
          : 'As soon as new library activity lands, the freshest thread will appear here with direct context.',
      };
    }

    return baseCard;
  }, [continueCard, latestSyncCard, latestSyncEntries]);

  const remainingPillarCards: DiscoveryCardData[] = [];

  // ─── Event Handlers ──────────────────────────────────────────────────

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

  // ─── Render ──────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen bg-[#F7F8FB] dark:bg-[#020408] text-slate-900 dark:text-white overflow-y-auto selection:bg-amber-500/30">
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 right-0 w-full h-[600px] bg-gradient-to-b from-blue-900/5 dark:from-blue-900/10 via-transparent to-transparent" />
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

            <div className="flex items-center gap-6">
              <h1 className="text-4xl md:text-5xl font-serif font-light tracking-wide text-slate-900 dark:text-white/90 italic">Discovery</h1>
              <button
                type="button"
                onClick={() => triggerRefresh(true)}
                disabled={isRefreshing}
                className={`flex h-10 w-10 items-center justify-center rounded-full border transition-all ${
                  isRefreshing
                    ? 'cursor-wait border-[#CC561E]/15 bg-[#CC561E]/5 text-[#CC561E]/80'
                    : 'border-[#CC561E]/20 bg-[#CC561E]/10 text-[#CC561E] hover:border-[#CC561E]/40 hover:bg-[#CC561E]/20 active:scale-95'
                }`}
                title="Bütün Discovery içeriğini yenile ve önbelleği temizle"
              >
                <RotateCw size={18} className={isRefreshing ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>
        </header>

        <main>
          {/* ─── Inner Space Section ──────────────────────────────── */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <h2 className="text-3xl font-black uppercase tracking-[0.2em] bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-500 dark:from-white dark:to-white/40">Inner Space</h2>
              </div>
            </div>

            {pageError && (
              <div className="mb-4 rounded-2xl border border-[#CC561E]/20 bg-[#CC561E]/5 px-4 py-3 text-sm text-[#CC561E]/90">
                {pageError}
              </div>
            )}

            {pageWarning && (
              <div className="mb-4 rounded-2xl border border-[#CC561E]/20 bg-[#CC561E]/5 px-4 py-3 text-sm text-[#CC561E]/90">
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
            ) : !pageLoading ? (
              <div className="rounded-2xl border border-black/5 dark:border-white/5 bg-white/40 dark:bg-white/[0.02] px-5 py-12 text-center">
                <div className="flex flex-col items-center gap-4">
                  <div className="h-16 w-16 rounded-full bg-slate-100 dark:bg-white/5 flex items-center justify-center text-slate-400 dark:text-white/20">
                    <Sparkles size={32} className="animate-pulse" />
                  </div>
                  <div className="space-y-2">
                    <p className="text-lg font-medium text-slate-700 dark:text-white/70">Initializing your discovery space...</p>
                    <p className="text-sm text-slate-500 dark:text-white/40 max-w-[400px] mx-auto">
                      We are analyzing your library and connecting threads. This usually takes a few seconds on the first load.
                    </p>
                  </div>
                  <button
                    onClick={() => triggerRefresh(true)}
                    className="mt-4 px-6 py-2 bg-[#CC561E] text-white rounded-full text-sm font-medium hover:bg-[#B44C1A] transition-colors"
                  >
                    Check for Updates
                  </button>
                </div>
              </div>
            ) : (
              <InnerSpaceLoadingGrid />
            )}
          </div>

          {/* ─── Pillars Section ──────────────────────────────────── */}
          <div className="mt-12">
            <div className="mb-8 flex flex-col gap-4 px-4 pl-6 md:flex-row md:items-end md:justify-between md:border-l-2 md:border-[#CC561E]/20">
              <div className="flex flex-col items-start">
                <span className="mb-2 text-[10px] font-sans font-light uppercase tracking-[0.4em] text-slate-500 dark:text-white/30 italic">Fundamental Layer</span>
                <h2 className="text-3xl font-serif italic tracking-tight text-slate-800 dark:text-white/80">The Pillars</h2>
                <div className="mt-4 h-[1px] w-32 bg-gradient-to-r from-slate-400/20 dark:from-white/20 to-transparent" />
              </div>
              <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 dark:text-white/30">
                {formatRelativeUpdateTime(viewMeta.lastUpdatedAt)}
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
                <CardSurface card={academicHero} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className={`${academicDetail ? "md:col-span-2" : "md:col-span-full"} min-h-[280px]`} />
                {academicDetail && (
                  <CardSurface card={academicDetail} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[280px]" />
                )}
              </div>
            )}

            {religiousHero && (
              <div className="grid grid-cols-1 gap-4 mb-4">
                <CardSurface card={religiousHero} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-full min-h-[360px]" />
              </div>
            )}

            {literaryHero && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <CardSurface card={literaryHero} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className={`${literaryDetail ? "md:col-span-1" : "md:col-span-full"} min-h-[280px]`} />
                {literaryDetail && (
                  <CardSurface card={literaryDetail} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[280px]" />
                )}
              </div>
            )}

            {cultureHero && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <CardSurface card={cultureHero} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className={`${cultureDetail ? "md:col-span-1" : "md:col-span-full"} min-h-[280px]`} />
                {cultureDetail && (
                  <CardSurface card={cultureDetail} onAsk={handleAsk} onSave={handleSave} onOpen={handleOpen} className="md:col-span-1 min-h-[280px]" />
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
              <div className="rounded-2xl border border-black/5 dark:border-white/5 bg-white/40 dark:bg-white/[0.02] px-5 py-10 text-center">
                <div className="flex flex-col items-center gap-3">
                  <div className="h-12 w-12 rounded-full bg-slate-100 dark:bg-white/5 flex items-center justify-center text-slate-400 dark:text-white/20">
                    <Sparkles size={24} />
                  </div>
                  <p className="text-sm font-medium text-slate-500 dark:text-white/40 max-w-[320px] mx-auto">
                    Pillars could not load external source cards right now. Check your internet connection or try refreshing.
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
};
