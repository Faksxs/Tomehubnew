import React from 'react';

interface LogoProps {
    className?: string;
    size?: number;
}

export const KnowledgeBaseLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <defs>
            <linearGradient id="kb-grad-orange" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#CC561E" />
                <stop offset="100%" stopColor="#A44319" />
            </linearGradient>
        </defs>
        <rect x="2" y="2" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.8" />
        <rect x="9" y="2" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.4" />
        <rect x="16" y="2" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.2" />
        <rect x="2" y="9" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.4" />
        <rect x="9" y="9" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" />
        <rect x="16" y="9" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.4" />
        <rect x="2" y="16" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.2" />
        <rect x="9" y="16" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.4" />
        <rect x="16" y="16" width="6" height="6" rx="2" fill="url(#kb-grad-orange)" fillOpacity="0.8" />
    </svg>
);

export const HighlightsLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <path d="M12 20H21" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        <path d="M16.5 3.5C17.3284 2.67157 18.6716 2.67157 19.5 3.5C20.3284 4.32843 20.3284 5.67157 19.5 6.5L7 19L3 20L4 16L16.5 3.5Z" stroke="#CC561E" strokeWidth="2" strokeLinejoin="round" />
        <path d="M15 5L19 9" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.4" />
    </svg>
);

export const BooksLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Vertical Books with varying heights */}
        <rect x="3" y="6" width="4" height="12" rx="0.5" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.1" />
        <path d="M4 9H6" stroke="#CC561E" strokeWidth="1" strokeLinecap="round" strokeOpacity="0.4" />

        <rect x="8" y="4" width="4" height="14" rx="0.5" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.3" />
        <path d="M9 7H11" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M9 15H11" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" />

        <rect x="13" y="7" width="4" height="11" rx="0.5" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.1" />

        {/* Leaning Book */}
        <rect x="18" y="5" width="4" height="13" rx="0.5" transform="rotate(12 18 5)" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.8" />

        {/* Shelf Line */}
        <path d="M2 19H22" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.3" />
    </svg>
);

export const ArticlesLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <path d="M4 4H14L20 10V20H4V4Z" stroke="#CC561E" strokeWidth="2" strokeLinejoin="round" />
        <path d="M14 4V10H20" stroke="#CC561E" strokeWidth="2" strokeLinejoin="round" />
        <path d="M8 14H16" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        <path d="M8 17H12" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
    </svg>
);

export const WebsitesLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Simplified Globe */}
        <circle cx="11" cy="11" r="9" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.05" />
        <ellipse cx="11" cy="11" rx="3.5" ry="9" stroke="#CC561E" strokeWidth="1.5" strokeOpacity="0.6" />
        <path d="M2 11H20" stroke="#CC561E" strokeWidth="1.5" strokeOpacity="0.6" />
        <path d="M11 2V20" stroke="#CC561E" strokeWidth="1.5" strokeOpacity="0.6" />

        {/* Clear Cursor Arrow */}
        <path d="M16 14L22 17L19 18L21 21L19 22L17 19L14 22V14Z" fill="#CC561E" stroke="#000" strokeWidth="0.5" />
    </svg>
);

export const NotesLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Background Notebook Sheet */}
        <rect x="5" y="5" width="14" height="15" rx="1.5" stroke="#CC561E" strokeWidth="2" strokeOpacity="0.3" fill="#CC561E" fillOpacity="0.1" />
        {/* Main Sticky Note / Notebook Page */}
        <path d="M3 4C3 3.44772 3.44772 3 4 3H19C19.5523 3 20 3.44772 20 4V20C20 20.5523 19.5523 21 19 21H4C3.44772 21 3 20.5523 3 20V4Z" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.15" />
        {/* Notebook Binding / Rings */}
        <path d="M5 1V5M9 1V5M13 1V5M17 1V5" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        {/* Lines on the Page */}
        <path d="M7 9H16" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.6" />
        <path d="M7 12H16" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.6" />
        <path d="M7 15H16" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.6" />
        {/* Folded Corner */}
        <path d="M16 21L20 17" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
    </svg>
);

export const ProgressLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Bar Chart */}
        <path d="M6 20V14" stroke="#CC561E" strokeWidth="3" strokeLinecap="round" />
        <path d="M12 20V10" stroke="#CC561E" strokeWidth="3" strokeLinecap="round" />
        <path d="M18 20V5" stroke="#CC561E" strokeWidth="3" strokeLinecap="round" />
        {/* Trend Line Arrow */}
        <path d="M4 14L10 8L15 13L21 4" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M21 4H16" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        <path d="M21 4V9" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
    </svg>
);

export const SystemDistributionLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Top Left Square */}
        <rect x="5" y="5" width="6" height="6" rx="2" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.1" />
        {/* Top Right Square */}
        <rect x="13" y="5" width="6" height="6" rx="2" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.1" />
        {/* Bottom Left Square */}
        <rect x="5" y="13" width="6" height="6" rx="2" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.1" />
        {/* Bottom Right Diamond (Rotated Square) */}
        <rect x="16" y="13" width="6" height="6" rx="2" transform="rotate(45 16 16)" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.1" />
    </svg>
);

