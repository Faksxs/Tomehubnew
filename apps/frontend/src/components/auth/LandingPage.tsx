import React from 'react';
import { motion } from 'framer-motion';
import {
    Zap,
    Brain,
    Waves,
    ShieldCheck,
    Network,
    ArrowRight,
    Library,
    Sparkles
} from 'lucide-react';
import logo from '../../assets/logo_v9.png';

interface LandingPageProps {
    onLogin: () => void;
}

const FloatingBlob = ({ color, size, initialPos, duration }: { color: string, size: string, initialPos: { x: string, y: string }, duration: number }) => (
    <motion.div
        animate={{
            x: [0, 80, -80, 0],
            y: [0, -100, 100, 0],
            scale: [1, 1.1, 0.95, 1],
        }}
        transition={{
            duration,
            repeat: Infinity,
            ease: "easeInOut"
        }}
        style={{
            position: 'absolute',
            width: size,
            height: size,
            borderRadius: '50%',
            backgroundColor: color,
            filter: 'blur(120px)',
            opacity: 0.1,
            left: initialPos.x,
            top: initialPos.y,
            zIndex: 1
        }}
    />
);

export const LandingPage: React.FC<LandingPageProps> = ({ onLogin }) => {
    const brandOrange = "#CC561E";

    const features = [
        {
            icon: <Library className="w-5 h-5" style={{ color: brandOrange }} />,
            subtitle: "The Foundation",
            title: "Dynamic Synthesis Hub",
            description: "A unified home for Books, Articles, Websites, and Notes. Enhanced by Night Shift processing.",
            highlight: "All-in-One Evolution",
            accent: brandOrange
        },
        {
            icon: <Zap className="w-5 h-5 text-yellow-500" />,
            subtitle: "The Reflex",
            title: "Smart Retrieval",
            description: "Sub-second response. Lemma-based and semantic proximity scan for instant access.",
            highlight: "Instant & Localized",
            accent: "#EAB308"
        },
        {
            icon: <Brain className="w-5 h-5 text-indigo-500" />,
            subtitle: "The Brain",
            title: "Explorer & Deep AI",
            description: "Dual AI validation. Work AI synthesizes while Judge AI evaluates answers with zero risk.",
            highlight: "Verified Intelligence",
            accent: "#6366F1"
        },
        {
            icon: <Waves className="w-5 h-5 text-blue-500" />,
            subtitle: "The Intuition",
            title: "Flow & Flux System",
            description: "Discovery beyond search. Uses graph mechanics to surface hidden connections organically.",
            highlight: "Autonomous Discovery",
            accent: "#3B82F6"
        },
        {
            icon: <Network className="w-5 h-5 text-emerald-500" />,
            subtitle: "Relational Intelligence",
            title: "Graph & Vector Harmony",
            description: "Blends vector similarity with knowledge graph traversal for deep connectivity.",
            highlight: "Contextual Depth",
            accent: "#10B981"
        },
        {
            icon: <ShieldCheck className="w-5 h-5 text-slate-500" />,
            subtitle: "Governance",
            title: "Privacy & Isolation",
            description: "Strict tenant isolation and absolute data privacy. Your vault remains exclusively yours.",
            highlight: "Absolute Security",
            accent: "#64748B"
        }
    ];

    return (
        <div className="min-h-screen bg-[#0d1117] text-slate-100 transition-colors duration-500 relative overflow-hidden flex flex-col font-sans">

            {/* Background System: Vignette, Network Pattern & Noise */}
            <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_transparent_0%,_rgba(13,17,23,0.8)_100%)] z-[5]" />
                <div className="absolute inset-0 opacity-[0.03] animate-pulse z-[2]"
                    style={{
                        backgroundImage: `radial-gradient(circle, ${brandOrange} 1px, transparent 1px)`,
                        backgroundSize: '40px 40px'
                    }}
                />
                <div className="absolute inset-0 opacity-[0.05] contrast-150 brightness-150 z-[10] mix-blend-overlay pointer-events-none"
                    style={{
                        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3%3Cfilter id='noiseFilter'%3%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3%3C/filter%3%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3%3C/svg%3")`
                    }}
                />
                <FloatingBlob color={brandOrange} size="700px" initialPos={{ x: '-5%', y: '15%' }} duration={30} />
                <FloatingBlob color="#6366f1" size="600px" initialPos={{ x: '65%', y: '-5%' }} duration={25} />
            </div>

            <main className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 relative z-20">

                {/* Hero Section */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    className="text-center max-w-5xl mb-8 md:mb-10"
                >
                    <div className="mb-6 flex justify-center">
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            transition={{ delay: 0.2, type: "spring", stiffness: 60 }}
                            className="relative"
                        >
                            {/* Diffused Premium Halo Glow */}
                            <div className="absolute inset-[-40px] bg-orange-500/12 blur-[140px] rounded-full pointer-events-none" />
                            <img
                                src={logo}
                                alt="TomeHub Logo"
                                className="h-32 md:h-40 w-auto object-contain drop-shadow-[0_20px_60px_rgba(204,86,30,0.3)] brightness-110 relative z-10"
                            />
                        </motion.div>
                    </div>

                    <h1 className="text-3xl md:text-5xl font-black tracking-tight mb-4 leading-[1.1] text-white">
                        From Information to<br />
                        <span className="relative inline-block bg-clip-text text-transparent bg-gradient-to-r from-[#CC561E] via-[#ff8a50] to-[#CC561E] animate-gradient-x">
                            Justified Knowledge
                        </span>
                    </h1>

                    <p className="text-lg md:text-xl text-slate-400 max-w-3xl mx-auto mb-8 leading-relaxed font-medium">
                        Interact dynamically with your personal knowledge base. TomeHub is a <span className="text-white font-bold">multi-dimensional synthesis tool</span> for evidence-based intelligence.
                    </p>

                    <div className="flex flex-col items-center gap-6">
                        <motion.button
                            whileHover={{ scale: 1.05, translateY: -2, boxShadow: `0 20px 50px ${brandOrange}44` }}
                            whileTap={{ scale: 0.98 }}
                            onClick={onLogin}
                            className="px-10 py-5 text-white rounded-xl font-black text-lg shadow-2xl transition-all flex items-center gap-4 border border-white/10 backdrop-blur-xl group relative overflow-hidden"
                            style={{ backgroundColor: brandOrange }}
                        >
                            <Sparkles className="w-5 h-5 fill-white animate-pulse" />
                            Continue with Google
                        </motion.button>
                        <div className="flex flex-wrap justify-center items-center gap-x-8 gap-y-2 text-[9px] font-black uppercase tracking-[0.4em] text-slate-500">
                            <span className="flex items-center gap-2">
                                <div className="w-1 h-1 rounded-full" style={{ backgroundColor: brandOrange }} />
                                Dynamic Synthesis
                            </span>
                            <span className="flex items-center gap-2">
                                <div className="w-1 h-1 rounded-full" style={{ backgroundColor: brandOrange }} />
                                Deep Intelligence
                            </span>
                            <span className="flex items-center gap-2">
                                <div className="w-1 h-1 rounded-full" style={{ backgroundColor: brandOrange }} />
                                Relational Graph
                            </span>
                        </div>
                    </div>
                </motion.div>

                {/* Architectural 6-Block Feature Grid with Softened Aesthetics */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 md:gap-6 w-full max-w-[1240px]">
                    {features.map((feature, idx) => (
                        <motion.div
                            key={idx}
                            initial={{ opacity: 0, scale: 0.98 }}
                            whileInView={{ opacity: 1, scale: 1 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.1 * idx }}
                            className="relative group h-full"
                        >
                            {/* Soft Card Container */}
                            <div className="h-full rounded-3xl border border-white/5 bg-[#161b22]/30 backdrop-blur-xl transition-all duration-500 group-hover:bg-[#1c2128]/50 group-hover:border-white/10 group-hover:translate-y-[-6px] group-hover:shadow-[0_40px_80px_-20px_rgba(0,0,0,0.6)] flex flex-col overflow-hidden relative">

                                {/* Ultra-thin Minimal Accent (Top) */}
                                <div className="absolute top-0 left-0 right-0 h-[1px] opacity-10 group-hover:opacity-100 transition-opacity duration-500"
                                    style={{ backgroundColor: feature.accent }}
                                />

                                {/* Diffused Inner Glow */}
                                <div className="absolute inset-[1px] rounded-[inherit] border border-white/[0.03] pointer-events-none" />

                                <div className="p-7 md:p-8 flex flex-col h-full relative z-10">
                                    <div className="mb-6 p-4 rounded-2xl w-fit bg-white/5 border border-white/5 group-hover:scale-105 group-hover:bg-white/[0.08] transition-all duration-500">
                                        {feature.icon}
                                    </div>

                                    <div className="flex-1">
                                        <h3 className="text-xl md:text-2xl font-black mb-3 text-white leading-tight">
                                            {feature.title}
                                        </h3>
                                        <p className="text-[14px] md:text-[15px] text-slate-400 leading-relaxed font-normal">
                                            {feature.description}
                                        </p>
                                    </div>

                                    <div className="mt-8 pt-6 border-t border-white/[0.05] flex items-center justify-between">
                                        <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 group-hover:text-orange-500/80 transition-colors">
                                            {feature.highlight}
                                        </span>
                                        <ArrowRight className="w-5 h-5 text-slate-500 opacity-0 group-hover:opacity-100 transition-all translate-x-3 group-hover:translate-x-0" />
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </main>

            <footer className="py-8 px-8 border-t border-white/5 text-center relative z-20 bg-black/10 backdrop-blur-md">
                <p className="text-[10px] font-black uppercase tracking-[0.8em] text-slate-600 opacity-60">
                    TomeHub • Multi-Layer Knowledge Engine
                </p>
            </footer>
        </div>
    );
};
