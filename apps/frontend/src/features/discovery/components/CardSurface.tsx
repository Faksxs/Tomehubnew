/**
 * CardSurface — the primary Discovery card renderer.
 *
 * Handles all visual variants (hero, detail, tall, wide) across every
 * Discovery category (Academic, Religious, Literary, Culture, Personal).
 *
 * Extracted from DiscoveryHome.tsx. No behavioral changes.
 */

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowUpRight,
  BookmarkPlus,
  MessageSquareText,
} from 'lucide-react';
import type { DiscoveryCardData } from '../discovery.types';
import { cardStyles } from '../discovery.types';
import { canOpenCard, compactWhySeen, compactEvidenceValue } from '../discoveryMappers';

interface CardSurfaceProps {
  card: DiscoveryCardData;
  onAsk: (card: DiscoveryCardData) => void;
  onSave: (card: DiscoveryCardData) => void;
  onOpen?: (card: DiscoveryCardData) => void;
  className?: string;
}

export const CardSurface: React.FC<CardSurfaceProps> = ({ card, onAsk, onSave, onOpen, className }) => {
  const [isTafsirExpanded, setIsTafsirExpanded] = useState(false);
  const isHero = card.size === 'hero';
  const isTall = card.size === 'tall';
  const isWide = card.size === 'wide';
  const isDormant = card.family === 'DORMANT GEM';
  const canOpen = canOpenCard(card);
  const showWhySeen = (card.category === 'Academic' || card.category === 'Literary' || card.category === 'Culture') && !card.slot;
  const whySeen = showWhySeen ? compactWhySeen(card.whySeen) : null;
  const RELIGIOUS_NO_TRUNCATE = new Set(['Tefsir', 'Meal']);
  const religiousEvidence = card.category === 'Religious'
    ? ['Arabic', 'Okunuş', 'Meal', 'Tefsir']
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
        <div className="absolute inset-0 bg-white/[0.02] z-0 pointer-events-none transition-all duration-500" />
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
            <span className="text-[11px] font-bold tracking-[0.25em] uppercase text-[#CC561E] dark:text-[#CC561E]/90">
              {card.category}
            </span>
            <span className="text-[10px] font-light italic text-slate-500 dark:text-white/80">
              {card.family}
            </span>
          </div>
          {card.syncRate && (
            <div className="px-2 py-0.5 rounded-full bg-[#CC561E]/10 dark:bg-[#CC561E]/10 border border-[#CC561E]/20 dark:border-[#CC561E]/20 text-[9px] font-mono text-[#CC561E]">
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
          <p className={isHero ? 'text-sm text-slate-600 dark:text-white/85 leading-relaxed max-w-[48ch] mb-6' : 'text-xs text-slate-600 dark:text-white/85 leading-relaxed max-w-[48ch] mb-6'}>
            {card.summary}
          </p>

          {whySeen && (
            <div className="mb-5 rounded-xl border border-black/5 dark:border-white/6 bg-black/[0.03] dark:bg-white/[0.025] px-3 py-2">
              <p className="text-[10px] leading-relaxed text-slate-600 dark:text-white/80">
                <span className="mr-1 uppercase tracking-[0.18em] text-[#CC561E] dark:text-[#CC561E]/80">Why:</span>
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
                          ? `${isHero ? 'text-sm md:text-[15px]' : 'text-[11px]'} leading-7 text-slate-800 dark:text-white/80 ${!isTafsirExpanded ? 'line-clamp-5' : ''}`
                          : `${isHero ? 'text-sm' : 'text-[11px]'} leading-relaxed text-slate-700 dark:text-white/75`
                    }
                  >
                    {item.value}
                  </p>
                  {item.label === 'Tefsir' && item.value.length > 200 && (
                    <button
                      onClick={() => setIsTafsirExpanded(!isTafsirExpanded)}
                      className="mt-2 text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 hover:underline"
                    >
                      {isTafsirExpanded ? 'Daha Az' : 'Daha Fazla'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {cultureEvidence.length > 0 && (
            <div className="mb-5 flex flex-wrap gap-2">
              {cultureEvidence.map((item) => (
                <div key={item.label} className="rounded-full border-[#CC561E]/12 bg-[#CC561E]/[0.06] border px-3 py-1.5">
                  <span className="mr-2 text-[9px] uppercase tracking-[0.18em] text-[#CC561E] dark:text-[#CC561E]/70">{item.label}</span>
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
                  className="text-[#CC561E] transition-all duration-1000"
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
            <button onClick={() => onAsk(card)} className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest hover:text-[#CC561E] transition-colors">
              <MessageSquareText size={12} />
              Ask
            </button>
            <button onClick={() => onSave(card)} className="opacity-40 hover:opacity-100 transition-opacity">
              <BookmarkPlus size={14} />
            </button>
          </div>

          {card.metadata && (
            <div className="text-[9px] uppercase tracking-[0.2em] font-medium text-[#CC561E] dark:text-[#CC561E]/70 italic">
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
