
import React from 'react';

export const CATEGORIES = [
    "Felsefe", "Sosyoloji", "Politika", "Ekonomi", "Edebiyat",
    "Roman", "Bilim", "Tarih", "İnanç", "Sanat",
    "Psikoloji", "Hukuk", "Eğitim"
];

interface CategorySelectorProps {
    activeCategory: string | null;
    onCategoryChange: (category: string | null) => void;
}

export const CategorySelector: React.FC<CategorySelectorProps> = ({ activeCategory, onCategoryChange }) => {
    return (
        <div className="flex flex-col gap-3 mb-8">
            <div className="flex items-center justify-between px-1">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">Keşif Alanları</span>
            </div>
            <div className="flex flex-wrap gap-2 pb-2">
                <button
                    onClick={() => onCategoryChange(null)}
                    className={`px-4 py-1.5 rounded-full text-sm font-bold transition-all duration-300 border-2 ${activeCategory === null
                        ? 'bg-[#CC561E]/10 border-[#CC561E] text-[#CC561E] shadow-[0_0_15px_rgba(204,86,30,0.3)]'
                        : 'bg-white border-slate-200 text-slate-900 hover:border-slate-400 hover:bg-slate-50'
                        }`}
                >
                    Tümü
                </button>
                {CATEGORIES.map((cat) => (
                    <button
                        key={cat}
                        onClick={() => onCategoryChange(cat)}
                        className={`px-4 py-1.5 rounded-full text-sm font-bold transition-all duration-300 border-2 ${activeCategory === cat
                            ? 'bg-[#CC561E]/10 border-[#CC561E] text-[#CC561E] shadow-[0_0_15px_rgba(204,86,30,0.3)]'
                            : 'bg-white border-slate-200 text-slate-900 hover:border-slate-400 hover:bg-slate-50'
                            }`}
                    >
                        {cat}
                    </button>
                ))}
            </div>
        </div>
    );
};
