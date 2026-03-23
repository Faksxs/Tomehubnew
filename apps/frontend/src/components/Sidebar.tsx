import React from 'react';
import { X, User, Moon, Sun, Film, Compass } from 'lucide-react';
import logo from '../assets/logo_v9.png';
import { useTheme } from '../contexts/ThemeContext';
import { AppTab } from '../features/app/types';
import {
  KnowledgeBaseLogo,
  SmartSearchLogo,
  DeepChatbotLogo,
  FluxLogo,
  BooksLogo,
  ArticlesLogo,
  NotesLogo,
  HighlightsLogo
} from './ui/FeatureLogos';

interface SidebarProps {
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
  mediaLibraryEnabled?: boolean;
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange, mediaLibraryEnabled = false, isOpen, onClose }) => {
  const { theme, toggleTheme } = useTheme();

  const menuItems = [
    { id: 'DISCOVERY', label: 'Discovery', icon: Compass },
    { id: 'DASHBOARD', label: 'Dashboard', icon: KnowledgeBaseLogo },
    { id: 'SMART_SEARCH', label: 'Search (Layer 2)', icon: SmartSearchLogo },
    { id: 'RAG_SEARCH', label: 'LogosChat (Layer 3)', icon: DeepChatbotLogo },
    { id: 'FLOW', label: 'Flux (Layer 4)', icon: FluxLogo },
    { id: 'BOOK', label: 'Books', icon: BooksLogo },
    ...(mediaLibraryEnabled ? [{ id: 'MOVIE', label: 'Cinema', icon: Film }] : []),
    { id: 'ARTICLE', label: 'Articles', icon: ArticlesLogo },

    { id: 'PERSONAL_NOTE', label: 'Personal Notes', icon: NotesLogo },
    { id: 'NOTES', label: 'All Notes', icon: HighlightsLogo },
  ];

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      <aside
        className={`
        fixed lg:static inset-y-0 left-0 z-50 w-[269px] border-r border-white/10 transform transition-transform duration-300 ease-in-out flex flex-col shadow-2xl lg:shadow-none h-full
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}
        style={{
          background:
            'linear-gradient(180deg, rgba(38,45,64,0.98) 0%, rgba(31,37,53,0.98) 55%, rgba(24,29,43,1) 100%)',
        }}
      >
        <div className="relative flex flex-col items-center gap-2 border-b border-white/10 bg-white/[0.02] px-3 pb-4 pt-2">
          <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          <img
            src={logo}
            alt="TomeHub Icon"
            className="h-[50px] w-auto object-contain brightness-110 drop-shadow-[0_8px_22px_rgba(204,86,30,0.28)] lg:h-[77px]"
          />
          <div className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[8.5px] font-semibold uppercase tracking-[0.22em] text-white/55">
            Personal Knowledge OS
          </div>

          <button
            onClick={onClose}
            className="lg:hidden absolute right-3 top-3 rounded-full border border-white/10 bg-white/5 p-1.5 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 pb-6 pt-4">
          <div className="mb-3 px-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-white/35">
            Workspace
          </div>
          <div className="space-y-1.5">
            {menuItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    onTabChange(item.id as any);
                    onClose();
                  }}
                  className={`w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-[13px] font-medium transition-all duration-200 group lg:py-3 lg:text-sm ${isActive
                    ? 'border border-white/10 bg-white/[0.09] text-white shadow-[0_8px_24px_rgba(0,0,0,0.18)]'
                    : 'border border-transparent text-white/70 hover:border-white/5 hover:bg-white/[0.045] hover:text-white'
                    }`}
                >
                  <Icon
                    className={`h-[18px] w-[18px] transition-colors lg:h-5 lg:w-5 ${item.id === 'MOVIE'
                      ? 'text-[#CC561E]'
                      : (isActive ? 'text-[#CC561E]' : 'text-white/60 group-hover:text-white')
                      }`}
                  />
                  <span className="flex-1 text-left">{item.label}</span>
                  {isActive ? <span className="h-2 w-2 rounded-full bg-[#CC561E] shadow-[0_0_12px_rgba(204,86,30,0.75)]" /> : null}
                </button>
              );
            })}
          </div>
        </nav>

        <div className="p-3 border-t border-white/10">
          <button
            onClick={() => {
              onTabChange('PROFILE');
              onClose();
            }}
            className="w-full text-left rounded-xl border border-white/10 bg-gradient-to-br from-white/[0.08] via-white/[0.04] to-transparent p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] hover:bg-white/[0.06] transition-colors flex items-center justify-between"
          >
            <div>
              <p className="mb-0.5 text-[11px] font-medium text-white/80">My Personal Library</p>
              <div className="flex items-center gap-1.5">
                <div className="h-1.5 w-1.5 rounded-full bg-[#CC561E] animate-pulse" />
                <p className="text-[8.5px] font-semibold uppercase tracking-[0.15em] text-white/50">Online</p>
              </div>
            </div>

            <div
              onClick={(e) => {
                e.stopPropagation();
                toggleTheme();
              }}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/70 hover:text-white transition-colors border border-white/10"
              title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            >
              {theme === 'light' ? <Moon size={14} /> : <Sun size={14} className="text-amber-400" />}
            </div>
          </button>
        </div>
      </aside>
    </>
  );
};
