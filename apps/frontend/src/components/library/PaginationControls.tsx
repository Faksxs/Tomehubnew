import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationControlsProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const getPageNumbers = (currentPage: number, totalPages: number): Array<number | string> => {
  const pages: Array<number | string> = [];
  const maxVisiblePages = 5;

  if (totalPages <= maxVisiblePages) {
    for (let i = 1; i <= totalPages; i += 1) pages.push(i);
    return pages;
  }

  if (currentPage <= 3) {
    pages.push(1, 2, 3, 4, '...', totalPages);
    return pages;
  }

  if (currentPage >= totalPages - 2) {
    pages.push(1, '...', totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
    return pages;
  }

  pages.push(1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages);
  return pages;
};

export const PaginationControls: React.FC<PaginationControlsProps> = ({
  currentPage,
  totalPages,
  onPageChange,
}) => {
  if (totalPages <= 1) return null;

  return (
    <div className="flex justify-center items-center gap-2 mt-4 md:mt-12 select-none">
      <button
        onClick={() => onPageChange(Math.max(currentPage - 1, 1))}
        disabled={currentPage === 1}
        className="p-2 rounded-lg border border-[#E6EAF2] dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 hover:text-[#262D40] dark:hover:text-[#262D40]/82 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft size={20} />
      </button>

      <div className="flex items-center gap-1">
        {getPageNumbers(currentPage, totalPages).map((page, idx) => (
          <React.Fragment key={idx}>
            {page === '...' ? (
              <span className="px-2 text-slate-400">...</span>
            ) : (
              <button
                onClick={() => onPageChange(page as number)}
                className={`w-8 h-8 md:w-10 md:h-10 rounded-lg text-sm font-medium transition-colors ${currentPage === page
                  ? 'bg-[#262D40]/40 text-white shadow-md shadow-[#262D40]/12 dark:shadow-none'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 hover:text-[#262D40] dark:hover:text-[#262D40]/82'
                  }`}
              >
                {page}
              </button>
            )}
          </React.Fragment>
        ))}
      </div>

      <button
        onClick={() => onPageChange(Math.min(currentPage + 1, totalPages))}
        disabled={currentPage === totalPages}
        className="p-2 rounded-lg border border-[#E6EAF2] dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-slate-800 hover:text-[#262D40] dark:hover:text-[#262D40]/82 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronRight size={20} />
      </button>
    </div>
  );
};
