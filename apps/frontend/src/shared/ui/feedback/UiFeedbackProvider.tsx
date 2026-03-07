import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

type ToastTone = 'info' | 'success' | 'warning' | 'error';
type ConfirmTone = 'default' | 'danger';

interface ToastPayload {
    title: string;
    description?: string;
    tone?: ToastTone;
    durationMs?: number;
}

interface ConfirmOptions {
    title: string;
    description?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    tone?: ConfirmTone;
}

interface PromptOptions extends ConfirmOptions {
    placeholder?: string;
    defaultValue?: string;
    validate?: (value: string) => string | null;
}

interface ToastItem extends Required<Pick<ToastPayload, 'title' | 'tone'>> {
    id: string;
    description?: string;
}

interface ConfirmState extends ConfirmOptions {
    resolve: (value: boolean) => void;
}

interface PromptState extends PromptOptions {
    resolve: (value: string | null) => void;
}

interface UiFeedbackContextValue {
    showToast: (payload: ToastPayload) => void;
    confirm: (options: ConfirmOptions) => Promise<boolean>;
    prompt: (options: PromptOptions) => Promise<string | null>;
}

const UiFeedbackContext = createContext<UiFeedbackContextValue | undefined>(undefined);

const toastToneStyles: Record<ToastTone, string> = {
    info: 'border-slate-200/90 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(244,247,252,0.96))] text-slate-900 dark:border-white/10 dark:bg-[linear-gradient(135deg,rgba(15,23,42,0.98),rgba(10,15,25,0.96))] dark:text-slate-100',
    success: 'border-emerald-200 bg-[linear-gradient(135deg,rgba(236,253,245,1),rgba(220,252,231,0.9))] text-emerald-900 dark:border-emerald-500/30 dark:bg-[linear-gradient(135deg,rgba(6,78,59,0.78),rgba(2,44,34,0.9))] dark:text-emerald-100',
    warning: 'border-amber-200 bg-[linear-gradient(135deg,rgba(255,251,235,1),rgba(254,243,199,0.92))] text-amber-900 dark:border-amber-500/30 dark:bg-[linear-gradient(135deg,rgba(120,53,15,0.8),rgba(69,26,3,0.92))] dark:text-amber-100',
    error: 'border-red-200 bg-[linear-gradient(135deg,rgba(254,242,242,1),rgba(254,226,226,0.94))] text-red-900 dark:border-red-500/30 dark:bg-[linear-gradient(135deg,rgba(127,29,29,0.82),rgba(69,10,10,0.92))] dark:text-red-100',
};

const confirmButtonStyles: Record<ConfirmTone, string> = {
    default: 'bg-[#262D40] text-white hover:bg-[#1e2433]',
    danger: 'bg-red-600 text-white hover:bg-red-700',
};

const ToastIcon = ({ tone }: { tone: ToastTone }) => {
    const className = 'h-4 w-4 shrink-0';
    if (tone === 'success') return <CheckCircle2 className={className} />;
    if (tone === 'warning') return <AlertTriangle className={className} />;
    if (tone === 'error') return <XCircle className={className} />;
    return <Info className={className} />;
};

