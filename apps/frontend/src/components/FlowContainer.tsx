/**
 * FlowContainer Component
 * Renders a single card in the Flux stream
 experience
 * Handles infinite scroll, session management, and card rendering
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ChevronLeft, SlidersHorizontal, Settings2, X, ChevronDown } from 'lucide-react';
import { FlowCard } from './FlowCard';
import { HorizonSlider } from './HorizonSlider';
import { CategorySelector } from './CategorySelector';
import {
    FlowCard as FlowCardType,
    startFlowSession,
    getNextFlowBatch,
    adjustFlowHorizon,
    resetFlowAnchor,
    PivotInfo,
} from '../services/flowService';
import SourceNavigator, { SourceFilter } from './SourceNavigator';

interface FlowContainerProps {
    firebaseUid: string;
    anchorType: 'note' | 'book' | 'author' | 'topic';
    anchorId: string;
    anchorLabel?: string;
    onClose?: () => void;
}

export const FlowContainer: React.FC<FlowContainerProps> = ({
    firebaseUid,
    anchorType,
    anchorId,
    anchorLabel,
    onClose,
}) => {
    // State
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [cards, setCards] = useState<FlowCardType[]>([]);
    const [topicLabel, setTopicLabel] = useState(anchorLabel || 'Flux');
    const [activeCategory, setActiveCategory] = useState<string | null>(null);
    const [horizon, setHorizon] = useState(0.25); // Start at Author zone
    const [isLoading, setIsLoading] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [flowStarted, setFlowStarted] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [isCategoryDrawerOpen, setIsCategoryDrawerOpen] = useState(false);
    const [pivotInfo, setPivotInfo] = useState<PivotInfo | null>(null);
    const [isJumping, setIsJumping] = useState(false);
    const [activeFilter, setActiveFilter] = useState<SourceFilter>('ALL');

    // Refs
    const containerRef = useRef<HTMLDivElement>(null);
    const observerRef = useRef<IntersectionObserver | null>(null);
    const loadMoreRef = useRef<HTMLDivElement>(null);

    const resolveResourceType = useCallback((filter: SourceFilter): string | undefined => {
        if (filter === 'ALL') return 'ALL_NOTES';
        return filter;
    }, []);

    // Function to initialize or re-initialize the flow session
    const initializeFlow = useCallback(async (
        filter: SourceFilter,
        category: string | null = null,
        horizonValue: number = 0.25
    ) => {
        if (!firebaseUid) return;
        setIsLoading(true);
        setError(null);
        setCards([]); // Clear cards when initializing new filter/anchor
        setHasMore(true); // Reset hasMore for new session

        try {
            const resourceType = resolveResourceType(filter);
            const response = await startFlowSession({
                firebase_uid: firebaseUid,
                anchor_type: anchorType,
                anchor_id: anchorId,
                mode: 'FOCUS',
                horizon_value: horizonValue,
                resource_type: resourceType,
                category: category || undefined
            });

            setSessionId(response.session_id);
            setCards(response.initial_cards);
            setTopicLabel(response.topic_label);
            setPivotInfo(null); // Clear pivot info on new session start
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start session');
        } finally {
            setIsLoading(false);
        }
    }, [firebaseUid, anchorType, anchorId, resolveResourceType]);

    // Auto-start session when user is ready
    useEffect(() => {
        if (!firebaseUid) return;
        if (!flowStarted) {
            setFlowStarted(true);
        }
    }, [firebaseUid, flowStarted]);

    // Start session after auto-start or user interaction
    useEffect(() => {
        if (!flowStarted) return;
        initializeFlow(activeFilter, activeCategory, horizon);
    }, [flowStarted, activeFilter, activeCategory, initializeFlow]);

    // Load more cards
    const loadMore = useCallback(async () => {
        if (sessionId === null || isLoading || !hasMore) return;

        setIsLoading(true);

        try {
            const response = await getNextFlowBatch({
                firebase_uid: firebaseUid,
                session_id: sessionId,
                batch_size: 5,
            });

            setCards((prev) => [...prev, ...response.cards]);
            setHasMore(response.has_more);

            // If the response triggered a pivot, update label and info
            if (response.pivot_info) {
                setPivotInfo(response.pivot_info);
            }
        } catch (err) {
            console.error('Failed to load more:', err);
        } finally {
            setIsLoading(false);
        }
    }, [sessionId, firebaseUid, isLoading, hasMore]);

    // Infinite scroll observer
    // Manual Load More Implementation - Observer removed

    // Handle horizon change
    const handleHorizonChange = async (newValue: number) => {
        setHorizon(newValue);

        if (!flowStarted) {
            setFlowStarted(true);
            return;
        }

        if (sessionId !== null) {
            try {
                await adjustFlowHorizon(sessionId, newValue, firebaseUid);
            } catch (err) {
                console.error('Failed to adjust horizon:', err);
            }
        }
    };

    const handleResetAnchor = async () => {
        if (!flowStarted) {
            setFlowStarted(true);
            return;
        }
        if (sessionId === null) return;

        setIsLoading(true);
        setIsJumping(true);
        setError(null);
        setPivotInfo(null);

        try {
            // Trigger RANDOMIZED TOPIC RESET instead of hierarchical discovery
            const result = await resetFlowAnchor(
                sessionId,
                'topic',
                'General Discovery',
                firebaseUid,
                resolveResourceType(activeFilter),
                activeCategory || undefined
            );

            setTopicLabel(result.topic_label);
            if (result.pivot_info) {
                setPivotInfo(result.pivot_info);
            }
            setCards([]);
            setHasMore(true);

            // Fetch the first batch of the new anchor immediately
            const nextBatch = await getNextFlowBatch({
                session_id: sessionId,
                firebase_uid: firebaseUid,
                batch_size: 5
            });

            setCards(nextBatch.cards);
            setHasMore(nextBatch.has_more);
            if (nextBatch.pivot_info) {
                setPivotInfo(nextBatch.pivot_info);
            }
        } catch (err: any) {
            setError(err.message);
        } finally {
            setIsLoading(false);
            setIsJumping(false);
        }
    };

    const handleCategoryChange = (category: string | null) => {
        if (category === activeCategory) return;

        setActiveCategory(category);

        if (!flowStarted) {
            setFlowStarted(true);
            return;
        }

        if (sessionId !== null) {
            setIsLoading(true);
            resetFlowAnchor(
                sessionId,
                'topic',
                'General Discovery',
                firebaseUid || '',
                resolveResourceType(activeFilter),
                category || undefined
            ).then((resp) => {
                setCards([]);
                setTopicLabel(resp.topic_label);
                setPivotInfo(resp.pivot_info || null);
                setHasMore(true);
                // Kick off loading for the new anchor
                getNextFlowBatch({
                    session_id: sessionId,
                    firebase_uid: firebaseUid,
                    batch_size: 5
                }).then(nextBatch => {
                    setCards(nextBatch.cards);
                    setHasMore(nextBatch.has_more);
                    if (nextBatch.pivot_info) {
                        setPivotInfo(nextBatch.pivot_info);
                    }
                }).catch(err => {
                    console.error("Failed to load initial batch after category pivot:", err);
                    setError(err instanceof Error ? err.message : 'Failed to load cards after category change');
                }).finally(() => {
                    setIsLoading(false);
                });
            }).catch(err => {
                console.error("Failed to pivot category:", err);
                setError(err instanceof Error ? err.message : 'Failed to change category');
                setIsLoading(false);
            });
        }
    };

    const handleFilterChange = (filter: SourceFilter) => {
        if (filter === activeFilter) return;
        setActiveFilter(filter);
        if (!flowStarted) {
            setFlowStarted(true);
        }
    };

    return (
        <div className="flow-container" ref={containerRef}>
            <div className="flow-layout">
                {/* Left Category Column */}
                <aside className="flow-left">
                    {onClose && (
                        <button
                            onClick={onClose}
                            className="flow-left__back group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                        >
                            <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                                <ChevronLeft size={16} />
                            </div>
                            <span className="text-xs font-bold uppercase tracking-wider">Back to Home</span>
                        </button>
                    )}
                    {(activeFilter === 'ALL' || activeFilter === 'BOOK') && (
                        <CategorySelector
                            activeCategory={activeCategory}
                            onCategoryChange={handleCategoryChange}
                        />
                    )}
                </aside>

                {/* Main Content */}
                <div className="flow-main">
                    {/* Header */}
                    <div className="flow-container__header">
                        <div className="flow-container__title-section">
                            <div className="flow-container__mobile-actions relative flex items-center justify-between">
                                {/* Left Group: Back + Kesif Alanlari */}
                                <div className="lg:hidden flex items-center gap-2 z-10 w-1/3">
                                    {onClose && (
                                        <button
                                            onClick={onClose}
                                            className="flow-mobile-action-btn group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                                            aria-label="Back"
                                        >
                                            <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                                                <ChevronLeft size={16} />
                                            </div>
                                        </button>
                                    )}
                                    <button
                                        onClick={() => setIsCategoryDrawerOpen(true)}
                                        className="flow-mobile-action-btn group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                                    >
                                        <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                                            <Settings2 size={16} />
                                        </div>
                                        <span className="text-[10px] font-bold uppercase tracking-wider hidden sm:inline">Keşif</span>
                                    </button>
                                </div>

                                {/* Center Group: Flux Title (Absolute) */}
                                <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-0 pointer-events-none select-none">
                                    <span className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[#CC561E] bg-[#CC561E]/10 px-3 py-1 rounded-md">
                                        FLUX
                                    </span>
                                </div>

                                {/* Right Group: Filters & Horizon */}
                                <div className="lg:hidden flex items-center justify-end gap-2 z-10 w-1/3">
                                    <button
                                        onClick={() => setIsSidebarOpen(true)}
                                        className="flow-mobile-action-btn group flex items-center gap-2 text-slate-500 hover:text-[#CC561E] transition-all duration-300"
                                    >
                                        <span className="text-[10px] font-bold uppercase tracking-wider hidden sm:inline">Filters</span>
                                        <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 group-hover:bg-[rgba(204,86,30,0.1)] transition-colors">
                                            <SlidersHorizontal size={16} />
                                        </div>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Error State */}
                    {flowStarted && error && (
                        <div className="flow-container__error">
                            <p>⚠️ {error}</p>
                            <button onClick={() => window.location.reload()}>Retry</button>
                        </div>
                    )}

                    {/* Topic Pivot Info (The "Why") */}
                    {flowStarted && pivotInfo && (
                        <div className="flow-container__pivot">
                            <span className="pivot-icon">🚀</span>
                            <p>{pivotInfo.message}</p>
                        </div>
                    )}

                    {/* Cards */}
                    <div className="flow-container__cards">
                        {!flowStarted ? (
                            <div className="flex flex-col items-center justify-center py-20 text-center px-4">
                                <h3 className="text-xl font-bold text-slate-800 dark:text-white mb-3">
                                    Flux başlatılmadı
                                </h3>
                                <p className="text-slate-500 max-w-md mx-auto mb-6">
                                    Başlamak için bir filtre seçebilir veya aşağıdaki butona tıklayabilirsin.
                                </p>
                                <button
                                    onClick={() => setFlowStarted(true)}
                                    className="px-6 py-2.5 bg-[#CC561E] hover:bg-[#b04a1a] text-white font-medium rounded-lg transition-colors"
                                >
                                    Flux Başlat
                                </button>
                            </div>
                        ) : (
                            <>
                                {cards.map((card) => (
                                    <FlowCard
                                        key={card.flow_id}
                                        card={card}
                                        sessionId={sessionId ?? ''}
                                        firebaseUid={firebaseUid}
                                    />
                                ))}

                                {/* Empty State - Explicitly show when no cards found */}
                                {!isLoading && !error && cards.length === 0 && (
                                    <div className="flex flex-col items-center justify-center py-20 text-center px-4">
                                        <div className="text-6xl mb-6 opacity-80">📚</div>
                                        <h3 className="text-xl font-bold text-slate-800 dark:text-white mb-2">
                                            {activeFilter === 'PERSONAL_NOTE' ? 'No Personal Notes Found' : 'Library Empty'}
                                        </h3>
                                        <p className="text-slate-500 max-w-md mx-auto mb-8">
                                            {activeFilter === 'PERSONAL_NOTE'
                                                ? "We couldn't find any personal notes or highlights. Try adding some content or switching to 'All Notes'."
                                                : "Your knowledge stream is waiting for content. Upload books or add notes to get started."}
                                        </p>
                                        <button
                                            onClick={onClose}
                                            className="px-6 py-2.5 bg-[#CC561E] hover:bg-[#b04a1a] text-white font-medium rounded-lg transition-colors"
                                        >
                                            Go to Dashboard
                                        </button>
                                    </div>
                                )}
                            </>
                        )}

                        {/* Manual Load More Trigger */}
                        {flowStarted && (cards.length > 0 || isLoading) && (
                            <div className="flow-container__load-more py-8 flex justify-center">
                                {isLoading ? (
                                    <div className="flex items-center gap-3 text-slate-500">
                                        <div className="w-5 h-5 border-2 border-[#CC561E] border-t-transparent rounded-full animate-spin" />
                                        <span className="text-sm font-medium">{isJumping ? 'Topic is shifting...' : 'Loading more thoughts...'}</span>
                                    </div>
                                ) : (
                                    hasMore && (
                                        <button
                                            onClick={loadMore}
                                            className="px-8 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-[#CC561E]/50 text-slate-700 dark:text-slate-300 hover:text-[#CC561E] dark:hover:text-[#CC561E] font-medium rounded-full shadow-sm hover:shadow-md transition-all duration-300 flex items-center gap-2 group"
                                        >
                                            <span>Daha Fazla Göster</span>
                                            <ChevronDown className="w-4 h-4 group-hover:translate-y-0.5 transition-transform" />
                                        </button>
                                    )
                                )}
                                {!hasMore && cards.length > 0 && (
                                    <div className="text-center text-slate-400 text-sm py-4">
                                        <span>🎉 You've explored all related thoughts</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Sidebar Drawer Container */}
                <div className={`flow-category-container ${isCategoryDrawerOpen ? 'is-open' : ''}`}>
                    <div
                        className="flow-sidebar-backdrop"
                        onClick={() => setIsCategoryDrawerOpen(false)}
                    />
                    <aside className="flow-category-sidebar">
                        <div className="flow-sidebar__sticky">
                            <div className="lg:hidden flex items-center justify-between mb-6 pb-4 border-bottom border-slate-100 dark:border-slate-800">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-xl bg-[rgba(204,86,30,0.1)] text-[#CC561E]">
                                        <Settings2 size={20} />
                                    </div>
                                    <span className="font-bold text-slate-800 dark:text-white">Keşif Alanları</span>
                                </div>
                                <button
                                    onClick={() => setIsCategoryDrawerOpen(false)}
                                    className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            {(activeFilter === 'ALL' || activeFilter === 'BOOK') && (
                                <CategorySelector
                                    activeCategory={activeCategory}
                                    onCategoryChange={(cat) => {
                                        handleCategoryChange(cat);
                                        setIsCategoryDrawerOpen(false);
                                    }}
                                />
                            )}
                        </div>
                    </aside>
                </div>

                <div className={`flow-sidebar-container ${isSidebarOpen ? 'is-open' : ''}`}>
                    {/* Backdrop for mobile */}
                    <div
                        className="flow-sidebar-backdrop"
                        onClick={() => setIsSidebarOpen(false)}
                    />

                    <aside className="flow-sidebar">
                        <div className="flow-sidebar__sticky">
                            {/* Mobile Drawer Header */}
                            <div className="lg:hidden flex items-center justify-between mb-6 pb-4 border-bottom border-slate-100 dark:border-slate-800">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-xl bg-[rgba(204,86,30,0.1)] text-[#CC561E]">
                                        <Settings2 size={20} />
                                    </div>
                                    <span className="font-bold text-slate-800 dark:text-white">Controls</span>
                                </div>
                                <button
                                    onClick={() => setIsSidebarOpen(false)}
                                    className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <SourceNavigator
                                activeFilter={activeFilter}
                                onFilterChange={handleFilterChange}
                            />

                            {/* Horizon Slider */}
                            <div className="mb-0">
                                <HorizonSlider
                                    value={horizon}
                                    onChange={handleHorizonChange}
                                    disabled={isLoading}
                                />
                            </div>

                            {/* Cards List */}
                            <button
                                className="flow-sidebar__pivot-button"
                                onClick={handleResetAnchor}
                                disabled={isLoading}
                            >
                                <span className="icon">🔄</span>
                                Change Topic
                            </button>

                            <div className="flow-sidebar__stats">
                                <div className="stat-item">
                                    <span className="stat-label">Session ID</span>
                                    <span className="stat-value">{sessionId !== null ? sessionId.toString() : '—'}</span>
                                </div>
                            </div>
                        </div>
                    </aside>
                </div>
            </div>

            <style>{`
                .flow-container {
                    max-width: 1100px;
                    margin: 0 auto;
                    width: 100%;
                    display: flex;
                    flex-direction: column;
                    height: 100%;
                    background: transparent;
                    position: relative;
                    padding: 24px;
                }

                .flow-container::before {
                    content: '';
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: 
                        radial-gradient(circle at 10% 20%, rgba(204, 86, 30, 0.03) 0%, transparent 40%),
                        radial-gradient(circle at 90% 80%, rgba(204, 86, 30, 0.03) 0%, transparent 40%);
                    pointer-events: none;
                    z-index: -1;
                }

                .flow-layout {
                    display: grid;
                    grid-template-columns: 180px 1fr 250px;
                    gap: 32px;
                    align-items: flex-start;
                    padding-top: 20px;
                    max-width: 1100px;
                    margin: 0 auto;
                }

                @media (max-width: 1024px) {
                    .flow-layout {
                        grid-template-columns: 1fr;
                        gap: 28px;
                    }

                    .flow-left {
                        display: none;
                    }

                    .flow-sidebar-container {
                        position: fixed;
                        top: 0;
                        right: 0;
                        bottom: 0;
                        left: 0;
                        z-index: 1000;
                        pointer-events: none;
                        display: flex;
                        justify-content: flex-end;
                    }

                    .flow-category-container {
                        position: fixed;
                        top: 0;
                        right: 0;
                        bottom: 0;
                        left: 0;
                        z-index: 1000;
                        pointer-events: none;
                        display: flex;
                        justify-content: flex-start;
                    }

                    .flow-sidebar-container.is-open {
                        pointer-events: auto;
                    }

                    .flow-category-container.is-open {
                        pointer-events: auto;
                    }

                    .flow-sidebar-backdrop {
                        position: absolute;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: rgba(0, 0, 0, 0.5);
                        backdrop-filter: blur(4px);
                        opacity: 0;
                        transition: opacity 0.4s ease;
                        pointer-events: none;
                    }

                    .is-open .flow-sidebar-backdrop {
                        opacity: 1;
                        pointer-events: auto;
                    }

                    .flow-sidebar {
                        width: 100%;
                        max-width: 340px;
                        height: 100%;
                        background: #fff;
                        transform: translateX(100%);
                        transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                        box-shadow: -10px 0 30px rgba(0, 0, 0, 0.1);
                        z-index: 1001;
                    }

                    .dark .flow-sidebar {
                        background: #0f172a;
                    }

                    .flow-category-sidebar {
                        width: 100%;
                        max-width: 340px;
                        height: 100%;
                        background: #fff;
                        transform: translateX(-100%);
                        transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                        box-shadow: 10px 0 30px rgba(0, 0, 0, 0.1);
                        z-index: 1001;
                    }

                    .dark .flow-category-sidebar {
                        background: #0f172a;
                    }

                    .is-open .flow-sidebar {
                        transform: translateX(0);
                    }

                    .is-open .flow-category-sidebar {
                        transform: translateX(0);
                    }

                    .flow-sidebar__sticky {
                        height: 100%;
                        max-height: 100vh;
                        padding: 24px;
                        overflow-y: auto;
                        position: relative;
                        top: 0 !important;
                    }

                    .flow-container__mobile-actions {
                        position: sticky;
                        top: 0;
                        z-index: 100;
                        background: rgba(255, 255, 255, 0.85);
                        backdrop-filter: blur(16px);
                        margin: -20px -20px 20px -20px;
                        padding: 12px 20px;
                        border-bottom: 1px solid rgba(0, 0, 0, 0.06);
                        width: calc(100% + 40px);
                    }

                    .flow-mobile-actions-row {
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 8px;
                        width: 100%;
                    }

                    .flow-mobile-actions-right {
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        margin-left: auto;
                    }

                    .flow-mobile-action-btn {
                        padding: 6px 10px;
                        border-radius: 10px;
                        border: 1px solid rgba(148, 163, 184, 0.22);
                        background: rgba(255, 255, 255, 0.9);
                    }

                    .dark .flow-mobile-action-btn {
                        background: rgba(15, 23, 42, 0.9);
                        border-color: rgba(255, 255, 255, 0.12);
                    }

                    .flow-badge--title {
                        display: table;
                        margin: 4px auto 0 auto;
                        text-align: center;
                        font-size: 11px;
                        padding: 6px 14px;
                        letter-spacing: 0.14em;
                    }

                    .dark .flow-container__mobile-actions {
                        background: rgba(15, 23, 42, 0.85);
                        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                    }
                }

                @media (min-width: 1025px) {
                    .flow-container__mobile-actions {
                        display: none;
                    }

                    .flow-category-container {
                        display: none;
                    }
                }

                .flow-sidebar__sticky {
                    position: sticky;
                    top: 24px;
                    display: flex;
                    flex-direction: column;
                    gap: 14px;
                }

                .flow-left {
                    position: sticky;
                    top: 24px;
                    align-self: flex-start;
                }

                .flow-left__back {
                    margin-bottom: 16px;
                }

                .flow-card__content:not(.expanded)::after {
                    content: '';
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    width: 100%;
                    height: 60px;
                    background: linear-gradient(to bottom, transparent, rgba(248, 250, 252, 0.9));
                    pointer-events: none;
                }

                .dark .flow-card__content:not(.expanded)::after {
                    background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.9));
                }

                .flow-sidebar__pivot-button {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 12px;
                    width: 100%;
                    padding: 14px;
                    background: #262D40;
                    border: none;
                    border-radius: 12px;
                    color: white;
                    font-weight: 700;
                    font-size: 14px;
                    cursor: pointer;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    box-shadow: 0 4px 15px rgba(38, 45, 64, 0.25);
                }

                .flow-sidebar__pivot-button:hover:not(:disabled) {
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(38, 45, 64, 0.35);
                    filter: brightness(1.08);
                }

                .flow-sidebar__pivot-button:disabled {
                    opacity: 0.4;
                    cursor: not-allowed;
                    filter: grayscale(0.5);
                }

                .flow-sidebar__stats {
                    padding: 20px;
                    background: hsl(var(--card));
                    border-radius: 16px;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                }

                .stat-item {
                    display: flex;
                    justify-content: space-between;
                    font-size: 11px;
                    margin-bottom: 8px;
                }

                .stat-label { color: rgba(255, 255, 255, 0.65); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
                .stat-value { color: rgba(255, 255, 255, 0.95); font-family: 'JetBrains Mono', monospace; }

                .flow-container__header {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-end;
                    margin-bottom: 40px;
                    padding-bottom: 24px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                }

                .flow-badge {
                    display: inline-block;
                    padding: 4px 10px;
                    background: rgba(204, 86, 30, 0.1);
                    color: #CC561E;
                    font-size: 10px;
                    font-weight: 800;
                    text-transform: uppercase;
                    letter-spacing: 0.1em;
                    border-radius: 6px;
                    margin-bottom: 12px;
                }

                .flow-container__title {
                    margin: 0 0 8px 0;
                    font-size: 28px;
                    font-weight: 800;
                    color: #0f172a;
                    letter-spacing: -0.02em;
                    font-family: 'Outfit', sans-serif;
                }

                .dark .flow-container__title {
                    color: #fff;
                }

                .flow-container__meta {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }

                .meta-dot {
                    width: 4px;
                    height: 4px;
                    background: #CC561E;
                    border-radius: 50%;
                }

                .flow-container__subtitle {
                    font-size: 14px;
                    color: #64748b;
                    font-weight: 500;
                }

                .flow-container__close {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    width: 40px;
                    height: 40px;
                    font-size: 14px;
                    color: #64748b;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .flow-container__close:hover {
                    background: rgba(239, 68, 68, 0.1);
                    color: #f87171;
                    border-color: rgba(239, 68, 68, 0.2);
                }

                .flow-container__pivot {
                    background: rgba(204, 86, 30, 0.05);
                    backdrop-filter: blur(12px);
                    border: 1px solid rgba(204, 86, 30, 0.1);
                    padding: 20px 24px;
                    border-radius: 16px;
                    margin-bottom: 32px;
                    display: flex;
                    align-items: center;
                    gap: 16px;
                    animation: slideInDown 0.6s cubic-bezier(0.16, 1, 0.3, 1);
                }

                @keyframes slideInDown {
                    from { opacity: 0; transform: translateY(-20px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                .pivot-icon {
                    font-size: 24px;
                }

                .flow-container__pivot p {
                    margin: 0;
                    color: rgba(204, 86, 30, 0.8);
                    font-size: 14px;
                    line-height: 1.6;
                    font-weight: 500;
                }

                .flow-container__cards {
                    display: flex;
                    flex-direction: column;
                    gap: 24px;
                }

                .flow-container__loader {
                    padding: 60px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 16px;
                    color: #64748b;
                    font-size: 14px;
                    font-weight: 500;
                }

                .spinner {
                    width: 24px;
                    height: 24px;
                    border: 2px solid rgba(204, 86, 30, 0.1);
                    border-top-color: #CC561E;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }

                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
};

export default FlowContainer;

