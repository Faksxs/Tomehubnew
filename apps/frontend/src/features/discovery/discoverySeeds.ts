import type { DiscoveryCategoryName } from '../../services/backendApiService';

const DISCOVERY_PROMPT_SEED_KEY = 'tomehub:discovery:prompt-seed';
const DISCOVERY_FLOW_SEED_KEY = 'tomehub:discovery:flow-seed';
const DISCOVERY_CATEGORY_KEY = 'tomehub:discovery:last-category';

export interface DiscoveryPromptSeed {
    prompt: string;
}

export interface DiscoveryFlowSeed {
    anchorId: string;
    anchorLabel: string;
    category?: DiscoveryCategoryName | null;
}

const readStorage = <T,>(key: string): T | null => {
    if (typeof window === 'undefined') return null;
    try {
        const raw = window.sessionStorage.getItem(key);
        if (!raw) return null;
        return JSON.parse(raw) as T;
    } catch {
        return null;
    }
};

const writeStorage = (key: string, value: unknown): void => {
    if (typeof window === 'undefined') return;
    try {
        window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
        // ignore storage failures
    }
};

const consumeStorage = <T,>(key: string): T | null => {
    if (typeof window === 'undefined') return null;
    const value = readStorage<T>(key);
    try {
        window.sessionStorage.removeItem(key);
    } catch {
        // ignore storage failures
    }
    return value;
};

export const persistDiscoveryPromptSeed = (prompt: string): void => {
    if (!prompt.trim()) return;
    writeStorage(DISCOVERY_PROMPT_SEED_KEY, { prompt: prompt.trim() });
};

export const consumeDiscoveryPromptSeed = (): DiscoveryPromptSeed | null =>
    consumeStorage<DiscoveryPromptSeed>(DISCOVERY_PROMPT_SEED_KEY);

export const persistDiscoveryFlowSeed = (seed: DiscoveryFlowSeed): void => {
    if (!seed.anchorId.trim()) return;
    writeStorage(DISCOVERY_FLOW_SEED_KEY, seed);
};

export const consumeDiscoveryFlowSeed = (): DiscoveryFlowSeed | null =>
    consumeStorage<DiscoveryFlowSeed>(DISCOVERY_FLOW_SEED_KEY);

export const readLastDiscoveryCategory = (): DiscoveryCategoryName | null => {
    if (typeof window === 'undefined') return null;
    try {
        const value = window.localStorage.getItem(DISCOVERY_CATEGORY_KEY);
        if (value === 'ACADEMIC' || value === 'RELIGIOUS' || value === 'LITERARY' || value === 'CULTURE_HISTORY') {
            return value;
        }
    } catch {
        // ignore storage failures
    }
    return null;
};

export const persistLastDiscoveryCategory = (category: DiscoveryCategoryName): void => {
    if (typeof window === 'undefined') return;
    try {
        window.localStorage.setItem(DISCOVERY_CATEGORY_KEY, category);
    } catch {
        // ignore storage failures
    }
};
