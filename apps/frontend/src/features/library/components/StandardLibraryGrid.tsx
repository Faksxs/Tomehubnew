import React from 'react';
import { AlertTriangle, CheckCircle, Film, Globe, Star, Trash2 } from 'lucide-react';
import { ArticlesLogo, BooksLogo } from '../../../components/ui/FeatureLogos';
import { LibraryItem, ReadingStatus, ResourceType } from '../../../types';

interface StandardLibraryGridProps {
  books: LibraryItem[];
  activeTab: ResourceType | 'NOTES' | 'DASHBOARD' | 'INSIGHTS' | 'INGEST' | 'FLOW' | 'RAG_SEARCH' | 'SMART_SEARCH' | 'PROFILE';
  isMediaTab: boolean;
  libraryCardDarkBg: string;
  onSelectBook: (book: LibraryItem) => void;
  onToggleFavorite: (id: string) => void;
  onDeleteBook: (id: string) => void;
  getCoverUrlForGrid: (coverUrl: string) => string;
}

const statusColors: Record<ReadingStatus, string> = {
  'To Read': 'bg-[#94A3B8]/15 text-[#94A3B8] border border-[#94A3B8]/40',
  'Reading': 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/40',
  'Finished': 'bg-[#22C55E]/15 text-[#22C55E] border border-[#22C55E]/40',
};

const resolveFooterText = (book: LibraryItem) => {
  if (book.type === 'BOOK') return book.publisher || '';
  if (book.type === 'MOVIE' || book.type === 'SERIES') return book.castTop?.slice(0, 2).join(', ') || 'Media';
  if (book.type === 'ARTICLE') return book.publisher || 'Journal';
  try {
    return book.url ? new URL(book.url).hostname : 'Web';
  } catch {
    return 'Web';
  }
};

