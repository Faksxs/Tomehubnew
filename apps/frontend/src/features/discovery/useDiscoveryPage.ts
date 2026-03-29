/**
 * Custom hook that encapsulates all Discovery page data-fetching,
 * caching (sessionStorage + memory), and refresh logic.
 *
 * Extracted from DiscoveryHome.tsx to separate data orchestration from UI.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { LibraryItem } from '../../types';
import { getFriendlyApiErrorMessage } from '../../services/apiClient';
import { 
  getDiscoveryPage, 
  getDiscoveryBoard, 
  type DiscoveryPageResponse, 
  type DiscoveryBoardResponse 
} from '../../services/backendApiService';
import type {
  DiscoveryCardData,
  DiscoveryViewMeta,
  ExternalCategoryKey,
  DiscoveryTopNode,
  LatestSyncEntry,
  DormantGemEntry,
} from './discovery.types';
import {
  DISCOVERY_PAGE_CACHE_KEY,
  LEGACY_DISCOVERY_PAGE_CACHE_KEYS,
  DISCOVERY_PAGE_CACHE_TTL_MS,
  DISCOVERY_PAGE_CACHE_MAX_STALE_MS,
  createEmptyPillarState,
  EMPTY_VIEW_META,
} from './discovery.types';
import {
  mapDiscoveryPagePayload,
  mapDiscoveryBoardPayload,
  limitPillarCardsForLayout,
  buildTopNodesFromLibrary,
  buildLatestSyncEntries,
  buildDormantGemEntries,
  buildFallbackInnerSpaceCards,
  fallbackPillarsByCategory,
} from './discoveryMappers';

// ─── Cache Layer ─────────────────────────────────────────────────────────────

interface DiscoveryPageCacheEntry {
  userId: string;
  fetchedAt: number;
  payload: DiscoveryPageResponse;
}

let discoveryPageMemoryCache: DiscoveryPageCacheEntry | null = null;
const DISCOVERY_LIVE_FETCH_FALLBACK_MS = 2500;

const buildFallbackPillarState = (): Record<ExternalCategoryKey, DiscoveryCardData[]> => ({
  ACADEMIC: fallbackPillarsByCategory('ACADEMIC'),
  RELIGIOUS: fallbackPillarsByCategory('RELIGIOUS'),
  LITERARY: fallbackPillarsByCategory('LITERARY'),
  CULTURE_HISTORY: fallbackPillarsByCategory('CULTURE_HISTORY'),
});

const clearDiscoveryPageCache = (): void => {
  discoveryPageMemoryCache = null;
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(DISCOVERY_PAGE_CACHE_KEY);
    LEGACY_DISCOVERY_PAGE_CACHE_KEYS.forEach((key) => window.sessionStorage.removeItem(key));
  } catch {
    // ignore
  }
};

const purgeLegacyDiscoveryPageCaches = (): void => {
  if (typeof window === 'undefined') return;
  try {
    LEGACY_DISCOVERY_PAGE_CACHE_KEYS.forEach((key) => window.sessionStorage.removeItem(key));
  } catch {
    // ignore
  }
};

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
      clearDiscoveryPageCache();
      return null;
    }
    const ageMs = Date.now() - parsed.fetchedAt;
    if (ageMs > DISCOVERY_PAGE_CACHE_MAX_STALE_MS) {
      clearDiscoveryPageCache();
      return null;
    }
    discoveryPageMemoryCache = parsed;
    return parsed;
  } catch {
    clearDiscoveryPageCache();
    return null;
  }
};

const writeDiscoveryPageCache = (entry: DiscoveryPageCacheEntry): void => {
  discoveryPageMemoryCache = entry;
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(DISCOVERY_PAGE_CACHE_KEY, JSON.stringify(entry));
  } catch {
    // ignore
  }
};

// ─── Hook ────────────────────────────────────────────────────────────────────

export interface UseDiscoveryPageResult {
  innerSpaceCards: DiscoveryCardData[];
  pillarCardsByCategory: Record<ExternalCategoryKey, DiscoveryCardData[]>;
  pageLoading: boolean;
  pageWarning: string | null;
  pageError: string | null;
  viewMeta: DiscoveryViewMeta;
  isRefreshing: boolean;
  topNodes: DiscoveryTopNode[];
  latestSyncEntries: LatestSyncEntry[];
  dormantGemEntries: DormantGemEntry[];
  triggerRefresh: (force?: boolean) => void;
}

export function useDiscoveryPage(userId: string, books: LibraryItem[]): UseDiscoveryPageResult {
  // ─── Initial State from Cache ──────────────────────────────────────────────
  // We read the cache synchronously during initialization to avoid a "flash of empty"
  // when navigating back to the Discovery page.
  const initialCache = useMemo(() => (userId ? readDiscoveryPageCache(userId) : null), [userId]);
  const initialMapped = useMemo(() => (initialCache ? mapDiscoveryPagePayload(initialCache.payload) : null), [initialCache]);

  const [innerSpaceCards, setInnerSpaceCards] = useState<DiscoveryCardData[]>(
    () => initialMapped?.innerSpace || []
  );
  const [pillarCardsByCategory, setPillarCardsByCategory] = useState<Record<ExternalCategoryKey, DiscoveryCardData[]>>(
    () => (initialMapped ? limitPillarCardsForLayout(initialMapped.pillars) : createEmptyPillarState()),
  );
  const [pageLoading, setPageLoading] = useState(() => !initialMapped);
  const [pageWarning, setPageWarning] = useState<string | null>(() => initialMapped?.warning || null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [viewMeta, setViewMeta] = useState<DiscoveryViewMeta>(() => 
    initialMapped ? { ...initialMapped.meta, hasCachedSnapshot: true } : EMPTY_VIEW_META
  );
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const forceRefreshRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const lastAutoRefreshAtRef = useRef(0);

  const topNodes = useMemo(() => buildTopNodesFromLibrary(books), [books]);
  const latestSyncEntries = useMemo(() => buildLatestSyncEntries(books), [books]);
  const dormantGemEntries = useMemo(() => buildDormantGemEntries(books), [books]);

  const triggerRefresh = (force = false) => {
    if (!userId || requestInFlightRef.current) return;
    if (force) {
      clearDiscoveryPageCache();
      setInnerSpaceCards([]);
      setPillarCardsByCategory(createEmptyPillarState());
      setViewMeta(EMPTY_VIEW_META);
    }
    forceRefreshRef.current = force;
    setIsRefreshing(true);
    setRefreshNonce((value) => value + 1);
  };

  // Purge legacy cache keys once on mount
  useEffect(() => {
    purgeLegacyDiscoveryPageCaches();
  }, []);

  // Main data-fetch effect
  useEffect(() => {
    let active = true;

    const loadPage = async () => {
      if (!userId) {
        if (active) {
          setPageLoading(false);
          setIsRefreshing(false);
        }
        return;
      }
      
      requestInFlightRef.current = true;
      const forceRefresh = forceRefreshRef.current;
      forceRefreshRef.current = false;

      if (forceRefresh && active) {
        clearDiscoveryPageCache();
        setPageWarning(null);
        setPageError(null);
        setPageLoading(true);
      }

      // 1. Snapshot / Cache Recovery
      const cached = readDiscoveryPageCache(userId);
      const isWithinTtl = Boolean(cached && (Date.now() - cached.fetchedAt) < DISCOVERY_PAGE_CACHE_TTL_MS);
      const cacheIsFresh = !forceRefresh && isWithinTtl;

      if (cached && active && !forceRefresh) {
        const mapped = mapDiscoveryPagePayload(cached.payload);
        setInnerSpaceCards(mapped.innerSpace);
        setPillarCardsByCategory(limitPillarCardsForLayout(mapped.pillars));
        setPageWarning(mapped.warning);
        setViewMeta({ ...mapped.meta, hasCachedSnapshot: true });
        setPageLoading(false);
      } else if (active) {
        setPageLoading(true);
      }

      // 2. Short-circuit if cache is still fresh
      if (cacheIsFresh) {
        setPageError(null);
        setIsRefreshing(false);
        requestInFlightRef.current = false;
        return;
      }

      // 3. Live Fetch - Phase 1: Main Page (Inner Space)
      try {
        const payload = await getDiscoveryPage(
          userId,
          forceRefresh,
          forceRefresh ? String(Date.now()) : undefined,
        );
        
        if (!active) return;

        const mapped = mapDiscoveryPagePayload(payload);
        setInnerSpaceCards(mapped.innerSpace);
        setPillarCardsByCategory(limitPillarCardsForLayout(mapped.pillars));
        setPageWarning(mapped.warning);
        setViewMeta(mapped.meta);
        setPageError(null);
        
        // Persist to session storage so navigation back is instant
        writeDiscoveryPageCache({
          userId,
          fetchedAt: Date.now(),
          payload
        });

        // Mark main loading as complete so Inner Space shows up
        setPageLoading(false);

        // 4. Phase 2: Independent Board Loading (Lazy)
        // Optimization: Even with forceRefresh=true (orange button), we can skip the heavy board refresh 
        // if we already have pillar data and it's within TTL, to keep the UI snappy.
        // On initial load (no cache), hasExistingPillars will be false, triggering the fetch.
        const currentPillars = limitPillarCardsForLayout(mapped.pillars);
        const hasExistingPillars = Object.values(currentPillars).some(cards => cards.length > 0);
        const shouldSkipBoardRefresh = hasExistingPillars && isWithinTtl && !forceRefresh;

        if (!shouldSkipBoardRefresh) {
          const categories: ExternalCategoryKey[] = ['ACADEMIC', 'RELIGIOUS', 'LITERARY', 'CULTURE_HISTORY'];
          const categoryKeyMap: Record<ExternalCategoryKey, keyof DiscoveryPageResponse['boards']> = {
            ACADEMIC: 'academic',
            RELIGIOUS: 'religious',
            LITERARY: 'literary',
            CULTURE_HISTORY: 'culture_history'
          };
          
          // Fetch each board independently so slow ones don't block others
          categories.forEach(async (cat) => {
            try {
              // Honor the global forceRefresh flag, but don't force just because state is empty
              // The backend has its own 24h cache logic.
              const boardPayload = await getDiscoveryBoard(userId, cat, forceRefresh);
              if (!active) return;
              
              const boardCards = mapDiscoveryBoardPayload(boardPayload);
              setPillarCardsByCategory(prev => ({
                ...prev,
                [cat]: boardCards
              }));

              // Update the cache with this new board data
              const currentCache = readDiscoveryPageCache(userId);
              if (currentCache) {
                const boardKey = categoryKeyMap[cat];
                currentCache.payload.boards[boardKey] = boardPayload;
                writeDiscoveryPageCache(currentCache);
              }
            } catch (err) {
              console.error(`Failed to load discovery board for ${cat}:`, err);
              // Fallback for this specific category if it fails
              if (active) {
                setPillarCardsByCategory(prev => ({
                  ...prev,
                  [cat]: fallbackPillarsByCategory(cat)
                }));
              }
            }
          });
        }

      } catch (error) {
        if (!active) return;
        const message = getFriendlyApiErrorMessage(error);
        if (cached && !forceRefresh) {
          setPageWarning('Showing the last successful discovery snapshot while live refresh is unavailable.');
          setViewMeta((prev) => ({ ...prev, hasCachedSnapshot: true }));
          setPageError(null);
        } else {
          setPageError(message);
          setPageWarning(null);
          setInnerSpaceCards([]);
          setPillarCardsByCategory(createEmptyPillarState());
          setViewMeta(EMPTY_VIEW_META);
        }
      } finally {
        if (active) {
          requestInFlightRef.current = false;
          setPageLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    loadPage();
    return () => { active = false; };
  }, [userId, refreshNonce]);

  // Visibility / focus-based stale-while-revalidate
  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;

    const handleFocusRefresh = () => {
      if (document.visibilityState === 'hidden' || requestInFlightRef.current) return;
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

  return {
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
  };
}
