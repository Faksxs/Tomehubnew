import React from 'react';
import { Book, FileText, Globe, PenTool, StickyNote, BarChart2, X, Library, User, Moon, Sun } from 'lucide-react';
import { ResourceType } from '../types';
import { useTheme } from '../contexts/ThemeContext';

interface SidebarProps {
  activeTab: ResourceType | 'NOTES' | 'DASHBOARD' | 'PROFILE';
  onTabChange: (tab: ResourceType | 'NOTES' | 'DASHBOARD' | 'PROFILE') => void;
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange, isOpen, onClose }) => {
  const { theme, toggleTheme } = useTheme();
  const menuItems = [
    { id: 'DASHBOARD', label: 'Dashboard', icon: BarChart2 },
    { id: 'BOOK', label: 'Books', icon: Book },
    { id: 'ARTICLE', label: 'Articles', icon: FileText },
    { id: 'WEBSITE', label: 'Websites', icon: Globe },
    { id: 'PERSONAL_NOTE', label: 'Personal Notes', icon: PenTool },
    { id: 'NOTES', label: 'All Notes', icon: StickyNote },
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
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transform transition-transform duration-300 ease-in-out flex flex-col shadow-xl lg:shadow-none h-full
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Logo Area */}
        <div className="p-6 flex items-center justify-between h-20 border-b border-slate-50 dark:border-slate-800">
          <div className="flex items-center gap-3 text-indigo-600 dark:text-indigo-500">
            <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-200 dark:shadow-none text-white">
              <Library size={20} strokeWidth={2.5} />
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight">TomeHub</h1>
          </div>
          <button onClick={onClose} className="lg:hidden p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-6 space-y-1 overflow-y-auto">
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
                  ? 'bg-indigo-50 text-indigo-700 shadow-sm dark:bg-indigo-900/20 dark:text-indigo-300'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
                  }`}
              >
                <Icon
                  size={20}
                  className={`transition-colors ${isActive ? 'text-indigo-600' : 'text-slate-400 group-hover:text-slate-500'}`}
                />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Profile Section */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800">
          <button
            onClick={() => {
              onTabChange('PROFILE');
              onClose();
            }}
            className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium transition-all duration-200 group ${activeTab === 'PROFILE'
              ? 'bg-indigo-50 text-indigo-700 shadow-sm dark:bg-indigo-900/20 dark:text-indigo-300'
              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
              }`}
          >
            <User
              size={20}
              className={`transition-colors ${activeTab === 'PROFILE' ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 group-hover:text-slate-500 dark:text-slate-500 dark:group-hover:text-slate-400'}`}
            />
            Profile
          </button>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-all duration-200 group mt-1"
          >
            {theme === 'light' ? (
              <>
                <Moon size={20} className="text-slate-400 group-hover:text-slate-500 dark:text-slate-500 dark:group-hover:text-slate-400" />
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
        <div className="p-4 border-t border-slate-100 dark:border-slate-800">
          <div className="bg-slate-50/80 dark:bg-slate-800/50 rounded-xl p-4 border border-slate-100 dark:border-slate-800">
            <p className="text-xs text-slate-500 dark:text-slate-400 font-medium mb-1">My Personal Library</p>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-semibold">Online</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};