/**
 * TomeHub Flow Service (Layer 4: Knowledge Stream)
 * Connects React frontend to Flow API endpoints
 */

import { getAuth } from 'firebase/auth';
import { API_BASE_URL } from './apiClient';


// ============================================================================
// AUTH HELPER
// ============================================================================

/**
 * Get Firebase Auth ID Token for API requests
 */
const getAuthToken = async (): Promise<string> => {
    const auth = getAuth();
    const user = auth.currentUser;

    if (!user) {
        throw new Error('User must be logged in to use Knowledge Stream');
    }

    return await user.getIdToken();
};

// ============================================================================
// TYPES
// ============================================================================

export type FlowMode = 'FOCUS' | 'EXPAND' | 'DISCOVER' | 'BRIDGE';
export type FeedbackAction = 'like' | 'dislike' | 'skip' | 'save';

export interface FlowCard {
    flow_id: string;
    chunk_id: string;
    content: string;
    title: string;
    author?: string;
    page_number?: number;
    source_type: 'personal' | 'pdf_chunk' | 'graph_bridge' | 'external';
    epistemic_level: 'A' | 'B' | 'C';
    reason?: string;
    zone: number;
}


export interface PivotInfo {
    type: string;
    message: string;
}

export interface FlowStartRequest {
    firebase_uid: string;
    anchor_type: 'note' | 'book' | 'author' | 'topic';
    anchor_id: string;
    mode?: FlowMode;
    horizon_value?: number; // 0.0 to 1.0
    resource_type?: string;
    category?: string;
}

export interface FlowStartResponse {
    session_id: string;
    initial_cards: FlowCard[];
    topic_label: string;
}

export interface FlowNextRequest {
    firebase_uid: string;
    session_id: string;
    batch_size?: number;
}

export interface FlowNextResponse {
    cards: FlowCard[];
    has_more: boolean;
    pivot_info?: PivotInfo;
    session_state?: {
        cards_shown: number;
        anchor_id?: string;
    };
}


export interface FlowFeedbackRequest {
    firebase_uid: string;
    session_id: string;
    chunk_id: string;
    action: FeedbackAction;
}

export interface FlowSessionInfo {
    session_id: string;
    cards_shown: number;
    horizon_value: number;
    mode: FlowMode;
    anchor_id: string;
}

// ============================================================================
// PREWARM CACHE (Layer 4 first-open latency reduction)
// ============================================================================

const FLOW_START_PREWARM_TTL_MS = 120_000;

type FlowStartPrewarmEntry = {
    response: FlowStartResponse;
    createdAt: number;
};

const flowStartPrewarmCache = new Map<string, FlowStartPrewarmEntry>();
const flowStartPrewarmInFlight = new Map<string, Promise<FlowStartResponse>>();

const normalizeFlowStartForKey = (request: FlowStartRequest): string => {
    const anchorType = request.anchor_type || 'note';
    const anchorId = request.anchor_id || '';
    const mode = request.mode || 'FOCUS';
    const horizon = Number(request.horizon_value ?? 0.25).toFixed(2);
    const resourceType = (request.resource_type || '').toUpperCase();
    const category = (request.category || '').toUpperCase();
    return [
        request.firebase_uid,
        anchorType,
        anchorId,
        mode,
        horizon,
        resourceType,
        category,
    ].join('|');
};

const isPrewarmFresh = (entry: FlowStartPrewarmEntry | undefined): entry is FlowStartPrewarmEntry => {
    if (!entry) return false;
    return (Date.now() - entry.createdAt) <= FLOW_START_PREWARM_TTL_MS;
};

/**
 * Prewarm default Flow start response in background.
 * - Deduplicates in-flight requests
 * - Keeps a short-lived cache entry for instant first open
 */
export async function prewarmFlowStartSession(request: FlowStartRequest): Promise<void> {
    const key = normalizeFlowStartForKey(request);
    const existing = flowStartPrewarmCache.get(key);
    if (isPrewarmFresh(existing)) {
        return;
    }

    const inflight = flowStartPrewarmInFlight.get(key);
    if (inflight) {
        await inflight;
        return;
    }

    const task = (async () => {
        const response = await startFlowSession(request);
        flowStartPrewarmCache.set(key, { response, createdAt: Date.now() });
        return response;
    })();

    flowStartPrewarmInFlight.set(key, task);
    try {
        await task;
    } finally {
        flowStartPrewarmInFlight.delete(key);
    }
}

/**
 * Consume (read-once) prewarmed Flow start response if available and fresh.
 */
export function consumePrewarmedFlowStartSession(request: FlowStartRequest): FlowStartResponse | null {
    const key = normalizeFlowStartForKey(request);
    const entry = flowStartPrewarmCache.get(key);
    if (!isPrewarmFresh(entry)) {
        flowStartPrewarmCache.delete(key);
        return null;
    }

    flowStartPrewarmCache.delete(key);
    return entry.response;
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

/**
 * Start a new Knowledge Stream session
 */
export async function startFlowSession(request: FlowStartRequest): Promise<FlowStartResponse> {
    if (!request.firebase_uid) {
        throw new Error('User must be authenticated');
    }

    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/flow/start`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start flow session');
    }

    return response.json();
}

/**
 * Get the next batch of cards
 */
export async function getNextFlowBatch(request: FlowNextRequest): Promise<FlowNextResponse> {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/flow/next`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to get next batch');
    }

    return response.json();
}

/**
 * Submit feedback on a card
 */
export async function sendFlowFeedback(request: FlowFeedbackRequest): Promise<{ success: boolean }> {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/flow/feedback`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to send feedback');
    }

    return response.json();
}

export async function adjustFlowHorizon(
    sessionId: string,
    horizonValue: number,
    firebaseUid: string
): Promise<{ success: boolean; new_horizon: number }> {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/flow/adjust`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        body: JSON.stringify({
            session_id: sessionId,
            horizon_value: horizonValue,
            firebase_uid: firebaseUid,
        }),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to adjust horizon');
    }

    return response.json();
}

/**
 * Reset the session anchor (Change Topic)
 */
export async function resetFlowAnchor(
    sessionId: string,
    anchorType: string,
    anchorId: string,
    firebaseUid: string,
    resourceType?: string,
    category?: string
): Promise<{ success: boolean; topic_label: string; pivot_info?: PivotInfo }> {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/flow/reset-anchor`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        },
        body: JSON.stringify({
            session_id: sessionId,
            anchor_type: anchorType,
            anchor_id: anchorId,
            firebase_uid: firebaseUid,
            resource_type: resourceType,
            category: category
        }),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to reset anchor');
    }

    return response.json();
}

/**
 * Get session info
 */
export async function getFlowSessionInfo(sessionId: string): Promise<FlowSessionInfo> {
    const idToken = await getAuthToken();

    const response = await fetch(`${API_BASE_URL}/api/flow/session/${sessionId}`, {
        headers: {
            'Authorization': `Bearer ${idToken}`
        }
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to get session info');
    }

    return response.json();
}