export const UiFeedbackProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [toasts, setToasts] = useState<ToastItem[]>([]);
    const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
    const [promptState, setPromptState] = useState<PromptState | null>(null);
    const [promptValue, setPromptValue] = useState('');
    const [promptError, setPromptError] = useState<string | null>(null);
    const timeoutsRef = useRef<Record<string, number>>({});

    const dismissToast = useCallback((id: string) => {
        const timeoutId = timeoutsRef.current[id];
        if (timeoutId) {
            window.clearTimeout(timeoutId);
            delete timeoutsRef.current[id];
        }
        setToasts((current) => current.filter((toast) => toast.id !== id));
    }, []);

    const showToast = useCallback((payload: ToastPayload) => {
        const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const toast: ToastItem = {
            id,
            title: payload.title,
            description: payload.description,
            tone: payload.tone || 'info',
        };
        setToasts((current) => [...current, toast]);
        const durationMs = payload.durationMs ?? 4200;
        timeoutsRef.current[id] = window.setTimeout(() => {
            dismissToast(id);
        }, durationMs);
    }, [dismissToast]);

    const confirm = useCallback((options: ConfirmOptions) => {
        return new Promise<boolean>((resolve) => {
            setConfirmState({
                title: options.title,
                description: options.description,
                confirmLabel: options.confirmLabel,
                cancelLabel: options.cancelLabel,
                tone: options.tone,
                resolve,
            });
        });
    }, []);

    const prompt = useCallback((options: PromptOptions) => {
        return new Promise<string | null>((resolve) => {
            setPromptValue(options.defaultValue || '');
            setPromptError(null);
            setPromptState({
                ...options,
                resolve,
            });
        });
    }, []);

    const resolveConfirm = useCallback((accepted: boolean) => {
        setConfirmState((current) => {
            current?.resolve(accepted);
            return null;
        });
    }, []);

    const resolvePrompt = useCallback((accepted: boolean) => {
        setPromptState((current) => {
            if (!current) return null;
            if (!accepted) {
                current.resolve(null);
                setPromptValue('');
                setPromptError(null);
                return null;
            }

            const trimmed = promptValue.trim();
            const validationError = current.validate ? current.validate(trimmed) : null;
            if (validationError) {
                setPromptError(validationError);
                return current;
            }

            current.resolve(trimmed);
            setPromptValue('');
            setPromptError(null);
            return null;
        });
    }, [promptValue]);

    const contextValue = useMemo<UiFeedbackContextValue>(() => ({
        showToast,
        confirm,
        prompt,
    }), [confirm, prompt, showToast]);

    return (
        <UiFeedbackContext.Provider value={contextValue}>
            {children}

            <div className="pointer-events-none fixed inset-x-0 top-4 z-[120] flex justify-center px-4 sm:justify-end">
                <div className="flex w-full max-w-sm flex-col gap-3">
                    {toasts.map((toast) => (
                        <div
                            key={toast.id}
                            className={`pointer-events-auto overflow-hidden rounded-[22px] border shadow-[0_18px_38px_rgba(15,23,42,0.16)] backdrop-blur-md ${toastToneStyles[toast.tone]}`}
                        >
                            <div className="flex items-start gap-3 px-4 py-3.5">
                                <div className="mt-0.5 rounded-full bg-black/5 p-2 dark:bg-white/10">
                                    <ToastIcon tone={toast.tone} />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <p className="text-sm font-semibold">{toast.title}</p>
                                    {toast.description ? (
                                        <p className="mt-1 text-sm leading-6 opacity-80">{toast.description}</p>
                                    ) : null}
                                </div>
                                <button
                                    type="button"
                                    onClick={() => dismissToast(toast.id)}
                                    className="rounded-md p-1 opacity-70 transition hover:opacity-100"
                                    aria-label="Dismiss notification"
                                >
                                    <X className="h-4 w-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {confirmState ? (
                <div className="fixed inset-0 z-[130] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-md">
                    <div className="w-full max-w-md rounded-[30px] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-6 shadow-[0_30px_70px_rgba(15,23,42,0.24)] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,0.98))]">
                        <div className="flex items-start gap-3">
                            <div className="mt-0.5 rounded-2xl bg-slate-100 p-2.5 text-slate-700 dark:bg-white/10 dark:text-slate-200">
                                <AlertTriangle className="h-5 w-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                                    {confirmState.title}
                                </h3>
                                {confirmState.description ? (
                                    <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                        {confirmState.description}
                                    </p>
                                ) : null}
                            </div>
                        </div>

                        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                            <button
                                type="button"
                                onClick={() => resolveConfirm(false)}
                                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/5"
                            >
                                {confirmState.cancelLabel || 'Cancel'}
                            </button>
                            <button
                                type="button"
                                onClick={() => resolveConfirm(true)}
                                className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${confirmButtonStyles[confirmState.tone || 'default']}`}
                            >
                                {confirmState.confirmLabel || 'Confirm'}
                            </button>
                        </div>
                    </div>
                </div>
            ) : null}

            {promptState ? (
                <div className="fixed inset-0 z-[131] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-md">
                    <div className="w-full max-w-md rounded-[30px] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-6 shadow-[0_30px_70px_rgba(15,23,42,0.24)] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,0.98))]">
                        <div>
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                                {promptState.title}
                            </h3>
                            {promptState.description ? (
                                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                    {promptState.description}
                                </p>
                            ) : null}
                        </div>

                        <div className="mt-5">
                            <input
                                autoFocus
                                type="text"
                                value={promptValue}
                                onChange={(event) => {
                                    setPromptValue(event.target.value);
                                    if (promptError) setPromptError(null);
                                }}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter') {
                                        event.preventDefault();
                                        resolvePrompt(true);
                                    }
                                    if (event.key === 'Escape') {
                                        event.preventDefault();
                                        resolvePrompt(false);
                                    }
                                }}
                                placeholder={promptState.placeholder}
                                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-0 transition focus:border-[#262D40] focus:ring-4 focus:ring-[#262D40]/10 dark:border-white/10 dark:bg-slate-900 dark:text-slate-100"
                            />
                            {promptError ? (
                                <p className="mt-2 text-sm text-red-600 dark:text-red-300">{promptError}</p>
                            ) : null}
                        </div>

                        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                            <button
                                type="button"
                                onClick={() => resolvePrompt(false)}
                                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/5"
                            >
                                {promptState.cancelLabel || 'Cancel'}
                            </button>
                            <button
                                type="button"
                                onClick={() => resolvePrompt(true)}
                                className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${confirmButtonStyles[promptState.tone || 'default']}`}
                            >
                                {promptState.confirmLabel || 'Save'}
                            </button>
                        </div>
                    </div>
                </div>
            ) : null}
        </UiFeedbackContext.Provider>
    );
};

export const useUiFeedback = () => {
    const context = useContext(UiFeedbackContext);
    if (!context) {
        throw new Error('useUiFeedback must be used within UiFeedbackProvider');
    }
    return context;
};
