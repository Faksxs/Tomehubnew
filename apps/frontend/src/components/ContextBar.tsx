import React, { useState } from 'react';
import { Compass, HelpCircle, AlertTriangle, CheckCircle, ChevronDown, ChevronUp } from 'lucide-react';

interface ContextBarProps {
    state: {
        active_topic?: string;
        assumptions?: Array<{ id: number; text: string; confidence: string }>;
        open_questions?: string[];
        established_facts?: Array<{ text: string; source: string }>;
    };
}

export const ContextBar: React.FC<ContextBarProps> = ({ state }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    if (!state.active_topic && (!state.assumptions || state.assumptions.length === 0)) {
        return null;
    }

    return (
        <div className="sticky top-0 z-10 bg-white/95 dark:bg-slate-800/95 backdrop-blur-sm border-b border-purple-100 dark:border-slate-700 shadow-sm transition-all">
            <div
                className="max-w-4xl mx-auto px-4 py-2 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/50"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 overflow-hidden">
                        <div className="p-1.5 bg-purple-100 dark:bg-purple-900/30 rounded-md flex-shrink-0">
                            <Compass className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div className="min-w-0">
                            <p className="text-xs font-semibold text-purple-600 dark:text-purple-400 uppercase tracking-wider">
                                Current Topic
                            </p>
                            <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                                {state.active_topic || "Initializing exploration..."}
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        {state.assumptions && state.assumptions.length > 0 && (
                            <div className="hidden sm:flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border border-amber-100 dark:border-amber-800/50">
                                <AlertTriangle className="w-3 h-3" />
                                {state.assumptions.length} Assumptions
                            </div>
                        )}
                        {isExpanded ? (
                            <ChevronUp className="w-4 h-4 text-slate-400" />
                        ) : (
                            <ChevronDown className="w-4 h-4 text-slate-400" />
                        )}
                    </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700 space-y-4 pb-2 animate-fade-in-down">

                        {/* Assumptions */}
                        {state.assumptions && state.assumptions.length > 0 && (
                            <div className="space-y-2">
                                <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase flex items-center gap-2">
                                    <AlertTriangle className="w-3 h-3" /> Working Assumptions
                                </h4>
                                <div className="grid gap-2">
                                    {state.assumptions.map((a, i) => (
                                        <div key={i} className="text-sm text-slate-700 dark:text-slate-300 bg-amber-50/50 dark:bg-amber-900/10 p-2 rounded border-l-2 border-amber-400">
                                            {a.text}
                                            <span className="ml-2 text-xs text-amber-600 dark:text-amber-500 font-medium opacity-75">
                                                ({a.confidence})
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Open Questions */}
                        {state.open_questions && state.open_questions.length > 0 && (
                            <div className="space-y-2">
                                <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase flex items-center gap-2">
                                    <HelpCircle className="w-3 h-3" /> Open Questions
                                </h4>
                                <ul className="space-y-1">
                                    {state.open_questions.map((q, i) => (
                                        <li key={i} className="text-sm text-slate-600 dark:text-slate-300 flex items-start gap-2">
                                            <span className="text-slate-400 mt-1.5">•</span>
                                            {q}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* Validated Facts */}
                        {state.established_facts && state.established_facts.length > 0 && (
                            <div className="space-y-2">
                                <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase flex items-center gap-2">
                                    <CheckCircle className="w-3 h-3" /> Validated Facts
                                </h4>
                                <ul className="space-y-1">
                                    {state.established_facts.map((f, i) => (
                                        <li key={i} className="text-sm text-slate-600 dark:text-slate-300 flex items-start gap-2">
                                            <CheckCircle className="w-3 h-3 text-green-500 mt-0.5 flex-shrink-0" />
                                            <span>
                                                {f.text}
                                                <span className="ml-1 text-xs text-slate-400">[{f.source}]</span>
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};