export const FocusLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Outer Ring */}
        <circle cx="12" cy="12" r="9" stroke="#CC561E" strokeWidth="2" strokeOpacity="0.8" />
        {/* Middle Ring */}
        <circle cx="12" cy="12" r="6" stroke="#CC561E" strokeWidth="1.5" strokeOpacity="0.5" />
        {/* Bullseye */}
        <circle cx="12" cy="12" r="3" fill="#CC561E" fillOpacity="0.8" />

        {/* Arrow Shaft (entering from top right) */}
        <path d="M19 5L13.5 10.5" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        {/* Arrow Fletching */}
        <path d="M19 5L20 9" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        <path d="M19 5L15 4" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
    </svg>
);

export const InventoryLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Main Box Body */}
        <path d="M21 8V20C21 21.1046 20.1046 22 19 22H5C3.89543 22 3 21.1046 3 20V8" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="#CC561E" fillOpacity="0.05" />

        {/* Lid / Top Cover */}
        <path d="M23 3H1V8H23V3Z" stroke="#CC561E" strokeWidth="2" strokeLinejoin="round" fill="#CC561E" fillOpacity="0.1" />

        {/* Label / Handle Area */}
        <rect x="10" y="12" width="4" height="2" rx="0.5" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />

        {/* Architectural Detail Lines */}
        <path d="M7 16H17" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.4" />
        <path d="M7 19H17" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.4" />
    </svg>
);

export const DashboardLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Central Nexus Square */}
        <rect x="9" y="9" width="6" height="6" rx="1" stroke="#CC561E" strokeWidth="2" fill="#CC561E" fillOpacity="0.8" />
        {/* Outbound Connection Points */}
        <path d="M12 3V9M12 15V21M3 12H9M15 12H21" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
        {/* Floating Architectural Pillars */}
        <path d="M6 6L8 8M16 16L18 18M6 18L8 16M16 8L18 6" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.4" />
    </svg>
);

export const SmartSearchLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Main Lens Circle */}
        <circle cx="11" cy="11" r="7" stroke="#CC561E" strokeWidth="2.5" fill="#CC561E" fillOpacity="0.05" />

        {/* Optical Glass Highlight (White) */}
        <path d="M14.5 7.5C14.5 7.5 13.5 6.5 11 6.5" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.7" />

        {/* Inner Detail Ring */}
        <circle cx="11" cy="11" r="4" stroke="#CC561E" strokeWidth="1" strokeOpacity="0.3" />

        {/* Handle */}
        <path d="M16 16L20 20" stroke="#CC561E" strokeWidth="3" strokeLinecap="round" />

        {/* Architectural Handle Detail */}
        <path d="M17 17L19 19" stroke="#fff" strokeWidth="1" strokeLinecap="round" strokeOpacity="0.5" />

        {/* Intelligent Sparkles (Discovery) */}
        <circle cx="18" cy="6" r="1.5" fill="#CC561E" fillOpacity="0.8" />
        <circle cx="21" cy="9" r="1" fill="#CC561E" fillOpacity="0.4" />
    </svg>
);

export const DeepChatbotLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <g transform="translate(-1, -1) scale(1.15)">
            {/* Magic Lamp Body */}
            <path d="M19 16C19 16 20.5 14.5 21 13C21.5 11.5 20.5 11 19 11C15 11 14 11 11 11C9 11 6 12 4 10C2.5 8.5 2 9 3 10.5C4 12 6 13 8 13L9 16H15L16 13H17C18 13 18.5 13.5 19 14.5C19 15.5 18 16 19 16Z" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="#CC561E" fillOpacity="0.1" />

            {/* Base of the Lamp */}
            <path d="M10 16L9 18H15L14 16" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M8 18H16" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />

            {/* Handle */}
            <path d="M19 11C21 11 22 12.5 21 14C20 15.5 18.5 15.5 19 16" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />

            {/* Lid / Top Detail */}
            <path d="M12 11V9" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" />
            <path d="M10 9H14" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" />

            {/* Magic Smoke / Genie Effect */}
            <path d="M3 9C2 7 4 6 5 5C6 4 5 2 7 2" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="3 3" />

            {/* Magic Sparkles */}
            <path d="M5 4L5.5 3M7 5L8 4" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.8" />
            <circle cx="8" cy="3" r="1" fill="#fff" fillOpacity="0.8" />
            <circle cx="3" cy="6" r="1" fill="#CC561E" fillOpacity="0.6" />
        </g>
    </svg>
);

export const FluxLogo: React.FC<LogoProps> = ({ className, size = 24 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        {/* Layered Waves of Data */}
        <path d="M2 6C6 6 6 10 10 10C14 10 14 6 18 6C20 6 21 7 22 8" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" fill="#CC561E" fillOpacity="0.05" />
        <path d="M2 12C6 12 6 16 10 16C14 16 14 12 18 12C20 12 21 13 22 14" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" fill="#CC561E" fillOpacity="0.1" />
        <path d="M2 18C6 18 6 22 10 22C14 22 14 18 18 18C20 18 21 19 22 20" stroke="#CC561E" strokeWidth="2" strokeLinecap="round" fill="#CC561E" fillOpacity="0.2" />
        {/* Vertical Stream Connection */}
        <path d="M10 4V20" stroke="#CC561E" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="2 4" strokeOpacity="0.5" />
    </svg>
);
