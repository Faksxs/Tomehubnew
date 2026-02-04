import React, { useMemo } from 'react';
import { DistributionResponse } from '../services/backendApiService';

interface DistributionChartProps {
    data: DistributionResponse['distribution'];
    onBarClick?: (pageNumber: number) => void;
    currentStartPage?: number;
    currentEndPage?: number;
}

export const DistributionChart: React.FC<DistributionChartProps> = ({
    data,
    onBarClick,
    currentStartPage,
    currentEndPage
}) => {
    // 1. Process Data
    const { maxPage, maxCount, bars } = useMemo(() => {
        if (!data || data.length === 0) return { maxPage: 0, maxCount: 0, bars: [] };

        const maxP = Math.max(...data.map(d => d.page_number));
        const maxC = Math.max(...data.map(d => d.count));

        // Fill gaps? No, let's just show present bars for now on a continuous axis
        return { maxPage: maxP, maxCount: maxC, bars: data };
    }, [data]);

    if (bars.length === 0) return null;

    // 2. Dimensions
    const height = 60;
    const width = 100; // Percent
    const barWidthPercent = Math.max(0.5, 100 / (maxPage || 1)); // Adaptive width

    return (
        <div className="w-full space-y-2">
            <div className="flex justify-between text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                <span>Page 1</span>
                <span>Distribution Timeline</span>
                <span>Page {maxPage}</span>
            </div>

            <div className="relative w-full h-[60px] bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-100 dark:border-slate-800 overflow-hidden flex items-end">
                {/* Y-Axis Guidelines */}
                <div className="absolute inset-0 flex flex-col justify-between pointer-events-none p-[1px]">
                    <div className="w-full h-px border-t border-dashed border-slate-200 dark:border-slate-700/50 opacity-50"></div>
                    <div className="w-full h-px border-t border-dashed border-slate-200 dark:border-slate-700/50 opacity-50"></div>
                </div>

                {/* Bars */}
                {bars.map((bar) => {
                    const leftPos = ((bar.page_number - 1) / maxPage) * 100;
                    const barHeight = (bar.count / maxCount) * 100;
                    const isHighDensity = bar.count > (maxCount * 0.7);

                    return (
                        <div
                            key={bar.page_number}
                            onClick={() => onBarClick && onBarClick(bar.page_number)}
                            className={`absolute bottom-0 cursor-pointer transition-all hover:opacity-80 group`}
                            style={{
                                left: `${leftPos}%`,
                                height: `${barHeight}%`,
                                width: `max(2px, ${100 / maxPage}%)`, // Ensure at least 2px visible
                                minHeight: '4px' // Ensure visibility for 1 count
                            }}
                        >
                            <div className={`w-full h-full rounded-t-sm ${isHighDensity ? 'bg-indigo-500 dark:bg-indigo-400' : 'bg-indigo-300 dark:bg-indigo-600'
                                }`} />

                            {/* Tooltip */}
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-20 whitespace-nowrap">
                                <div className="bg-slate-800 text-white text-[10px] px-2 py-1 rounded shadow-lg">
                                    Page {bar.page_number}: {bar.count} hits
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
