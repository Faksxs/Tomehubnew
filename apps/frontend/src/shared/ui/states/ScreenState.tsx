import React from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

type ScreenStateMode = 'loading' | 'empty' | 'error';

interface ScreenStateProps {
    mode: ScreenStateMode;
    title?: string;
    message?: string;
    icon?: React.ReactNode;
    actionLabel?: string;
    onAction?: () => void;
    fullScreen?: boolean;
}

const defaultTitles: Record<ScreenStateMode, string> = {
    loading: 'Loading',
    empty: 'Nothing here yet',
    error: 'Something went wrong',
};

export const ScreenState: React.FC<ScreenStateProps> = ({
    mode,
    title,
    message,
    icon,
    actionLabel,
    onAction,
    fullScreen = false,
}) => {
    const containerClass = fullScreen
        ? 'min-h-screen flex items-center justify-center px-6'
        : 'flex items-center justify-center px-6 py-16 md:py-20';

    const resolvedIcon = icon || (
        mode === 'loading'
            ? <Loader2 className="h-8 w-8 animate-spin text-[#262D40]/90" />
            : <AlertTriangle className="h-8 w-8 text-[#262D40]/80" />
    );

    return (
        <div className={containerClass}>
            <div className="relative w-full max-w-lg overflow-hidden rounded-[30px] border border-dashed border-slate-300 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.96))] px-6 py-10 text-center shadow-[0_24px_60px_rgba(15,23,42,0.08)] dark:border-slate-700 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,0.96))]">
                <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#CC561E]/35 to-transparent" />
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-[22px] bg-[#F3F5FA] text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] dark:bg-slate-800 dark:text-slate-200">
                    {resolvedIcon}
                </div>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.26em] text-slate-400 dark:text-slate-500">
                    System State
                </div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white md:text-xl">
                    {title || defaultTitles[mode]}
                </h3>
                {message ? (
                    <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500 dark:text-slate-400 md:text-[15px]">
                        {message}
                    </p>
                ) : null}
                {actionLabel && onAction ? (
                    <button
                        type="button"
                        onClick={onAction}
                        className="mt-6 rounded-2xl bg-[linear-gradient(135deg,#262D40_0%,#313a52_100%)] px-4 py-2.5 text-sm font-medium text-white shadow-[0_14px_28px_rgba(38,45,64,0.18)] transition hover:-translate-y-0.5 hover:bg-[#1e2433]"
                    >
                        {actionLabel}
                    </button>
                ) : null}
            </div>
        </div>
    );
};
