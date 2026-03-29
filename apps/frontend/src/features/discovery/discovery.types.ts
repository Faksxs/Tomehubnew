/**
 * Shared types, constants, and visual configuration for the Discovery feature.
 *
 * Extracted from DiscoveryHome.tsx to reduce coupling and improve reuse.
 */

import type React from 'react';
import type { LibraryItem } from '../../types';
import type {
  DiscoveryInnerSpaceSlot,
  DiscoveryEvidence,
} from '../../services/backendApiService';

// ─── Category & Layout Types ─────────────────────────────────────────────────

export type DiscoveryCategory = 'Personal' | 'Academic' | 'Religious' | 'Literary' | 'Culture';
export type DiscoveryCardSize = 'hero' | 'detail' | 'wide' | 'tall';
export type DiscoveryTone = 'light' | 'dark' | 'green' | 'blue' | 'purple' | 'amber';
export type ExternalCategoryKey = 'ACADEMIC' | 'RELIGIOUS' | 'LITERARY' | 'CULTURE_HISTORY';

// ─── Core Data Interfaces ────────────────────────────────────────────────────

export interface DiscoveryCardData {
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

export interface DiscoveryTopNode {
  label: string;
  count: number;
}

export interface DiscoveryViewMeta {
  lastUpdatedAt: string | null;
  hasCachedSnapshot: boolean;
  hasPartialErrors: boolean;
  boardErrorCount: number;
}

export interface LatestSyncEntry {
  key: string;
  label: string;
  title: string;
  description: string;
  item?: LibraryItem;
}

export interface DormantGemEntry {
  key: string;
  label: string;
  title: string;
  reason: string;
  item: LibraryItem;
}

// ─── Cache Configuration ─────────────────────────────────────────────────────

export const DISCOVERY_PAGE_CACHE_KEY = 'tomehub:discovery:page-cache:v3';

export const LEGACY_DISCOVERY_PAGE_CACHE_KEYS = [
  'tomehub:discovery:page-cache:v1',
  'tomehub:discovery:page-cache:v2',
];

/** How long a cached snapshot is considered fresh (no re-fetch). */
export const DISCOVERY_PAGE_CACHE_TTL_MS = 6 * 60 * 60 * 1000;

/** Maximum age before the cache is silently discarded. */
export const DISCOVERY_PAGE_CACHE_MAX_STALE_MS = 24 * 60 * 60 * 1000;

// ─── Visual Configuration ────────────────────────────────────────────────────

export const categoryVisuals: Record<ExternalCategoryKey, Pick<DiscoveryCardData, 'category' | 'tone'>> = {
  ACADEMIC: { category: 'Academic', tone: 'blue' },
  RELIGIOUS: { category: 'Religious', tone: 'green' },
  LITERARY: { category: 'Literary', tone: 'purple' },
  CULTURE_HISTORY: { category: 'Culture', tone: 'amber' },
};

export const cardStyles = (tone: DiscoveryTone): string => {
  switch (tone) {
    case 'blue': return 'bg-white dark:bg-[#080C14] border-blue-500/20 text-slate-900 dark:text-blue-50 shadow-sm';
    case 'green': return 'bg-white dark:bg-[#060D0A] border-emerald-500/20 text-slate-900 dark:text-emerald-50 shadow-sm';
    case 'purple': return 'bg-white dark:bg-[#0B0814] border-purple-500/20 text-slate-900 dark:text-purple-50 shadow-sm';
    case 'amber': return 'bg-white dark:bg-[#0D0806] border-[#CC561E]/30 text-slate-900 dark:text-[#CC561E]/90 shadow-sm';
    case 'dark': return 'bg-white dark:bg-[#020408] border border-white/10 text-slate-900 dark:text-slate-100 shadow-md';
    default: return 'bg-white dark:bg-[#0A0C10] border-white/10 text-slate-900 dark:text-white';
  }
};

// ─── Helper Factories ────────────────────────────────────────────────────────

export const createEmptyPillarState = (): Record<ExternalCategoryKey, DiscoveryCardData[]> => ({
  ACADEMIC: [],
  RELIGIOUS: [],
  LITERARY: [],
  CULTURE_HISTORY: [],
});

export const EMPTY_VIEW_META: DiscoveryViewMeta = {
  lastUpdatedAt: null,
  hasCachedSnapshot: false,
  hasPartialErrors: false,
  boardErrorCount: 0,
};
