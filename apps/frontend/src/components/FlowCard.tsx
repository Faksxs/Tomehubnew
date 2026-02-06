/**
 * FlowCard Component
 * Renders a single card in the Knowledge Stream
 */

import React, { useState } from 'react';
import { FlowCard as FlowCardType, FeedbackAction, sendFlowFeedback } from '../services/flowService';

interface FlowCardProps {
    card: FlowCardType;
    sessionId: number;
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

export const FlowCard: React.FC<FlowCardProps> = ({
    card,
    sessionId,
    firebaseUid,
    onFeedback
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [feedbackGiven, setFeedbackGiven] = useState<FeedbackAction | null>(null);
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
                    onClick={() => setIsExpanded(!isExpanded)}
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
                    padding: 24px;
                    margin-bottom: 20px;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    position: relative;
                    overflow: hidden;
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

                .flow-card__meta-item {
                    font-size: 12px;
                    font-weight: 600;
                    color: #64748b;
                }

                .flow-card__header {
                    margin-bottom: 16px;
                }

                .flow-card__title {
                    font-family: 'Outfit', 'Inter', sans-serif;
                    font-size: 17px;
                    font-weight: 700;
                    color: #1e293b;
                    line-height: 1.3;
                    margin: 0 0 8px 0;
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

                .flow-card__footer-reason {
                    font-size: 12px;
                    line-height: 1.5;
                    color: rgba(204, 86, 30, 0.7);
                    font-weight: 600;
                    font-style: italic;
                    letter-spacing: 0.02em;
                }

                .flow-card__footer {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-top: 24px;
                    padding-top: 20px;
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

                .expand-toggle:hover {
                    background: rgba(204, 86, 30, 0.1);
                    transform: translateX(4px);
                }
            `}</style>
        </div>
    );
};

export default FlowCard;
