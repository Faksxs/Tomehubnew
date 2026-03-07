import React from 'react';
import { Menu, Plus } from 'lucide-react';

interface LibraryPageHeaderProps {
  title: string;
  subtitle: string;
  Icon: React.ElementType;
  primaryActionLabel: string;
  onPrimaryAction: () => void;
  onMobileMenuClick: () => void;
}

export const LibraryPageHeader: React.FC<LibraryPageHeaderProps> = ({
  title,
  subtitle,
  Icon,
  primaryActionLabel,
  onPrimaryAction,
  onMobileMenuClick,
}) => {
  return (
    <div className="relative mb-3 overflow-hidden rounded-[28px] border border-[#E6EAF2] bg-white/80 px-3 py-3 shadow-[0_16px_50px_rgba(38,45,64,0.06)] backdrop-blur-sm dark:border-white/10 dark:bg-slate-950/70 md:mb-8 md:px-5 md:py-5">
      <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-40 bg-[radial-gradient(circle_at_top_right,rgba(204,86,30,0.14),transparent_60%)] md:block" />
      <div className="flex items-center justify-between gap-3">
      <div className="flex flex-1 items-center gap-2 overflow-hidden md:gap-4">
        <button
          onClick={onMobileMenuClick}
          className="lg:hidden -ml-1 shrink-0 rounded-xl border border-[#E6EAF2] bg-white/75 p-2 text-slate-600 transition-colors hover:bg-[#F3F5FA] dark:border-white/10 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
        >
          <Menu size={18} className="md:w-6 md:h-6" />
        </button>

        <div className="flex items-center gap-3">
          <div className="hidden rounded-2xl border border-[#262D40]/10 bg-[linear-gradient(135deg,#262D40_0%,#38425f_100%)] p-3 shadow-[0_14px_30px_rgba(38,45,64,0.18)] md:flex">
            <Icon size={24} className="text-white" />
          </div>
          <div className="min-w-0 flex flex-col justify-center">
            <div className="mb-1 hidden text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-400 dark:text-slate-500 md:block">
              Library Space
            </div>
            <h1 className="truncate text-lg font-bold leading-none tracking-tight text-slate-900 dark:text-white md:text-3xl">
              {title}
            </h1>
            <p className="mt-1 truncate text-[10px] font-medium text-slate-500 dark:text-slate-400 md:text-sm">
              {subtitle}
            </p>
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onPrimaryAction}
          className="shrink-0 rounded-2xl bg-[linear-gradient(135deg,#262D40_0%,#313a52_100%)] px-2.5 py-2 text-white shadow-[0_14px_30px_rgba(38,45,64,0.22)] transition-all hover:-translate-y-0.5 hover:shadow-[0_18px_34px_rgba(38,45,64,0.25)] active:scale-95 dark:shadow-none md:px-5 md:py-3"
        >
          <span className="flex items-center gap-1.5 font-medium">
            <Plus size={14} className="md:h-5 md:w-5" />
            <span className="text-[10px] md:text-base">{primaryActionLabel}</span>
          </span>
        </button>
      </div>
      </div>
    </div>
  );
};
