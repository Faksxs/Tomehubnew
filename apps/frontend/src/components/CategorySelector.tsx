import React from 'react';

export const MIN_CATEGORY_BOOKS_VISIBLE = 4;

export const CATEGORIES = [
    'Felsefe', 'Sosyoloji', 'Psikoloji', 'Bilim ve Teknoloji',
    'Din ve İnanç', 'Tarih', 'İnceleme ve Araştırma', 'Ekonomi ve Hukuk',
    'Türk Edebiyatı', 'Dünya Edebiyatı', 'Sanat ve Kültür', 'Diğer'
];

interface CategorySelectorProps {
    activeCategory: string | null;
    onCategoryChange: (category: string | null) => void;
    categories?: string[];
}

export const CategorySelector: React.FC<CategorySelectorProps> = ({
    activeCategory,
    onCategoryChange,
    categories = CATEGORIES,
}) => {
    return (
        <div className="w-full flex flex-col gap-2 p-3 bg-card border border-white/10 rounded-2xl">
            <h3 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-1 px-1 flex items-center gap-2">
                <span className="w-1 h-1 bg-[#CC561E] rounded-full"></span>
                Discovery Areas
            </h3>
            <div className="space-y-1">
                <button
                    onClick={() => onCategoryChange(null)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all duration-300 border bg-card text-card-foreground ${activeCategory === null
                        ? 'border-[#CC561E] shadow-[0_0_12px_rgba(204,86,30,0.35)]'
                        : 'border-white/10 hover:border-white/20 hover:bg-card/90'
                        }`}
                >
                    <span className={activeCategory === null ? 'text-card-foreground' : 'text-card-foreground/80'}>All Categories</span>
                    {activeCategory === null && <div className="w-1.5 h-1.5 bg-[#CC561E] rounded-full animate-pulse mr-1" />}
                </button>
                {categories.map((cat) => (
                    <button
                        key={cat}
                        onClick={() => onCategoryChange(cat)}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all duration-300 border bg-card text-card-foreground ${activeCategory === cat
                            ? 'border-[#CC561E] shadow-[0_0_12px_rgba(204,86,30,0.35)]'
                            : 'border-white/10 hover:border-white/20 hover:bg-card/90'
                            }`}
                    >
                        <span className={activeCategory === cat ? 'text-card-foreground' : 'text-card-foreground/80'}>{cat}</span>
                        {activeCategory === cat && <div className="w-1.5 h-1.5 bg-[#CC561E] rounded-full animate-pulse mr-1" />}
                    </button>
                ))}
            </div>
        </div>
    );
};
