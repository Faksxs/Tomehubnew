/**
 * InnerSpaceCluster — the personal / archive section of the Discovery page.
 *
 * Contains InnerSpaceMiniCard (dormant gems) and InnerSpaceLoadingGrid.
 * Extracted from DiscoveryHome.tsx. No behavioral changes.
 */

import React from 'react';
import { motion } from 'framer-motion';
import type { LibraryItem } from '../../../types';
import type {
  DiscoveryCardData,
  DiscoveryTopNode,
  LatestSyncEntry,
  DormantGemEntry,
} from '../discovery.types';
import { cardStyles } from '../discovery.types';
import { canOpenCard } from '../discoveryMappers';

// ─── InnerSpaceMiniCard ──────────────────────────────────────────────────────

const InnerSpaceMiniCard: React.FC<{
  card: DiscoveryCardData;
  dormantEntries?: DormantGemEntry[];
  onAsk: (card: DiscoveryCardData) => void;
  onOpen: (card: DiscoveryCardData) => void;
  onOpenItem: (item: LibraryItem) => void;
}> = ({ card, dormantEntries = [], onAsk, onOpen, onOpenItem }) => {
  const isDormant = card.slot === 'dormant_gem';

  return (
    <div className="rounded-2xl border border-black/5 dark:border-white/6 bg-white/40 dark:bg-white/[0.025] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          
                    {isDormant && dormantEntries.length > 0 ? (
            <div className="space-y-3">
              {dormantEntries.map((entry) => (
                <div key={entry.key} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="mt-1 text-base font-serif text-slate-900 dark:text-white/90">{entry.title}</p>
                    <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-white/75">{entry.reason}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onOpenItem(entry.item)}
                    className="shrink-0 rounded-full border border-black/10 dark:border-white/10 px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500 dark:text-white/60 transition hover:border-[#CC561E]/30 dark:hover:border-[#CC561E]/30 hover:text-[#CC561E] dark:hover:text-[#CC561E]"
                  >
                    Open
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <>
              <p className="mt-2 text-base font-serif text-slate-900 dark:text-white/90">{card.title}</p>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-white/75 line-clamp-3">{card.summary}</p>
            </>
          )}
          {card.metadata ? (
            <p className="mt-3 text-[9px] uppercase tracking-[0.22em] text-slate-500 dark:text-white/25">{card.metadata}</p>
          ) : null}
        </div>
        
      </div>
    </div>
  );
};

// ─── InnerSpaceCluster ───────────────────────────────────────────────────────

interface InnerSpaceClusterProps {
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
}

export const InnerSpaceCluster: React.FC<InnerSpaceClusterProps> = ({
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
  const pulseBadge = topNodes.length > 0
    ? `${topNodes.length} top node${topNodes.length === 1 ? '' : 's'}`
    : themePulseCard?.syncRate;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.8fr] gap-4 xl:auto-rows-fr">
      <motion.article
        whileHover={{ scale: 1.005, y: -2 }}
        className={`relative flex min-h-0 xl:min-h-[420px] flex-col rounded-2xl border p-5 transition-all duration-300 ${cardStyles('purple')}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div />
          {latestCard.progress !== undefined ? (
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-[#CC561E]/20 bg-[#CC561E]/5 text-sm font-bold text-[#CC561E]">
              {latestCard.progress}%
            </div>
          ) : null}
        </div>

        <div className="mt-8 grid grid-cols-1 gap-3 xl:grid-cols-2">
          {latestEntries.map((entry) => (
            <div key={entry.key} className="rounded-2xl border border-white/6 bg-white/[0.025] px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[9px] uppercase tracking-[0.24em] text-[#CC561E] dark:text-[#CC561E]/90">{entry.label}</p>
                  <p className="mt-2 text-base font-serif text-slate-900 dark:text-white/90">{entry.title}</p>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-white/75 line-clamp-3">{entry.description}</p>
                </div>
                {entry.item ? (
                  <button
                    type="button"
                    onClick={() => onOpenItem(entry.item)}
                    className="shrink-0 rounded-full border border-black/10 dark:border-white/10 px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500 dark:text-white/60 transition hover:border-[#CC561E]/30 dark:hover:border-[#CC561E]/30 hover:text-[#CC561E] dark:hover:text-[#CC561E]"
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

        </motion.article>

      {themePulseCard ? (
        <motion.article
          whileHover={{ scale: 1.005, y: -2 }}
          className={`relative flex min-h-0 xl:min-h-[420px] flex-col rounded-2xl border p-5 transition-all duration-300 ${cardStyles('dark')}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div />
              <div className="rounded-full border border-[#CC561E]/20 bg-[#CC561E]/10 px-2 py-0.5 text-[9px] font-mono text-[#CC561E]">
                {pulseBadge}
              </div>
          </div>

          <div className="mt-6">
            
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
                      className="h-full bg-slate-700/80"
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-6 text-sm leading-relaxed text-slate-700 dark:text-white/45">{themePulseCard.summary}</p>
          )}

          

          </motion.article>
      ) : null}
    </div>
  );
};

// ─── Loading Skeleton ────────────────────────────────────────────────────────

export const InnerSpaceLoadingGrid: React.FC = () => (
  <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.8fr] gap-4 xl:auto-rows-fr">
    {[0, 1].map((index) => (
      <div
        key={index}
        className={`${index === 0 ? 'min-h-[220px] xl:min-h-[420px]' : 'min-h-[220px] xl:min-h-[420px]'} rounded-2xl border border-black/5 dark:border-white/5 bg-black/[0.02] dark:bg-white/[0.02]`}
      />
    ))}
  </div>
);
