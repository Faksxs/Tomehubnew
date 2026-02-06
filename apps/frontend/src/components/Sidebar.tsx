import React from 'react';
import { X, Library, User, Moon, Sun, Search, Upload } from 'lucide-react';
import logo from '../assets/logo_v5.png';
import { ResourceType } from '../types';
import { useTheme } from '../contexts/ThemeContext';
import {
  KnowledgeBaseLogo,
  SmartSearchLogo,
  DeepChatbotLogo,
  FluxLogo,
  BooksLogo,
  ArticlesLogo,
  WebsitesLogo,
  NotesLogo,
  HighlightsLogo
} from './ui/FeatureLogos';

interface SidebarProps {
  activeTab: ResourceType | 'NOTES' | 'DASHBOARD' | 'PROFILE' | 'RAG_SEARCH' | 'INGEST' | 'SMART_SEARCH' | 'FLOW';
  onTabChange: (tab: ResourceType | 'NOTES' | 'DASHBOARD' | 'PROFILE' | 'RAG_SEARCH' | 'INGEST' | 'SMART_SEARCH' | 'FLOW') => void;
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange, isOpen, onClose }) => {
  const { theme, toggleTheme } = useTheme();
  const menuItems = [
    { id: 'DASHBOARD', label: 'Dashboard', icon: KnowledgeBaseLogo },
    { id: 'SMART_SEARCH', label: 'Search (Layer 2)', icon: SmartSearchLogo },
    { id: 'RAG_SEARCH', label: 'LagosChat (Layer 3)', icon: DeepChatbotLogo },
    { id: 'FLOW', label: 'Flux (Layer 4)', icon: FluxLogo }, // Changed from KnowledgeStreamLogo
    { id: 'BOOK', label: 'Books', icon: BooksLogo },
    { id: 'ARTICLE', label: 'Articles', icon: ArticlesLogo },
    { id: 'WEBSITE', label: 'Websites', icon: WebsitesLogo },
    { id: 'PERSONAL_NOTE', label: 'Personal Notes', icon: NotesLogo },
    { id: 'NOTES', label: 'All Notes', icon: HighlightsLogo },
  ];

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50 w-[269px] bg-[#262D40] border-r border-white/10 transform transition-transform duration-300 ease-in-out flex flex-col shadow-xl lg:shadow-none h-full
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Logo Area */}
        <div className="px-3 pt-0 pb-3 flex flex-col items-center border-b border-white/10 bg-[#262D40] gap-2 relative">
          <img
            src={logo}
            alt="TomeHub Icon"
            className="h-[77px] w-auto object-contain brightness-110 drop-shadow-md"
          />
          <h1 className="text-2xl font-bold text-white tracking-tighter leading-none">TomeHub</h1>

          <button
            onClick={onClose}
            className="lg:hidden absolute top-2 right-3 p-1 hover:bg-white/10 rounded-full text-white/70 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 pt-2 pb-6 space-y-1 overflow-y-auto">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onTabChange(item.id as any);
                  onClose(); // Close on mobile when clicked
                }}
                className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium transition-all duration-200 group ${isActive
                  ? 'bg-white/10 text-white shadow-sm border-r-2 border-[#CC561E]'
                  : 'text-white/70 hover:bg-white/5 hover:text-white'
                  }`}
              >
                <Icon
                  size={20}
                  className={`transition-colors ${isActive ? 'text-[#CC561E]' : 'text-white/60 group-hover:text-white'}`}
                />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Profile Section */}
        <div className="p-3 border-t border-white/10">
          <button
            onClick={() => {
              onTabChange('PROFILE');
              onClose();
            }}
            className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium transition-all duration-200 group ${activeTab === 'PROFILE'
              ? 'bg-white/10 text-white shadow-sm border-r-2 border-[#CC561E]'
              : 'text-white/70 hover:bg-white/5 hover:text-white'
              }`}
          >
            <User
              size={20}
              className={`transition-colors ${activeTab === 'PROFILE' ? 'text-[#CC561E]' : 'text-white/60 group-hover:text-white'}`}
            />
            Profile
          </button>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium text-white/70 hover:bg-white/5 hover:text-white transition-all duration-200 group mt-1"
          >
            {theme === 'light' ? (
              <>
                <Moon size={20} className="text-white/60 group-hover:text-white" />
                Dark Mode
              </>
            ) : (
              <>
                <Sun size={20} className="text-amber-400" />
                Light Mode
              </>
            )}
          </button>
        </div>

        {/* Footer info */}
        <div className="p-4 border-t border-white/10">
          <div className="bg-white/5 rounded-xl p-4 border border-white/10">
            <p className="text-xs text-white/70 font-medium mb-1">My Personal Library</p>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[#CC561E] animate-pulse"></div>
              <p className="text-[10px] text-white/50 uppercase tracking-wider font-semibold">Online</p>
            </div>
          </div>
        </div>
      </aside >
    </>
  );
};
