import React from 'react';
import { ArrowUpDown, Filter, Hash, ListFilter, Loader2, Search, Star } from 'lucide-react';

interface LibraryFiltersBarProps {
  searchPlaceholder: string;
  localInput: string;
  onLocalInputChange: (value: string) => void;
  showSearchLoading: boolean;
  showFavoritesToggle: boolean;
  isFavoritesActive: boolean;
  onToggleFavorites: () => void;
  showStandardFilters: boolean;
  statusFilter: string;
  onStatusChange: (value: string) => void;
  sortOption: 'date_desc' | 'date_asc' | 'title_asc';
  onSortChange: (value: 'date_desc' | 'date_asc' | 'title_asc') => void;
  showCategoryFilter: boolean;
  categoryFilter?: string | null;
  categoryOptions: string[];
  onCategoryChange?: (value: string | null) => void;
  showPublisherFilter: boolean;
  publisherFilter: string;
  onPublisherFilterChange: (value: string) => void;
  showMediaTypeFilter: boolean;
  mediaTypeFilter: 'ALL' | 'MOVIE' | 'SERIES';
  onMediaTypeFilterChange: (value: 'ALL' | 'MOVIE' | 'SERIES') => void;
  isMediaTab: boolean;
  onPageReset: () => void;
}

export const LibraryFiltersBar: React.FC<LibraryFiltersBarProps> = ({
  searchPlaceholder,
  localInput,
  onLocalInputChange,
  showSearchLoading,
  showFavoritesToggle,
  isFavoritesActive,
  onToggleFavorites,
  showStandardFilters,
  statusFilter,
  onStatusChange,
  sortOption,
  onSortChange,
  showCategoryFilter,
  categoryFilter,
  categoryOptions,
  onCategoryChange,
  showPublisherFilter,
  publisherFilter,
  onPublisherFilterChange,
  showMediaTypeFilter,
  mediaTypeFilter,
  onMediaTypeFilterChange,
  isMediaTab,
  onPageReset,
}) => {
  return (
    <div className="mb-3 w-full rounded-[26px] border border-[#E6EAF2] bg-white/85 p-2 shadow-[0_14px_40px_rgba(38,45,64,0.05)] backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900/85 md:mb-8 md:p-4">
      <div className="mb-2 hidden items-center justify-between px-1 md:flex">
        <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
          Find, filter, refine
        </div>
        <div className="text-[11px] text-slate-400 dark:text-slate-500">
          Search and library controls
        </div>
      </div>
      <div className="flex flex-col gap-2 md:flex-row md:gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-5 md:h-5" />
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={localInput}
            onChange={(e) => onLocalInputChange(e.target.value)}
            className={`w-full rounded-2xl border border-[#E6EAF2] bg-white px-4 py-2.5 pl-8 text-[11px] text-slate-900 outline-none transition-all placeholder-slate-400 focus:border-[#CC561E]/35 focus:ring-4 focus:ring-[#CC561E]/10 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder-slate-500 md:pl-10 md:text-base ${showFavoritesToggle ? 'pr-10' : 'pr-4'} md:pr-4`}
          />
          {showSearchLoading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <Loader2 size={16} className="animate-spin text-[#CC561E]" />
            </div>
          )}

          {showFavoritesToggle && (
            <button
              onClick={onToggleFavorites}
              className={`absolute right-2 top-1/2 flex shrink-0 -translate-y-1/2 items-center justify-center rounded-xl border p-1.5 transition-all md:hidden ${isFavoritesActive
                ? 'border-orange-200 bg-orange-100 text-orange-600 dark:border-orange-800 dark:bg-orange-900/30 dark:text-orange-400'
                : 'border-[#E6EAF2] bg-white text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500'
                }`}
              title={isFavoritesActive ? 'Show All' : 'Show Favorites Only'}
            >
              <Star size={14} fill={isFavoritesActive ? 'currentColor' : 'none'} />
            </button>
          )}
        </div>

        {showFavoritesToggle && (
          <button
            onClick={onToggleFavorites}
            className={`hidden shrink-0 items-center justify-center rounded-2xl border p-2.5 transition-all md:flex ${isFavoritesActive
              ? 'border-orange-200 bg-orange-100 text-orange-600 shadow-[0_8px_20px_rgba(251,146,60,0.14)] dark:border-orange-800 dark:bg-orange-900/30 dark:text-orange-400'
              : 'border-[#E6EAF2] bg-white text-slate-400 hover:bg-[#F3F5FA] dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500 dark:hover:bg-slate-700'
              }`}
            title={isFavoritesActive ? 'Show All' : 'Show Favorites Only'}
          >
            <Star size={20} className="md:w-5 md:h-5" fill={isFavoritesActive ? 'currentColor' : 'none'} />
          </button>
        )}

        {showStandardFilters && (
          <div className="grid grid-cols-2 items-center gap-2 md:flex">
            <div className="relative min-w-[100px] md:min-w-[160px]">
              <Filter className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
              <select
                value={statusFilter}
                onChange={(e) => {
                  onStatusChange(e.target.value);
                  onPageReset();
                }}
                className="w-full cursor-pointer appearance-none rounded-2xl border border-[#E6EAF2] bg-white py-2 pl-7 pr-7 text-xs font-medium text-slate-700 transition-all hover:border-slate-300 focus:border-[#CC561E]/35 focus:ring-4 focus:ring-[#CC561E]/10 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-600 md:py-2.5 md:pl-9 md:pr-8 md:text-sm"
              >
                <option value="ALL">All</option>
                <option value="FAVORITES">Favorites</option>
                <option value="HIGHLIGHTS">Highlight</option>
                <optgroup label="Status">
                  <option value="To Read">{isMediaTab ? 'Watchlist' : 'To Read'}</option>
                  <option value="Reading">{isMediaTab ? 'Watching' : 'Reading'}</option>
                  <option value="Finished">{isMediaTab ? 'Watched' : 'Finished'}</option>
                </optgroup>
                {showCategoryFilter && (
                  <optgroup label="Inventory">
                    <option value="On Shelf">On Shelf</option>
                    <option value="Digital">Digital</option>
                    <option value="Lent Out">Lent Out</option>
                    <option value="Lost">Lost</option>
                  </optgroup>
                )}
              </select>
            </div>

            <div className="relative min-w-[100px] md:min-w-[160px]">
              <ArrowUpDown className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
              <select
                value={sortOption}
                onChange={(e) => {
                  onSortChange(e.target.value as 'date_desc' | 'date_asc' | 'title_asc');
                  onPageReset();
                }}
                className="w-full cursor-pointer appearance-none rounded-2xl border border-[#E6EAF2] bg-white py-2 pl-7 pr-7 text-xs font-medium text-slate-700 transition-all hover:border-slate-300 focus:border-[#CC561E]/35 focus:ring-4 focus:ring-[#CC561E]/10 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-600 md:py-2.5 md:pl-9 md:pr-8 md:text-sm"
              >
                <option value="date_desc">Newest</option>
                <option value="date_asc">Oldest</option>
                <option value="title_asc">A-Z</option>
              </select>
            </div>

            {showCategoryFilter && (
              <div className="relative min-w-[140px] md:min-w-[180px]">
                <Hash className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
                <select
                  value={categoryFilter || ''}
                  onChange={(e) => onCategoryChange?.(e.target.value || null)}
                  className="w-full cursor-pointer appearance-none rounded-2xl border border-[#E6EAF2] bg-white py-2 pl-7 pr-7 text-xs font-medium text-slate-700 transition-all hover:border-slate-300 focus:border-[#CC561E]/35 focus:ring-4 focus:ring-[#CC561E]/10 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-600 md:py-2.5 md:pl-9 md:pr-8 md:text-sm"
                >
                  <option value="">All categories</option>
                  {categoryOptions.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {showPublisherFilter && (
              <input
                type="text"
                placeholder="Journal..."
                value={publisherFilter}
                onChange={(e) => {
                  onPublisherFilterChange(e.target.value);
                  onPageReset();
                }}
                className="hidden min-w-[140px] rounded-2xl border border-[#E6EAF2] bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 transition-all focus:border-[#CC561E]/35 focus:ring-4 focus:ring-[#CC561E]/10 dark:border-slate-700 dark:bg-slate-800 dark:text-white dark:placeholder-slate-500 md:block"
              />
            )}

            {showMediaTypeFilter && (
              <div className="relative min-w-[140px] md:min-w-[180px]">
                <ListFilter className="absolute left-2 md:left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 w-3.5 h-3.5 md:w-4 md:h-4" />
                <select
                  value={mediaTypeFilter}
                  onChange={(e) => {
                    onMediaTypeFilterChange(e.target.value as 'ALL' | 'MOVIE' | 'SERIES');
                    onPageReset();
                  }}
                  className="w-full cursor-pointer appearance-none rounded-2xl border border-[#E6EAF2] bg-white py-2 pl-7 pr-7 text-xs font-medium text-slate-700 transition-all hover:border-slate-300 focus:border-[#CC561E]/35 focus:ring-4 focus:ring-[#CC561E]/10 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-600 md:py-2.5 md:pl-9 md:pr-8 md:text-sm"
                >
                  <option value="ALL">All Media</option>
                  <option value="MOVIE">Movies</option>
                  <option value="SERIES">Series</option>
                </select>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
