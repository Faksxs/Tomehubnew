import React, { useState, useRef } from 'react';

interface StarRatingProps {
    value?: number; // 0.5-5 in 0.5 steps, undefined = unrated
    onChange?: (rating: number) => void;
    readonly?: boolean;
    size?: number;
}

/** Renders a single star that can be full, half, or empty */
const StarIcon: React.FC<{ fill: 'full' | 'half' | 'empty'; size: number }> = ({ fill, size }) => {
    const id = `half-${Math.random().toString(36).slice(2, 7)}`;
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
        >
            {fill === 'half' && (
                <defs>
                    <linearGradient id={id} x1="0" x2="1" y1="0" y2="0">
                        <stop offset="50%" stopColor="#FBBF24" />
                        <stop offset="50%" stopColor="transparent" />
                    </linearGradient>
                </defs>
            )}
            <polygon
                points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"
                stroke="#FBBF24"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill={
                    fill === 'full'
                        ? '#FBBF24'
                        : fill === 'half'
                            ? `url(#${id})`
                            : 'transparent'
                }
                className={fill === 'empty' ? 'stroke-slate-300 dark:stroke-slate-600' : ''}
            />
        </svg>
    );
};

const StarRating: React.FC<StarRatingProps> = ({
    value,
    onChange,
    readonly = false,
    size = 20,
}) => {
    const [hovered, setHovered] = useState<number | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    const effective = hovered ?? value ?? 0;

    const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>, star: number) => {
        if (readonly) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        setHovered(x < rect.width / 2 ? star - 0.5 : star);
    };

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>, star: number) => {
        if (readonly || !onChange) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const newRating = x < rect.width / 2 ? star - 0.5 : star;
        onChange(value === newRating ? 0 : newRating);
    };

    const getFill = (star: number): 'full' | 'half' | 'empty' => {
        if (effective >= star) return 'full';
        if (effective >= star - 0.5) return 'half';
        return 'empty';
    };

    return (
        <div
            ref={containerRef}
            className="flex items-center gap-0.5"
            role={readonly ? 'img' : 'radiogroup'}
            aria-label={`Rating: ${value ?? 'not rated'} out of 5`}
            onMouseLeave={() => !readonly && setHovered(null)}
        >
            {[1, 2, 3, 4, 5].map((star) => (
                <button
                    key={star}
                    type="button"
                    disabled={readonly}
                    aria-label={`${star} stars`}
                    onMouseMove={(e) => handleMouseMove(e, star)}
                    onClick={(e) => handleClick(e, star)}
                    className={`transition-transform focus:outline-none ${readonly ? 'cursor-default' : 'cursor-pointer hover:scale-110'
                        }`}
                >
                    <StarIcon fill={getFill(star)} size={size} />
                </button>
            ))}
            {!readonly && value !== undefined && value > 0 && (
                <span className="ml-2 text-xs text-slate-500 dark:text-slate-400 select-none tabular-nums">
                    {value % 1 === 0 ? `${value}.0` : value}/5
                </span>
            )}
        </div>
    );
};

export default StarRating;
