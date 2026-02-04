import React from 'react';
import { InsightCard as InsightCardType } from '../services/flowService';
import { Sparkles, Bookmark, Layers, AlertCircle } from 'lucide-react';

interface InsightCardProps {
    card: InsightCardType;
    onAction?: (card: InsightCardType) => void;
}

const TYPE_META: Record<InsightCardType['type'], { label: string; icon: React.ElementType; tone: string }> = {
    CONCEPT_OVERLAP: { label: 'Prestij', icon: Sparkles, tone: 'border-[#CC561E] bg-[#CC561E]/10 text-[#CC561E]' },
    FORGOTTEN: { label: 'Hatirlatma', icon: Bookmark, tone: 'border-amber-400 bg-amber-50 text-amber-700' },
    CATEGORY_STATS: { label: 'Istatistik', icon: Layers, tone: 'border-slate-200 bg-white text-slate-700' },
    UNLABELED_CLUSTER: { label: 'Kume', icon: AlertCircle, tone: 'border-indigo-200 bg-indigo-50 text-indigo-700' },
};

export const InsightCard: React.FC<InsightCardProps> = ({ card, onAction }) => {
    const meta = TYPE_META[card.type] || TYPE_META.CATEGORY_STATS;
    const Icon = meta.icon;

    return (
        <div className="rounded-2xl border border-slate-100 bg-white/70 dark:bg-slate-900/60 p-6 shadow-sm hover:shadow-md transition-all">
            <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${meta.tone}`}>
                <Icon size={14} />
                <span>{meta.label}</span>
            </div>
            <h3 className="mt-4 text-lg font-extrabold text-slate-900 dark:text-white leading-snug">{card.title}</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{card.body}</p>
            {card.cta?.label && (
                <button
                    type="button"
                    className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#CC561E] px-4 py-2 text-xs font-bold uppercase tracking-wider text-white shadow-sm hover:bg-[#b34b1a] transition-colors"
                    onClick={() => onAction?.(card)}
                >
                    {card.cta.label}
                </button>
            )}
        </div>
    );
};

export default InsightCard;
