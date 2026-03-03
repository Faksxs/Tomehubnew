/**
 * FlowCard Component
 * Renders a single card in the Knowledge Stream
 */

import React, { useState, useRef, useCallback } from 'react';
import { FlowCard as FlowCardType, FeedbackAction, sendFlowFeedback } from '../services/flowService';
import { translateChunk, TranslationResponse } from '../services/backendApiService';

interface FlowCardProps {
    card: FlowCardType;
    sessionId: string;
    firebaseUid: string;
    onFeedback?: (action: FeedbackAction) => void;
}

// Zone colors and labels
const ZONE_CONFIG: Record<number, { color: string; label: string; icon: string }> = {
    1: { color: '#CC561E', label: 'Tight Context', icon: '📖' },
    2: { color: '#e66a2e', label: "Author's Mind", icon: '✍️' },
    3: { color: '#b34b1a', label: 'Syntopic Debate', icon: '🔗' },
    4: { color: '#CC561E', label: 'Keşif Köprüsü', icon: '🌉' },
};

type TranslateStatus = 'idle' | 'loading' | 'ready' | 'error';
type ActiveLang = 'en' | 'nl';

export const FlowCard: React.FC<FlowCardProps> = ({
    card,
    sessionId,
    firebaseUid,
    onFeedback
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [feedbackGiven, setFeedbackGiven] = useState<FeedbackAction | null>(null);
    const [translateStatus, setTranslateStatus] = useState<TranslateStatus>('idle');
    const [showTranslation, setShowTranslation] = useState(false);
    const [translation, setTranslation] = useState<TranslationResponse | null>(null);
    const [activeLang, setActiveLang] = useState<ActiveLang>('en');
    const [translateError, setTranslateError] = useState<string | null>(null);
    const translateTriggeredRef = useRef(false);
    const zone = ZONE_CONFIG[card.zone] || ZONE_CONFIG[1];

    const handleFeedback = async (action: FeedbackAction) => {
        try {
            await sendFlowFeedback({
                firebase_uid: firebaseUid,
                session_id: sessionId,
                chunk_id: card.chunk_id,
                action,
            });
            setFeedbackGiven(action);
            onFeedback?.(action);
        } catch (error) {
            console.error('Feedback failed:', error);
        }
    };

    const triggerTranslation = useCallback(async () => {
        if (translateTriggeredRef.current || translateStatus === 'ready') return;
        translateTriggeredRef.current = true;
        setTranslateStatus('loading');
        setTranslateError(null);

        try {
            const chunkIdNum = parseInt(card.chunk_id, 10);
            if (isNaN(chunkIdNum)) {
                throw new Error('Invalid chunk_id');
            }
            const result = await translateChunk(
                chunkIdNum,
                card.content,
                card.title,
                card.author ?? '',
            );
            setTranslation(result);
            setTranslateStatus('ready');
        } catch (err) {
            console.error('Translation failed:', err);
            setTranslateError(err instanceof Error ? err.message : 'Translation failed');
            setTranslateStatus('error');
            translateTriggeredRef.current = false;
        }
    }, [card.chunk_id, card.content, card.title, card.author, translateStatus]);

    const handleExpandToggle = () => {
        const newExpanded = !isExpanded;
        setIsExpanded(newExpanded);
        // Trigger translation in background when user expands the card
        if (newExpanded && translateStatus === 'idle') {
            triggerTranslation();
        }
    };

    const handleTranslateToggle = () => {
        if (translateStatus === 'idle') {
            triggerTranslation();
        }
        if (translateStatus === 'ready' || translateStatus === 'loading') {
            setShowTranslation(!showTranslation);
        }
        if (translateStatus === 'error') {
            // Retry on error
            translateTriggeredRef.current = false;
            triggerTranslation();
            setShowTranslation(true);
        }
    };

    return (
        <div className="flow-card" style={{
            '--zone-color': zone.color,
        } as React.CSSProperties}>
            {/* Top Bar for Metadata and Zone */}
            <div className="flow-card__top-bar">
                <div className="flow-card__zone-indicator">
                    <span className="zone-dot" style={{ backgroundColor: zone.color }}></span>
                    <span className="zone-label">{zone.label}</span>
                </div>
                {(card.page_number !== undefined && card.page_number !== null && card.page_number > 0) && (
                    <div className="flow-card__meta-item">
                        <span className="text-slate-500 mr-1.5 opacity-50">#</span>
                        <span>Page {card.page_number}</span>
                    </div>
                )}
            </div>

            {/* Title Section */}
            <div className="flow-card__header">
                <h3 className="flow-card__title">{card.title}</h3>
                {card.author && (
                    <div className="flow-card__author-pill">
                        <span className="opacity-60 italic">by</span> {card.author}
                    </div>
                )}
            </div>

            {/* Content with elegant typography */}
            <div className={`flow-card__content ${isExpanded ? 'expanded' : ''}`}>
                <p>{card.content}</p>
            </div>

            {/* Translation Panel */}
            {showTranslation && (
                <div className="flow-card__translation">
                    {translateStatus === 'loading' && (
                        <div className="translation-loading">
                            <div className="translation-spinner" />
                            <span>Translating...</span>
                        </div>
                    )}
                    {translateStatus === 'error' && (
                        <div className="translation-error">
                            <span>⚠️ {translateError || 'Translation failed'}</span>
                            <button onClick={() => { translateTriggeredRef.current = false; triggerTranslation(); }}>
                                Retry
                            </button>
                        </div>
                    )}
                    {translateStatus === 'ready' && translation && (
                        <>
                            <div className="translation-tabs">
                                <button
                                    className={`translation-tab ${activeLang === 'en' ? 'active' : ''}`}
                                    onClick={() => setActiveLang('en')}
                                >
                                    English
                                </button>
                                <button
                                    className={`translation-tab ${activeLang === 'nl' ? 'active' : ''}`}
                                    onClick={() => setActiveLang('nl')}
                                >
                                    Nederlands
                                </button>
                                {translation.cached && (
                                    <span className="translation-cached-badge" title="From cache">⚡</span>
                                )}
                            </div>
                            <div className="translation-text">
                                {activeLang === 'en' ? translation.en : translation.nl}
                            </div>
                        </>
                    )}
                </div>
            )}

            {/* Footer with Actions */}
            <div className="flow-card__footer">
                <div className="flex items-center gap-4">
                    <div className="flow-card__feedback">
                        <button
                            className={`feedback-btn ${feedbackGiven === 'like' ? 'active like' : ''}`}
                            onClick={() => handleFeedback('like')}
                            disabled={!!feedbackGiven}
                            title="Relevant"
                        >
                            <span className="btn-icon">✨</span>
                        </button>
                        <button
                            className={`feedback-btn ${feedbackGiven === 'dislike' ? 'active dislike' : ''}`}
                            onClick={() => handleFeedback('dislike')}
                            disabled={!!feedbackGiven}
                            title="Not relevant"
                        >
                            <span className="btn-icon">✕</span>
                        </button>
                        <button
                            className={`feedback-btn ${feedbackGiven === 'save' ? 'active save' : ''}`}
                            onClick={() => handleFeedback('save')}
                            disabled={!!feedbackGiven}
                            title="Keep in Library"
                        >
                            <span className="btn-icon">🔖</span>
                        </button>
                        <button
                            className={`feedback-btn translate-btn ${showTranslation ? 'active translate' : ''} ${translateStatus === 'ready' ? 'has-translation' : ''}`}
                            onClick={handleTranslateToggle}
                            title={translateStatus === 'ready' ? 'Toggle Translation' : 'Translate to EN & NL'}
                        >
                            <span className="btn-icon">🌐</span>
                            {translateStatus === 'loading' && (
                                <span className="translate-spinner" />
                            )}
                            {translateStatus === 'ready' && (
                                <span className="translate-dot" />
                            )}
                        </button>
                    </div>

                    {/* Minimalist Reason in footer */}
                    {card.reason && (
                        <div className="flow-card__footer-reason">
                            {card.reason}
                        </div>
                    )}
                </div>

                <button
                    className={`expand-toggle ${isExpanded ? 'is-expanded' : ''}`}
                    onClick={handleExpandToggle}
                >
                    {isExpanded ? 'Collapse' : 'Read More'}
                </button>
            </div>

            <style>{`
                .flow-card {
                    background: #ffffff;
                    border: 1px solid #E6EAF2;
                    border-left: 3px solid var(--zone-color);
                    border-radius: 20px;
                    padding: 20px;
                    margin-bottom: 12px;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    position: relative;
                    overflow: hidden;
                }

                @media (max-width: 768px) {
                    .flow-card {
                        padding: 16px;
                        margin-bottom: 8px;
                        border-radius: 16px;
                    }
                }

                @media (min-width: 769px) {
                    .flow-card {
                            margin-bottom: 10px;
                    }
                }
                
                .dark .flow-card {
                    background: rgba(15, 23, 42, 0.5);
                    border-color: rgba(255, 255, 255, 0.1);
                }

                .flow-card::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    right: 0;
                    width: 150px;
                    height: 150px;
                    background: radial-gradient(circle at top right, var(--zone-color), transparent 70%);
                    opacity: 0.04;
                    pointer-events: none;
                }

                .flow-card:hover {
                    background: #ffffff;
                    border-color: #DDE2ED;
                    transform: translateY(-2px);
                    box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08);
                }

                .dark .flow-card:hover {
                    background: rgba(15, 23, 42, 0.7);
                    border-color: rgba(204, 86, 30, 0.3);
                    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
                }

                .flow-card__top-bar {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 16px;
                }

                .flow-card__zone-indicator {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }

                .zone-dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    box-shadow: 0 0 10px var(--zone-color);
                }

                .zone-label {
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 0.05em;
                    text-transform: uppercase;
                    color: var(--zone-color);
                    opacity: 0.9;
                }

                @media (max-width: 768px) {
                    .zone-label {
                        font-size: 9px;
                    }
                }

                .flow-card__meta-item {
                    font-size: 12px;
                    font-weight: 600;
                    color: #64748b;
                }

                @media (max-width: 768px) {
                    .flow-card__meta-item {
                        font-size: 10px;
                    }
                }

                .flow-card__header {
                    margin-bottom: 12px;
                }

                .flow-card__title {
                    font-family: 'Outfit', 'Inter', sans-serif;
                    font-size: 17px;
                    font-weight: 700;
                    color: #1e293b;
                    line-height: 1.3;
                    margin: 0 0 8px 0;
                }

                @media (max-width: 768px) {
                    .flow-card__title {
                        font-size: 15px;
                    }
                }

                .dark .flow-card__title {
                    color: #f1f5f9;
                }

                .flow-card__author-pill {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    padding: 4px 12px;
                    background: #F3F5FA;
                    border: 1px solid #E6EAF2;
                    border-radius: 100px;
                    font-size: 12px;
                    color: #475569;
                    font-weight: 500;
                }

                .dark .flow-card__author-pill {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(255, 255, 255, 0.1);
                    color: #94a3b8;
                }

                .flow-card__content {
                    color: #475569;
                    font-size: 15px;
                    line-height: 1.7;
                    max-height: 120px;
                    overflow: hidden;
                    position: relative;
                    transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
                }

                .dark .flow-card__content {
                    color: #94a3b8;
                }

                .flow-card__content:not(.expanded)::after {
                    content: '';
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    width: 100%;
                    height: 60px;
                    background: linear-gradient(to bottom, transparent, rgba(255, 255, 255, 0.95));
                    pointer-events: none;
                }

                .dark .flow-card__content:not(.expanded)::after {
                    background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.9));
                }

                .flow-card__content.expanded {
                    max-height: 2000px;
                    color: #111827;
                }

                .dark .flow-card__content.expanded {
                    color: #f1f5f9;
                }

                /* ---- Translation Panel ---- */
                .flow-card__translation {
                    margin-top: 14px;
                    padding: 14px 16px;
                    background: linear-gradient(135deg, #f0f4ff 0%, #fdf4f0 100%);
                    border: 1px solid rgba(204, 86, 30, 0.15);
                    border-radius: 14px;
                    animation: slideDown 0.3s ease-out;
                }

                .dark .flow-card__translation {
                    background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(60, 30, 15, 0.3) 100%);
                    border-color: rgba(204, 86, 30, 0.25);
                }

                @keyframes slideDown {
                    from { opacity: 0; transform: translateY(-8px); max-height: 0; }
                    to { opacity: 1; transform: translateY(0); max-height: 500px; }
                }

                .translation-loading {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    color: #64748b;
                    font-size: 13px;
                    padding: 8px 0;
                }

                .translation-spinner {
                    width: 16px;
                    height: 16px;
                    border: 2px solid rgba(204, 86, 30, 0.2);
                    border-top: 2px solid #CC561E;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }

                @keyframes spin {
                    to { transform: rotate(360deg); }
                }

                .translation-error {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    color: #ef4444;
                    font-size: 13px;
                }

                .translation-error button {
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 600;
                    color: #CC561E;
                    background: rgba(204, 86, 30, 0.1);
                    border: 1px solid rgba(204, 86, 30, 0.2);
                    border-radius: 8px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }

                .translation-error button:hover {
                    background: rgba(204, 86, 30, 0.2);
                }

                .translation-tabs {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    margin-bottom: 10px;
                }

                .translation-tab {
                    padding: 5px 14px;
                    font-size: 12px;
                    font-weight: 600;
                    border-radius: 20px;
                    border: 1px solid #E6EAF2;
                    background: #ffffff;
                    color: #64748b;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }

                .dark .translation-tab {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(255, 255, 255, 0.1);
                    color: #94a3b8;
                }

                .translation-tab.active {
                    background: #CC561E;
                    border-color: #CC561E;
                    color: #ffffff;
                    box-shadow: 0 2px 8px rgba(204, 86, 30, 0.3);
                }

                .translation-cached-badge {
                    font-size: 14px;
                    margin-left: auto;
                    opacity: 0.6;
                    cursor: default;
                }

                .translation-text {
                    font-size: 14px;
                    line-height: 1.7;
                    color: #334155;
                    white-space: pre-wrap;
                }

                .dark .translation-text {
                    color: #cbd5e1;
                }

                /* ---- Translate Button Styles ---- */
                .translate-btn {
                    position: relative;
                }

                .translate-btn.active.translate {
                    background: rgba(59, 130, 246, 0.1);
                    color: #3b82f6;
                    border-color: rgba(59, 130, 246, 0.2);
                }

                .translate-spinner {
                    position: absolute;
                    top: -2px;
                    right: -2px;
                    width: 10px;
                    height: 10px;
                    border: 1.5px solid rgba(204, 86, 30, 0.2);
                    border-top: 1.5px solid #CC561E;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }

                .translate-dot {
                    position: absolute;
                    top: -1px;
                    right: -1px;
                    width: 8px;
                    height: 8px;
                    background: #22c55e;
                    border-radius: 50%;
                    border: 1.5px solid #ffffff;
                    box-shadow: 0 0 6px rgba(34, 197, 94, 0.4);
                }

                .dark .translate-dot {
                    border-color: rgba(15, 23, 42, 0.8);
                }

                .flow-card__footer-reason {
                    font-size: 12px;
                    line-height: 1.5;
                    color: rgba(204, 86, 30, 0.7);
                    font-weight: 600;
                    font-style: italic;
                    letter-spacing: 0.02em;
                }

                @media (max-width: 768px) {
                    .flow-card__footer-reason {
                        font-size: 10px;
                    }
                }

                .flow-card__footer {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-top: 16px;
                    padding-top: 14px;
                    border-top: 1px solid #E6EAF2;
                }

                .dark .flow-card__footer {
                    border-top-color: rgba(255, 255, 255, 0.1);
                }

                .flow-card__feedback {
                    display: flex;
                    gap: 8px;
                }

                .feedback-btn {
                    width: 38px;
                    height: 38px;
                    border-radius: 10px;
                    border: 1px solid #E6EAF2;
                    background: #ffffff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    color: #64748b;
                    position: relative;
                }

                .dark .feedback-btn {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(255, 255, 255, 0.1);
                    color: #94a3b8;
                }

                .feedback-btn:hover:not(:disabled) {
                    background: #F3F5FA;
                    border-color: #DDE2ED;
                    transform: translateY(-2px);
                    color: #1e293b;
                }

                .dark .feedback-btn:hover:not(:disabled) {
                    background: rgba(255, 255, 255, 0.1);
                    border-color: rgba(204, 86, 30, 0.4);
                    color: #f1f5f9;
                }

                .feedback-btn.active.like { background: rgba(34, 197, 94, 0.1); color: #22c55e; border-color: rgba(34, 197, 94, 0.2); }
                .feedback-btn.active.dislike { background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.2); }
                .feedback-btn.active.save { background: rgba(204, 86, 30, 0.1); color: #CC561E; border-color: rgba(204, 86, 30, 0.2); }

                .expand-toggle {
                    background: transparent;
                    border: none;
                    color: #CC561E;
                    font-size: 13px;
                    font-weight: 700;
                    cursor: pointer;
                    padding: 8px 16px;
                    border-radius: 8px;
                    transition: all 0.2s ease;
                }

                @media (max-width: 768px) {
                    .expand-toggle {
                        font-size: 11px;
                        padding: 6px 12px;
                    }
                }

                .expand-toggle:hover {
                    background: rgba(204, 86, 30, 0.1);
                    transform: translateX(4px);
                }
            `}</style>
        </div>
    );
};

export default FlowCard;
