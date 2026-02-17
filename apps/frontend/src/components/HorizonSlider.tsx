/**
 * HorizonSlider Component
 * Controls the "Expanding Horizons" level from Focus to Discovery
 */

import React from 'react';

interface HorizonSliderProps {
    value: number; // 0.0 to 1.0
    onChange: (value: number) => void;
    disabled?: boolean;
}

const ZONE_LABELS = [
    { label: '📖 Focus', description: 'Same book, nearby pages' },
    { label: '✍️ Author', description: "Same author's other works" },
    { label: '🔗 Syntopic', description: 'Similar ideas across authors' },
    { label: '🌉 Bridge', description: 'Unexpected connections' },
];

export const HorizonSlider: React.FC<HorizonSliderProps> = ({
    value,
    onChange,
    disabled = false
}) => {
    // Determine active zone based on value
    const getActiveZone = (val: number): number => {
        if (val < 0.25) return 0;
        if (val < 0.50) return 1;
        if (val < 0.75) return 2;
        return 3;
    };

    const activeZone = getActiveZone(value);

    return (
        <div className="horizon-slider">
            <div className="horizon-slider__header">
                <div className="flex flex-col">
                    <span className="horizon-slider__title">Epistemic Horizon</span>
                    <span className="text-[10px] text-card-foreground/70 font-medium tracking-tight">Search Breadth Control</span>
                </div>
                <div className="horizon-slider__value-badge">
                    {Math.round(value * 100)}%
                </div>
            </div>

            {/* Slider */}
            <div className="horizon-slider__track-container">
                <input
                    type="range"
                    min="0"
                    max="100"
                    value={value * 100}
                    onChange={(e) => onChange(parseInt(e.target.value) / 100)}
                    disabled={disabled}
                    className="horizon-slider__input"
                />
                <div
                    className="horizon-slider__progress"
                    style={{ width: `${value * 100}%` }}
                />
            </div>

            {/* Zone Labels */}
            <div className="horizon-slider__zones">
                {ZONE_LABELS.map((zone, index) => {
                    const isActive = index === activeZone;
                    const emoji = zone.label.split(' ')[0];
                    const text = zone.label.split(' ')[1];

                    return (
                        <div
                            key={index}
                            className={`horizon-slider__zone ${isActive ? 'active' : ''}`}
                            onClick={() => onChange((index * 0.25) + 0.125)}
                        >
                            <span className="zone-emoji">{emoji}</span>
                            <span className="zone-text">{text}</span>
                            {isActive && (
                                <div className="active-indicator"></div>
                            )}
                        </div>
                    );
                })}
            </div>

            <style>{`
                .horizon-slider {
                    background: hsl(var(--card));
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    padding: 12px;
                }

                .horizon-slider__header {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 12px;
                }

                .horizon-slider__title {
                    font-size: 13px;
                    font-weight: 700;
                    color: hsl(var(--card-foreground));
                    letter-spacing: -0.01em;
                    font-family: 'Outfit', sans-serif;
                }

                .horizon-slider__value-badge {
                    padding: 2px 8px;
                    background: rgba(204, 86, 30, 0.1);
                    color: #CC561E;
                    font-size: 11px;
                    font-weight: 800;
                    border-radius: 6px;
                    font-family: 'JetBrains Mono', monospace;
                }

                .horizon-slider__track-container {
                    position: relative;
                    height: 4px;
                    background: rgba(255, 255, 255, 0.08);
                    border-radius: 100px;
                    margin-bottom: 12px;
                    overflow: visible;
                }

                .horizon-slider__input {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    -webkit-appearance: none;
                    appearance: none;
                    background: transparent;
                    cursor: pointer;
                    z-index: 5;
                    margin: 0;
                    padding: 0;
                }

                .horizon-slider__input::-webkit-slider-thumb {
                    -webkit-appearance: none;
                    width: 14px;
                    height: 14px;
                    border-radius: 50%;
                    background: #fff;
                    box-shadow: 0 0 10px rgba(204, 86, 30, 0.5);
                    cursor: grab;
                    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                    border: 3px solid #CC561E;
                }

                .horizon-slider__input::-webkit-slider-thumb:hover {
                    transform: scale(1.1);
                    box-shadow: 0 0 20px rgba(204, 86, 30, 0.7);
                }

                .horizon-slider__progress {
                    position: absolute;
                    top: 0;
                    left: 0;
                    height: 100%;
                    background: linear-gradient(90deg, #CC561E 0%, #e66a2e 100%);
                    border-radius: 100px;
                    pointer-events: none;
                    z-index: 1;
                }

                .horizon-slider__zones {
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 2px;
                }

                .horizon-slider__zone {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 2px;
                    padding: 8px 2px;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    position: relative;
                }

                .horizon-slider__zone:hover {
                    background: rgba(255, 255, 255, 0.06);
                }

                .horizon-slider__zone.active {
                    background: rgba(204, 86, 30, 0.08);
                }

                .zone-emoji {
                    font-size: 14px;
                    filter: grayscale(1) opacity(0.55);
                    transition: all 0.3s ease;
                }

                .horizon-slider__zone.active .zone-emoji {
                    filter: grayscale(0) opacity(1);
                    transform: scale(1.1);
                }

                .zone-text {
                    font-size: 9px;
                    font-weight: 700;
                    color: rgba(255, 255, 255, 0.7);
                    text-transform: uppercase;
                    letter-spacing: 0.02em;
                    transition: all 0.3s ease;
                    text-align: center;
                }

                .horizon-slider__zone.active .zone-text {
                    color: rgba(255, 255, 255, 0.95);
                }

                .active-indicator {
                    position: absolute;
                    bottom: 0;
                    width: 3px;
                    height: 3px;
                    background: #CC561E;
                    border-radius: 50%;
                    box-shadow: 0 0 8px #CC561E;
                }
            `}</style>
        </div>
    );
};

export default HorizonSlider;
