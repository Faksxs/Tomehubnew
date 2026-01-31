/**
 * FlowCard Component
 * Renders a single card in the Knowledge Stream
 */

import React, { useState } from 'react';
import { FlowCard as FlowCardType, FeedbackAction, sendFlowFeedback } from '../services/flowService';

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
                {card.page_number && (
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

            {/* Reason Tag - Minimalist */}
            <div className="flow-card__reason">
                <div className="reason-icon">💭</div>
                <p>{card.reason}</p>
            </div>

            {/* Footer with Actions */}
            <div className="flow-card__footer">
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

                <button
                    className={`expand-toggle ${isExpanded ? 'is-expanded' : ''}`}
                    onClick={() => setIsExpanded(!isExpanded)}
                >
                    {isExpanded ? 'Collapse' : 'Read More'}
                </button>
            </div>

            <style>{`
                .flow-card {
                    background: rgba(255, 255, 255, 0.03);
                    backdrop-filter: blur(16px);
                    -webkit-backdrop-filter: blur(16px);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-left: 3px solid var(--zone-color);
                    border-radius: 20px;
                    padding: 24px;
                    margin-bottom: 20px;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    position: relative;
                    overflow: hidden;
                }

                .flow-card::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    right: 0;
                    width: 150px;
                    height: 150px;
                    background: radial-gradient(circle at top right, var(--zone-color), transparent 70%);
                    opacity: 0.05;
                    pointer-events: none;
                }

                .flow-card:hover {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(255, 255, 255, 0.15);
                    transform: translateY(-2px);
                    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
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
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 100px;
                    font-size: 12px;
                    color: #cbd5e1;
                    font-weight: 500;
                }

                .flow-card__content {
                    color: #94a3b8;
                    font-size: 15px;
                    line-height: 1.7;
                    max-height: 120px;
                    overflow: hidden;
                    position: relative;
                    transition: max-height 0.5s ease;
                }

                .flow-card__content:not(.expanded)::after {
                    content: '';
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    width: 100%;
                    height: 60px;
                    background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.9));
                    pointer-events: none;
                }

                .flow-card__content.expanded {
                    max-height: 2000px;
                    color: #334155;
                }

                .dark .flow-card__content.expanded {
                    color: #e2e8f0;
                }

                .flow-card__reason {
                    margin-top: 20px;
                    padding: 16px;
                    background: rgba(255, 255, 255, 0.03);
                    border-radius: 12px;
                    display: flex;
                    gap: 12px;
                    align-items: flex-start;
                }

                .reason-icon {
                    font-size: 18px;
                    opacity: 0.8;
                }

                .flow-card__reason p {
                    margin: 0;
                    font-size: 13px;
                    line-height: 1.5;
                    color: rgba(204, 86, 30, 0.8);
                    font-weight: 500;
                    font-style: italic;
                }

                .flow-card__footer {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-top: 24px;
                    padding-top: 20px;
                    border-top: 1px solid rgba(255, 255, 255, 0.05);
                }

                .flow-card__feedback {
                    display: flex;
                    gap: 8px;
                }

                .feedback-btn {
                    width: 38px;
                    height: 38px;
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    background: rgba(255, 255, 255, 0.02);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    color: #64748b;
                }

                .feedback-btn:hover:not(:disabled) {
                    background: rgba(255, 255, 255, 0.08);
                    border-color: rgba(255, 255, 255, 0.2);
                    transform: translateY(-2px);
                    color: #fff;
                }

                .feedback-btn.active.like { background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: rgba(34, 197, 94, 0.3); }
                .feedback-btn.active.dislike { background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
                .feedback-btn.active.save { background: rgba(204, 86, 30, 0.15); color: #CC561E; border-color: rgba(204, 86, 30, 0.3); }

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