export const StandardLibraryGrid: React.FC<StandardLibraryGridProps> = ({
  books,
  activeTab,
  isMediaTab,
  libraryCardDarkBg,
  onSelectBook,
  onToggleFavorite,
  onDeleteBook,
  getCoverUrlForGrid,
}) => {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 md:gap-6">
      {books.map((book) => (
        <div
          key={book.id}
          onClick={() => onSelectBook(book)}
          className={`bg-white ${libraryCardDarkBg} rounded-xl border border-[#E6EAF2] dark:border-slate-800 overflow-hidden hover:shadow-lg hover:-translate-y-1 transition-all cursor-pointer group flex flex-col h-full relative active:scale-[0.99]`}
        >
          <div className="h-[122px] md:h-40 bg-[#F3F5FA] dark:bg-slate-800 relative flex items-end justify-between overflow-hidden group-hover:opacity-95 transition-opacity">
            <div className="absolute top-2 right-2 z-40 flex gap-1">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleFavorite(book.id);
                }}
                className={`p-1.5 rounded-full shadow-sm backdrop-blur-sm border border-[#E6EAF2] dark:border-slate-800 transition-all ${book.isFavorite
                  ? 'bg-amber-100/90 dark:bg-amber-900/80 text-amber-500 dark:text-amber-400 opacity-100'
                  : 'bg-white/90 dark:bg-slate-900/90 text-slate-400 dark:text-slate-500 hover:text-amber-500 dark:hover:text-amber-400 opacity-0 group-hover:opacity-100 focus:opacity-100'
                  }`}
                title={book.isFavorite ? 'Remove from Favorites' : 'Add to Favorites'}
              >
                <Star size={14} className="md:w-4 md:h-4" fill={book.isFavorite ? 'currentColor' : 'none'} />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteBook(book.id);
                }}
                className="p-1.5 bg-white/90 dark:bg-slate-900/90 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-slate-900 dark:hover:text-white rounded-full shadow-sm backdrop-blur-sm border border-[#E6EAF2] dark:border-slate-800 transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                title="Delete Item"
              >
                <Trash2 size={14} className="md:w-4 md:h-4" />
              </button>

              {book.isIngested && (
                <div
                  className="p-1.5 bg-[#262D40]/90 dark:bg-[#262D40]/90 text-white rounded-full shadow-sm backdrop-blur-sm border border-[#262D40]/50 dark:border-[#262D40]/50 transition-all z-40"
                  title="Added to AI Library"
                >
                  <CheckCircle size={14} className="md:w-4 md:h-4" fill="currentColor" />
                </div>
              )}
            </div>

            <div className="absolute inset-0 flex items-center justify-center bg-[#F3F5FA] dark:bg-slate-800 transition-colors group-hover:bg-[#EDF1F8] dark:group-hover:bg-slate-700">
              <div className="relative">
                <div className="absolute inset-0 bg-[#262D40]/20 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <div className="relative p-4 rounded-full">
                  {book.type === 'BOOK' ? <BooksLogo size={48} className="text-[#262D40] dark:text-white/80 drop-shadow-[0_0_8px_rgba(38,45,64,0.35)]" /> :
                    (book.type === 'MOVIE' || book.type === 'SERIES') ? <Film size={48} className="text-[#262D40] dark:text-white/80 drop-shadow-[0_0_8px_rgba(38,45,64,0.35)]" /> :
                      <ArticlesLogo size={48} className="text-[#262D40] dark:text-white/80 drop-shadow-[0_0_8px_rgba(38,45,64,0.35)]" />}
                </div>
              </div>
            </div>

            {(book.type === 'BOOK' || book.type === 'MOVIE' || book.type === 'SERIES') && book.coverUrl && (
              <>
                <img
                  src={getCoverUrlForGrid(book.coverUrl)}
                  alt={book.title}
                  loading="lazy"
                  decoding="async"
                  className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105 z-10"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                    const gradient = e.currentTarget.nextElementSibling;
                    if (gradient) gradient.classList.add('hidden');
                  }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 via-slate-900/20 to-transparent z-20 pointer-events-none" />
              </>
            )}

            {book.type !== 'BOOK' && (
              <div className="absolute inset-0 bg-gradient-to-t from-slate-900/60 via-transparent to-transparent z-20 pointer-events-none" />
            )}

            <div className="relative z-30 p-1.5 md:p-4 w-full flex justify-between items-end">
              <div className={`text-[8px] md:text-xs font-bold px-1.5 md:px-2.5 py-1 md:py-1.5 rounded-full shadow-lg backdrop-blur-md flex items-center gap-1.5 ${(book.type === 'BOOK' && book.coverUrl) || book.type !== 'BOOK' ? 'bg-slate-900/80 text-white border border-white/20' : statusColors[book.readingStatus]}`}>
                {isMediaTab && book.readingStatus === 'Reading' && (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-500"></span>
                  </span>
                )}
                {isMediaTab
                  ? (book.readingStatus === 'To Read' ? 'Watchlist' : (book.readingStatus === 'Reading' ? 'Watching' : 'Watched'))
                  : book.readingStatus}
              </div>

              <div className="flex gap-0.5 md:gap-1">
                {book.type === 'BOOK' && book.status === 'Lent Out' && (
                  <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-[#F59E0B] text-white flex items-center justify-center shadow-sm border border-white/20" title="Lent Out">
                    <AlertTriangle size={10} className="md:w-3 md:h-3" />
                  </div>
                )}
                {book.type === 'BOOK' && book.status === 'Lost' && (
                  <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-[#F43F5E] text-white flex items-center justify-center shadow-sm border border-white/20" title="Lost">
                    <AlertTriangle size={10} className="md:w-3 md:h-3" />
                  </div>
                )}
                {book.type === 'BOOK' && book.status === 'Digital' && (
                  <div className="w-4 h-4 md:w-6 md:h-6 rounded-full bg-[#0EA5E9] text-white flex items-center justify-center shadow-sm border border-white/20" title="Digital">
                    <Globe size={10} className="md:w-3 md:h-3" />
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="p-2.5 md:p-5 flex-1 flex flex-col">
            <h3 className="font-bold text-sm md:text-lg text-slate-900 dark:text-white leading-tight mb-0.5 md:mb-1 line-clamp-2 group-hover:text-[#262D40] dark:group-hover:text-[#262D40] transition-colors">
              {book.title}
            </h3>
            <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm mb-2 md:mb-4 line-clamp-1">{book.author}</p>

            <div className="mt-auto pt-2 md:pt-4 border-t border-slate-50 dark:border-slate-800 flex justify-between items-center text-[10px] md:text-xs text-slate-400 dark:text-slate-500">
              <span className="truncate max-w-[70%]">
                {resolveFooterText(book)}
              </span>
              {book.type === 'ARTICLE' && book.publicationYear && (
                <span className="bg-[#F3F5FA] dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500 dark:text-slate-400 font-mono">
                  {book.publicationYear}
                </span>
              )}
              {(book.type === 'MOVIE' || book.type === 'SERIES') && book.publicationYear && (
                <span className="bg-[#F3F5FA] dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500 dark:text-slate-400 font-mono">
                  {book.publicationYear}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
