const localhostHosts = new Set(['localhost', '127.0.0.1']);

const localDefaultBase = 'http://127.0.0.1:5000';
const productionDefaultBase = 'https://api.tomehub.nl';

const configuredBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
const fallbackBase = localhostHosts.has(window.location.hostname)
    ? localDefaultBase
    : productionDefaultBase;

export const API_BASE_URL = (configuredBase || fallbackBase).replace(/\/+$/, '');

const backendStartHint = "Backend baglantisi kurulamadi. `apps/backend` klasorunde `python app.py` calistirin.";

export async function getFirebaseIdToken(): Promise<string> {
    const { auth } = await import('./firebaseClient');
    const user = auth.currentUser;
    if (!user) {
        throw new Error('Oturum dogrulamasi bulunamadi. Lutfen tekrar giris yapin.');
    }
    return user.getIdToken();
}

export async function fetchWithAuth(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const token = await getFirebaseIdToken();
    const headers = new Headers(init.headers || {});
    if (!headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    return fetch(input, { ...init, headers });
}

export async function parseApiErrorMessage(response: Response, fallbackMessage: string): Promise<string> {
    try {
        const payload = await response.json();
        const detail = payload?.detail || payload?.details || payload?.error;
        if (typeof detail === 'string' && detail.trim()) {
            return detail;
        }
    } catch {
        // Ignore json parse errors and fall back to a generic message.
    }
    return fallbackMessage;
}

export function getFriendlyApiErrorMessage(error: unknown): string {
    if (error instanceof TypeError && /fetch/i.test(error.message)) {
        return `${backendStartHint} (API: ${API_BASE_URL})`;
    }
    if (error instanceof Error && error.message) {
        return error.message;
    }
    return 'Beklenmeyen API hatasi';
}
