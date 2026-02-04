import React from 'react';

export const CATEGORIES = [
    "Felsefe", "Sosyoloji", "Politika", "Ekonomi", "Edebiyat",
    "Roman", "Bilim", "Tarih", "Inanç", "Sanat",
    "Psikoloji", "Hukuk", "Eğitim"
];

interface CategorySelectorProps {
    activeCategory: string | null;
    onCategoryChange: (category: string | null) => void;
}

export const CategorySelector: React.FC<CategorySelectorProps> = ({ activeCategory, onCategoryChange }) => {
    return (
        <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between px-1">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Keşif Alanları</span>
            </div>
            <div className="flex flex-col gap-2">
                <button
                    onClick={() => onCategoryChange(null)}
                    className={`w-full text-left px-4 py-2 rounded-xl text-sm font-bold transition-all duration-300 border ${activeCategory === null
                        ? 'bg-[#CC561E]/10 border-[#CC561E] text-[#CC561E] shadow-[0_0_12px_rgba(204,86,30,0.25)]'
                        : 'bg-white border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50'
                        }`}
                >
                    Tümü
                </button>
                {CATEGORIES.map((cat) => (
                    <button
                        key={cat}
                        onClick={() => onCategoryChange(cat)}
                        className={`w-full text-left px-4 py-2 rounded-xl text-sm font-bold transition-all duration-300 border ${activeCategory === cat
                            ? 'bg-[#CC561E]/10 border-[#CC561E] text-[#CC561E] shadow-[0_0_12px_rgba(204,86,30,0.25)]'
                            : 'bg-white border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50'
                            }`}
                    >
                        {cat}
                    </button>
                ))}
            </div>
        </div>
    );
};
