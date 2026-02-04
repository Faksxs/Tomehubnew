import React, { useEffect } from 'react';
import { ConcordanceResponse, getConcordance, getDistribution, DistributionResponse } from '../services/backendApiService';
import { DistributionChart } from './DistributionChart';
import { X, ExternalLink, Loader2, Info } from 'lucide-react';

interface ConcordanceViewProps {
    bookId: string;
    term: string;
    initialContexts: ConcordanceResponse['contexts'];
    firebaseUid: string;
    onClose: () => void;
}

export const ConcordanceView: React.FC<ConcordanceViewProps> = ({
    bookId,
    term,
    initialContexts = [],
    firebaseUid,
    onClose
}) => {
    const [contexts, setContexts] = React.useState(initialContexts || []);
    const [isLoadingMore, setIsLoadingMore] = React.useState(false);
    const [offset, setOffset] = React.useState(contexts?.length || 0);
    const [hasMore, setHasMore] = React.useState((contexts?.length || 0) >= 10); // Simple heuristic
    const [distribution, setDistribution] = React.useState<DistributionResponse['distribution']>([]);

    useEffect(() => {
        const fetchDist = async () => {
            try {
                const res = await getDistribution(firebaseUid, bookId, term);
                setDistribution(res.distribution || []);
            } catch (e) {
                console.error("Dist fetch failed", e);
            }
        };
        fetchDist();
    }, [bookId, term, firebaseUid]);

    const loadMore = async () => {
        if (isLoadingMore) return;
        setIsLoadingMore(true);
        try {
            const resp = await getConcordance(firebaseUid, bookId, term, 50, offset);
            if (resp.contexts.length > 0) {
                setContexts(prev => [...prev, ...resp.contexts]);
                setOffset(prev => prev + resp.contexts.length);
            } else {
                setHasMore(false);
            }
        } catch (err) {
            console.error("Failed to load more contexts:", err);
        } finally {
            setIsLoadingMore(false);
        }
    };

    const highlightKeyword = (text: string, keyword: string) => {
        if (!keyword) return text;
        // Case insensitive Turkish match
        const parts = text.split(new RegExp(`(${keyword})`, 'gi'));
        return (
            <>
                {parts.map((part, i) =>
                    part.toLowerCase() === keyword.toLowerCase()
                        ? <mark key={i} className="bg-yellow-200 text-slate-900 font-semibold rounded-sm px-0.5">{part}</mark>
                        : part
                )}
            </>
        );
    };

    return (
        <div className="flex flex-col h-full bg-white dark:bg-slate-950 border-l border-slate-200 dark:border-slate-800 shadow-xl animate-in slide-in-from-right duration-300">
            {/* Header */}
            <div className="p-4 border-b border-slate-100 dark:border-slate-900 flex justify-between items-center bg-slate-50/50 dark:bg-slate-900/50">
                <div>
                    <h3 className="text-lg font-bold text-slate-800 dark:text-white flex items-center gap-2">
                        "{term}" Bağlamları
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Total occurrences found</p>
                </div>
                <button
                    onClick={onClose}
                    className="p-2 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-full transition-colors text-slate-500"
                >
                    <X size={20} />
                </button>
            </div>

            {/* Info Alert */}
            <div className="p-3 bg-indigo-50 dark:bg-indigo-900/20 m-4 rounded-lg border border-indigo-100 dark:border-indigo-800 flex gap-3 text-xs text-indigo-700 dark:text-indigo-300">
                <Info size={16} className="shrink-0 mt-0.5" />
                <p>
                    Bu liste, kelimenin kitaptaki farklı formlarını (çekim ekleri, kök formları)
                    ve geçtiği orijinal pasajları gösterir.
                </p>
            </div>

            {/* Distribution Chart */}
            <div className="px-4 pb-2">
                <DistributionChart data={distribution} />
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
                {contexts.map((ctx, idx) => (
                    <div key={idx} className="group relative">
                        <div className="flex justify-between items-start mb-1 text-[10px] items-center">
                            <span className="font-semibold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded uppercase tracking-wider">
                                Sayfa {ctx.page_number}
                            </span>
                            <button className="text-slate-300 group-hover:text-slate-500 dark:text-slate-700 dark:group-hover:text-slate-400 flex items-center gap-1 transition-colors">
                                <span className="text-[9px]">GÖRÜNTÜLE</span>
                                <ExternalLink size={10} />
                            </button>
                        </div>

                        <div className="text-sm md:text-base text-slate-700 dark:text-slate-300 leading-relaxed font-lora border-l-2 border-slate-100 dark:border-slate-800 pl-4 py-1 italic hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors">
                            {highlightKeyword(ctx.snippet, ctx.keyword_found)}
                        </div>
                    </div>
                ))}

                {hasMore && (
                    <button
                        onClick={loadMore}
                        disabled={isLoadingMore}
                        className="w-full py-4 text-sm font-medium text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400 border-2 border-dashed border-slate-100 dark:border-slate-800 rounded-xl hover:border-indigo-200 dark:hover:border-indigo-800 hover:bg-slate-50 dark:hover:bg-slate-900 transition-all flex items-center justify-center gap-2"
                    >
                        {isLoadingMore ? (
                            <>
                                <Loader2 size={16} className="animate-spin" />
                                Yükleniyor...
                            </>
                        ) : (
                            'Daha Fazla Bağlam Yükle'
                        )}
                    </button>
                )}
            </div>
        </div>
    );
};
