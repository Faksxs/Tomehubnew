import React from 'react';

export const CATEGORIES = [
    "Felsefe", "Sosyoloji", "Psikoloji", "Bilim ve Teknoloji",
    "Din ve İnanç", "Tarih", "Siyaset Bilimi", "Ekonomi ve Hukuk",
    "Türk Edebiyatı", "Dünya Edebiyatı", "Sanat ve Kültür", "Diğer"
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
                    className={`w-full text-left px-3 py-2 rounded-xl text-sm font-bold transition-all duration-300 border ${activeCategory === null
                        ? 'bg-card border-[#CC561E] text-card-foreground shadow-[0_0_12px_rgba(204,86,30,0.35)]'
                        : 'bg-card border-white/10 text-card-foreground hover:border-white/20 hover:bg-card/90'
                        }`}
                >
                    Tümü
                </button>
                {CATEGORIES.map((cat) => (
                    <button
                        key={cat}
                        onClick={() => onCategoryChange(cat)}
                        className={`w-full text-left px-3 py-2 rounded-xl text-sm font-bold transition-all duration-300 border ${activeCategory === cat
                            ? 'bg-card border-[#CC561E] text-card-foreground shadow-[0_0_12px_rgba(204,86,30,0.35)]'
                            : 'bg-card border-white/10 text-card-foreground hover:border-white/20 hover:bg-card/90'
                            }`}
                    >
                        {cat}
                    </button>
                ))}
            </div>
        </div>
    );
};
