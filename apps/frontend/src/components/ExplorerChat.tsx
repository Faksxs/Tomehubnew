import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, BookOpen, ChevronDown, ChevronUp, RotateCcw, MessageCircle, User, Bot, Compass, Brain, Gauge, Quote, ExternalLink } from 'lucide-react';
import { sendChatMessage } from '../services/backendApiService';
import { ContextBar } from './ContextBar';

interface Message {
    id: number;
    role: 'user' | 'assistant';
    content: string;
    sources?: Array<{
        id?: number;
        title: string;
        score: number;
        page_number: number;
        content?: string;
    }>;
    thinkingHistory?: Array<{
        attempt: number;
        answer: string;
        evaluation: {
            verdict: string;
            overall_score: number;
            explanation: string;
        };
        latency: number;
    }>;
    timestamp: string;
}

interface ExplorerChatProps {
    userId: string;
    onBack?: () => void;
}

export const ExplorerChat: React.FC<ExplorerChatProps> = ({ userId, onBack }) => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [sessionId, setSessionId] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());
    const [expandedThinking, setExpandedThinking] = useState<Set<number>>(new Set());
    const [hoveredCitation, setHoveredCitation] = useState<{ id: number; messageId: number; x: number; y: number } | null>(null);
    const [scopeMode, setScopeMode] = useState<'AUTO' | 'BOOK_FIRST'>('AUTO');

    // Structured Context State
    const [conversationState, setConversationState] = useState<{
        active_topic?: string;
        assumptions?: Array<{ id: number; text: string; confidence: string }>;
        open_questions?: string[];
        established_facts?: Array<{ text: string; source: string }>;
    }>({});

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Auto-scroll to bottom when new messages arrive
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Focus input on mount
    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    const handleSend = async () => {
        if (!input.trim() || isLoading) return;

        // Validate userId
        if (!userId || userId.includes('@')) {
            setError('Authentication error. Please refresh the page.');
            return;
        }

        const userMessage: Message = {
            id: Date.now(),
            role: 'user',
            content: input.trim(),
            timestamp: new Date().toISOString()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);
        setError(null);

        try {
            const response = await sendChatMessage(
                userMessage.content,
                userId,
                sessionId,
                'EXPLORER',
                null,
                20,
                scopeMode
            );

            if (response.session_id) {
                setSessionId(response.session_id);
            }

            if (response.conversation_state) {
                setConversationState(response.conversation_state);
            }

            const assistantMessage: Message = {
                id: Date.now() + 1,
                role: 'assistant',
                content: response.answer || '',
                sources: response.sources || [],
                thinkingHistory: response.thinking_history || [],
                timestamp: response.timestamp || new Date().toISOString()
            };
            setMessages(prev => [...prev, assistantMessage]);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send message');
        } finally {
            setIsLoading(false);
            inputRef.current?.focus();
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const toggleThinking = (messageId: number) => {
        setExpandedThinking(prev => {
            const next = new Set(prev);
            if (next.has(messageId)) {
                next.delete(messageId);
            } else {
                next.add(messageId);
            }
            return next;
        });
    };

    const toggleSources = (messageId: number) => {
        setExpandedSources(prev => {
            const next = new Set(prev);
            if (next.has(messageId)) {
                next.delete(messageId);
            } else {
                next.add(messageId);
            }
            return next;
        });
    };

    const startNewConversation = () => {
        setMessages([]);
        setSessionId(null);
        setError(null);
        setConversationState({});
        inputRef.current?.focus();
    };

    // Clean answer: remove internal self-check sections and system tags
    const cleanAnswer = (text: string) => {
        return text
            .replace(/\[DÜŞÜNCE SÜRECİ\][\s\S]*?\[\/DÜŞÜNCE SÜRECİ\]/, "")
            .replace(/## AŞAMA 0:[\s\S]*?(?=##)/, "")
            .trim();
    };

    // Render text with in-text citation parsing [ID: X]
    const renderTextWithCitations = (text: string, sources?: Message['sources'], messageId?: number) => {
        if (!sources) return text;

        const parts = text.split(/(\[ID: \d+\])/g);
        return parts.map((part, i) => {
            const match = part.match(/\[ID: (\d+)\]/);
            if (match) {
                const sourceId = parseInt(match[1]);
                const source = sources.find(s => s.id === sourceId);

                if (source) {
                    return (
                        <button
                            key={i}
                            onMouseEnter={(e) => {
                                const rect = e.currentTarget.getBoundingClientRect();
                                setHoveredCitation({
                                    id: sourceId,
                                    messageId: messageId || 0,
                                    x: rect.left,
                                    y: rect.top - 10
                                });
                            }}
                            onMouseLeave={() => setHoveredCitation(null)}
                            className="inline-flex items-center justify-center w-5 h-5 mx-0.5 text-[10px] font-bold bg-[#CC561E]/10 dark:bg-[#CC561E]/20 text-[#CC561E] dark:text-[#f3a47b] rounded-md border border-[#CC561E]/20 dark:border-[#CC561E]/30 hover:bg-[#CC561E] hover:text-white transition-all transform hover:-translate-y-0.5 cursor-help"
                        >
                            {sourceId}
                        </button>
                    );
                }
            }
            return part;
        });
    };

    // Render message content with markdown-like formatting
    const renderContent = (content: string, sources?: Message['sources'], messageId?: number) => {
        const cleaned = cleanAnswer(content);
        let inExplorationPaths = false;

        return cleaned.split('\n').map((line, i) => {
            const trimmed = line.trim();

            // Detect Exploration Paths section
            if (trimmed.toLowerCase().includes('keşif önerileri') || trimmed.toLowerCase().includes('exploration paths')) {
                inExplorationPaths = true;
                return (
                    <h4 key={i} className="text-sm font-bold text-slate-800 dark:text-slate-200 mt-6 mb-3 flex items-center gap-2">
                        <Compass className="w-4 h-4 text-[#CC561E]" />
                        {trimmed}
                    </h4>
                );
            }

            if (trimmed.startsWith('## ') || (trimmed.startsWith('### ') && !inExplorationPaths)) {
                return (
                    <h3 key={i} className="text-base font-bold text-[#CC561E] dark:text-[#f3a47b] mt-5 mb-2">
                        {trimmed.replace(/^#+\s+/, '')}
                    </h3>
                );
            } else if (trimmed === '') {
                return <div key={i} className="h-2" />;
            } else if (inExplorationPaths && (trimmed.startsWith('-') || trimmed.startsWith('•') || /^\d+\./.test(trimmed))) {
                // Exploration path item - Interactive!
                const pathText = trimmed.replace(/^[-•\d.]+\s+/, '');
                return (
                    <div
                        key={i}
                        onClick={() => {
                            if (!isLoading) setInput(pathText);
                        }}
                        className="ml-2 mb-2 p-3 bg-white dark:bg-slate-800/50 border border-[#CC561E]/10 dark:border-[#CC561E]/20 rounded-xl shadow-sm hover:shadow-md hover:border-[#CC561E]/40 dark:hover:border-[#CC561E]/60 transition-all cursor-pointer group active:scale-[0.98]"
                    >
                        <p className="text-sm text-slate-700 dark:text-slate-200 flex items-center gap-3">
                            <span className="w-6 h-6 flex-shrink-0 bg-[#CC561E]/10 dark:bg-[#CC561E]/20 rounded-full flex items-center justify-center text-[10px] font-bold text-[#CC561E] group-hover:bg-[#CC561E] group-hover:text-white transition-colors">
                                {i - 10} {/* Arbitrary index-based number or just icon */}
                            </span>
                            {pathText}
                        </p>
                    </div>
                );
            } else {
                return (
                    <p key={i} className={`text-sm leading-relaxed mb-2 ${inExplorationPaths ? 'text-slate-500 dark:text-slate-400 italic' : 'text-slate-700 dark:text-slate-300'}`}>
                        {renderTextWithCitations(line, sources, messageId)}
                    </p>
                );
            }
        });
    };

    return (
        <div className="flex h-[calc(100vh-120px)] w-full gap-4">
            {/* Main Chat Area */}
            <div className="flex flex-col flex-1 min-w-0 bg-white dark:bg-slate-900 rounded-xl shadow-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-t-xl">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-[#CC561E]/10 dark:bg-[#CC561E]/20 rounded-lg">
                            <MessageCircle className="w-5 h-5 text-[#CC561E] dark:text-[#f3a47b]" />
                        </div>
                        <div>
                            <h2 className="font-semibold text-slate-900 dark:text-white">Explorer Mode</h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                {sessionId ? `Session #${sessionId} • ${messages.length} messages` : 'New conversation'}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <label className="inline-flex items-center gap-2 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800">
                            <input
                                type="checkbox"
                                checked={scopeMode === 'BOOK_FIRST'}
                                onChange={(e) => setScopeMode(e.target.checked ? 'BOOK_FIRST' : 'AUTO')}
                                className="w-3.5 h-3.5 rounded border-slate-300 text-[#CC561E] focus:ring-[#CC561E]/40"
                                aria-label="Bu kitapla sınırla"
                            />
                            Bu kitapla sınırla
                        </label>
                        <button
                            onClick={startNewConversation}
                            className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                            title="Start new conversation"
                        >
                            <RotateCcw className="w-4 h-4" />
                            New
                        </button>
                        {onBack && (
                            <button
                                onClick={onBack}
                                className="px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                            >
                                Back
                            </button>
                        )}
                    </div>
                </div>

                {/* Context Bar (Sticky, below header) */}
                <ContextBar state={conversationState} />

                {/* Messages Container */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50 dark:bg-slate-900">
                    {messages.length === 0 && !isLoading && (
                        <div className="flex flex-col items-center justify-center h-full text-center">
                            <div className="p-4 bg-[#CC561E]/10 dark:bg-[#CC561E]/20 rounded-full mb-4">
                                <BookOpen className="w-8 h-8 text-[#CC561E] dark:text-[#f3a47b]" />
                            </div>
                            <h3 className="text-lg font-medium text-slate-900 dark:text-white mb-2">
                                Explorer Mode
                            </h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md">
                                Ask deep, philosophical questions. I'll analyze your notes dialectically,
                                identify gaps, and expand with general knowledge when needed.
                            </p>
                            <div className="mt-6 space-y-2">
                                {[
                                    "What is the relationship between consciousness and reality?",
                                    "How do different philosophers define virtue?",
                                    "Analyze the concept of free will in my notes"
                                ].map((example, i) => (
                                    <button
                                        key={i}
                                        onClick={() => setInput(example)}
                                        className="block w-full text-left px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm text-slate-600 dark:text-slate-300 hover:bg-[#CC561E]/5 dark:hover:bg-[#CC561E]/10 transition-colors"
                                    >
                                        {example}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {messages.map((message) => (
                        <div
                            key={message.id}
                            className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            {message.role === 'assistant' && (
                                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#CC561E]/10 dark:bg-[#CC561E]/20 flex items-center justify-center">
                                    <Bot className="w-4 h-4 text-[#CC561E] dark:text-[#f3a47b]" />
                                </div>
                            )}

                            <div className={`max-w-[80%] ${message.role === 'user' ? 'order-first' : ''}`}>
                                {/* Thinking Process (for explorer mode) */}
                                {message.role === 'assistant' && message.thinkingHistory && message.thinkingHistory.length > 0 && (
                                    <div className="mb-2">
                                        <button
                                            onClick={() => toggleThinking(message.id)}
                                            className="flex items-center gap-2 text-[10px] uppercase font-bold tracking-wider text-slate-400 hover:text-[#CC561E] transition-colors"
                                        >
                                            <Brain className="w-3 h-3" />
                                            {expandedThinking.has(message.id) ? 'Hide Reflection' : 'Show Reflection'}
                                            <span className="opacity-50">• {message.thinkingHistory.length} Iterations</span>
                                        </button>

                                        {expandedThinking.has(message.id) && (
                                            <div className="mt-2 mb-3 space-y-3 bg-slate-100/50 dark:bg-slate-800/50 p-3 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 animate-fade-in">
                                                {message.thinkingHistory.map((step, idx) => (
                                                    <div key={idx} className="space-y-1">
                                                        <div className="flex items-center justify-between">
                                                            <div className="flex items-center gap-2">
                                                                <div className={`w-1.5 h-1.5 rounded-full ${step.evaluation.verdict === 'PASSED' ? 'bg-green-500' :
                                                                    step.evaluation.verdict === 'DECLINE' ? 'bg-red-500' : 'bg-amber-500'
                                                                    }`} />
                                                                <span className="text-[10px] font-bold text-slate-500">STEP {step.attempt}: {step.evaluation.verdict}</span>
                                                            </div>
                                                            <span className="text-[10px] text-slate-400 flex items-center gap-1">
                                                                <Gauge className="w-2.5 h-2.5" />
                                                                {(step.latency / 1000).toFixed(1)}s
                                                            </span>
                                                        </div>
                                                        <div className="h-1 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                                            <div
                                                                className={`h-full transition-all duration-1000 ${step.evaluation.overall_score > 0.7 ? 'bg-green-500' :
                                                                    step.evaluation.overall_score > 0.4 ? 'bg-amber-500' : 'bg-red-500'
                                                                    }`}
                                                                style={{ width: `${step.evaluation.overall_score * 100}%` }}
                                                            />
                                                        </div>
                                                        <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-snug">
                                                            {step.evaluation.explanation}
                                                        </p>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div
                                    className={`rounded-2xl px-4 py-3 ${message.role === 'user'
                                        ? 'bg-[#CC561E] text-white rounded-br-md shadow-lg shadow-[#CC561E]/20'
                                        : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-bl-md'
                                        }`}
                                >
                                    {message.role === 'user' ? (
                                        <p className="text-sm">{message.content}</p>
                                    ) : (
                                        <div className="prose prose-sm dark:prose-invert max-w-none">
                                            {renderContent(message.content, message.sources, message.id)}
                                        </div>
                                    )}
                                </div>

                                {/* Sources (for assistant messages) */}
                                {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
                                    <div className="mt-2">
                                        <button
                                            onClick={() => toggleSources(message.id)}
                                            className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 hover:text-[#CC561E] dark:hover:text-[#f3a47b] transition-colors"
                                        >
                                            {expandedSources.has(message.id) ? (
                                                <ChevronUp className="w-3 h-3" />
                                            ) : (
                                                <ChevronDown className="w-3 h-3" />
                                            )}
                                            {message.sources.length} sources
                                        </button>

                                        {expandedSources.has(message.id) && (
                                            <div className="mt-2 space-y-1 pl-2 border-l-2 border-[#CC561E]/30 dark:border-[#CC561E]/50">
                                                {message.sources.map((source, idx) => (
                                                    <div key={idx} className="text-xs text-slate-500 dark:text-slate-400 py-1 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800/50 rounded px-1">
                                                        <span className="inline-flex items-center justify-center w-4 h-4 mr-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-[9px] font-bold">
                                                            {source.id || (idx + 1)}
                                                        </span>
                                                        <span className="font-medium">{source.title}</span>
                                                        <span className="ml-2 text-slate-400 text-[10px]">
                                                            p.{source.page_number}
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {message.role === 'user' && (
                                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#CC561E] flex items-center justify-center">
                                    <User className="w-4 h-4 text-white" />
                                </div>
                            )}
                        </div>
                    ))}

                    {/* Source Preview Popover (Fixed position relative to viewport or parent) */}
                    {hoveredCitation && (
                        <div
                            className="fixed z-50 pointer-events-none"
                            style={{ left: hoveredCitation.x, top: hoveredCitation.y - 120 }}
                        >
                            <div className="w-64 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl p-4 animate-in fade-in zoom-in duration-200 origin-bottom">
                                {messages.find(m => m.id === hoveredCitation.messageId)?.sources?.find(s => s.id === hoveredCitation.id) ? (
                                    <>
                                        <div className="flex items-center gap-2 mb-2 text-[#CC561E]">
                                            <Quote className="w-3 h-3" />
                                            <span className="text-[10px] font-bold uppercase tracking-wider">Source Snippet</span>
                                        </div>
                                        <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed italic mb-3">
                                            "...{messages.find(m => m.id === hoveredCitation.messageId)?.sources?.find(s => s.id === hoveredCitation.id)?.content?.slice(0, 200)}..."
                                        </p>
                                        <div className="flex items-center justify-between border-t border-slate-100 dark:border-slate-700 pt-2 text-[10px] text-slate-400">
                                            <span className="font-medium truncate max-w-[120px]">
                                                {messages.find(m => m.id === hoveredCitation.messageId)?.sources?.find(s => s.id === hoveredCitation.id)?.title}
                                            </span>
                                            <span className="flex items-center gap-1">
                                                <ExternalLink className="w-2.5 h-2.5" />
                                                p.{messages.find(m => m.id === hoveredCitation.messageId)?.sources?.find(s => s.id === hoveredCitation.id)?.page_number}
                                            </span>
                                        </div>
                                    </>
                                ) : (
                                    <p className="text-xs text-slate-400">Loading source info...</p>
                                )}
                                {/* Little triangle arrow */}
                                <div className="absolute -bottom-1 left-4 w-2 h-2 bg-white dark:bg-slate-800 border-r border-b border-slate-200 dark:border-slate-700 rotate-45" />
                            </div>
                        </div>
                    )}

                    {/* Loading indicator */}
                    {isLoading && (
                        <div className="flex gap-3">
                            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#CC561E]/10 dark:bg-[#CC561E]/20 flex items-center justify-center">
                                <Bot className="w-4 h-4 text-[#CC561E] dark:text-[#f3a47b]" />
                            </div>
                            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl rounded-bl-md px-4 py-3">
                                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Analyzing deeply...
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Error message */}
                    {error && (
                        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
                            {error}
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <div className="p-4 border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-b-xl">
                    <div className="flex gap-3">
                        <input
                            ref={inputRef}
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyPress={handleKeyPress}
                            placeholder="Ask a deep question..."
                            disabled={isLoading}
                            className="flex-1 px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#CC561E] focus:border-transparent disabled:opacity-50"
                        />
                        <button
                            onClick={handleSend}
                            disabled={!input.trim() || isLoading}
                            className="px-4 py-3 bg-[#CC561E] hover:bg-[#b34b1a] disabled:bg-slate-300 dark:disabled:bg-slate-700 text-white rounded-xl transition-all shadow-lg shadow-[#CC561E]/20 flex items-center gap-2"
                        >
                            {isLoading ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Send className="w-5 h-5" />
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ExplorerChat;
