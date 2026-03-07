import React from 'react';
import { X } from 'lucide-react';

interface ActiveCategoryFilterPillProps {
  category: string;
  onClear: () => void;
}

export const ActiveCategoryFilterPill: React.FC<ActiveCategoryFilterPillProps> = ({
  category,
  onClear,
}) => {
  return (
    <div className="flex items-center gap-2 mb-4 md:mb-6">
      <span className="text-xs md:text-sm text-slate-500">Category:</span>
      <button
        className="flex items-center gap-2 px-3 py-1 bg-[rgba(204,86,30,0.1)] text-[#CC561E] rounded-full text-xs md:text-sm border border-[#CC561E]/20 shadow-sm"
        onClick={onClear}
      >
        <span className="font-semibold">{category}</span>
        <X size={14} />
      </button>
    </div>
  );
};
