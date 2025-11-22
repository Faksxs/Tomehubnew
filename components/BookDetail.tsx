import React, { useState } from 'react';
import { LibraryItem, PhysicalStatus, ReadingStatus, Highlight } from '../types';
import { ArrowLeft, Edit2, Trash2, BookOpen, FileText, Globe, StickyNote, Sparkles, Hash, Calendar, Link as LinkIcon, PenTool, CheckCircle, Clock, Library, AlertTriangle, Archive } from 'lucide-react';
import { HighlightSection } from './HighlightSection';
import { analyzeHighlightsAI } from '../services/geminiService';

interface BookDetailProps {
  book: LibraryItem;
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onUpdateHighlights: (highlights: Highlight[]) => void;
}

export const BookDetail: React.FC<BookDetailProps> = React.memo(({ book, onBack, onEdit, onDelete, onUpdateHighlights }) => {
  const [activeTab, setActiveTab] = useState<'info' | 'highlights'>('info');
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const getReadingStatusConfig = (status: ReadingStatus) => {
    switch (status) {
      case 'Reading':
        return { icon: BookOpen, color: 'text-indigo-600', bg: 'bg-indigo-50', border: 'border-indigo-200' };
      case 'Finished':
        return { icon: CheckCircle, color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-200' };
      case 'To Read':
        return { icon: Clock, color: 'text-slate-500', bg: 'bg-slate-50', border: 'border-slate-200' };
      default:
        return { icon: BookOpen, color: 'text-slate-500', bg: 'bg-slate-50', border: 'border-slate-200' };
    }
  };

  const getPhysicalStatusConfig = (status: PhysicalStatus) => {
    switch (status) {
      case 'Lent Out':
        return { icon: AlertTriangle, color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200' };
      case 'Lost':
        return { icon: AlertTriangle, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' };
      case 'On Shelf':
      default:
        return { icon: Library, color: 'text-slate-600', bg: 'bg-slate-50', border: 'border-slate-200' };
    }
  }

  const handleAnalyze = async () => {
    if (book.highlights.length === 0) return;
    setIsAnalyzing(true);
    const texts = book.highlights.map(h => h.text);
    const summary = await analyzeHighlightsAI(texts);
    setAiSummary(summary);
    setIsAnalyzing(false);
  };

  const isNote = book.type === 'PERSONAL_NOTE';
  const readingConfig = !isNote ? getReadingStatusConfig(book.readingStatus) : null;
  const physicalConfig = !isNote ? getPhysicalStatusConfig(book.status) : null;

  // Helper to render status cards compactly
  const renderStatusCard = (config: any, label: string, value: string) => (
    <div className={`p-2 md:p-4 rounded-lg md:rounded-xl border-2 ${config.bg} ${config.border} flex items-center gap-2 md:gap-3 shadow-sm h-full`}>
      <div className={`p-1.5 md:p-2 rounded-full bg-white/50 ${config.color} flex-shrink-0`}>
        <config.icon size={16} className="md:w-5 md:h-5" />
      </div>
      <div className="min-w-0 flex-1">
        <span className={`block text-[9px] md:text-[10px] uppercase tracking-wider font-bold opacity-60 ${config.color} truncate`}>{label}</span>
        <span className={`font-bold text-xs md:text-base leading-tight ${config.color} truncate block`}>{value}</span>
      </div>
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto p-3 md:p-4 pb-20 animate-in fade-in duration-300">
      {/* Header Navigation */}
      <button onClick={onBack} className="mb-2 md:mb-6 flex items-center text-slate-500 hover:text-indigo-600 transition-colors group text-sm md:text-base">
        <ArrowLeft size={16} className="mr-1 md:mr-1 md:w-5 md:h-5 group-hover:-translate-x-1 transition-transform" />
        Back to {isNote ? 'Notes' : 'Library'}
      </button>

      <div className="bg-white rounded-xl md:rounded-2xl shadow-sm border border-slate-200 overflow-hidden">

        {/* Book Header Content */}
        <div className="p-4 md:p-8 border-b border-slate-100">
          {isNote ? (
            // --- SIMPLIFIED HEADER FOR NOTES ---
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 md:gap-3 mb-2 md:mb-4 text-indigo-500">
                  <PenTool size={18} className="md:w-6 md:h-6" />
                  <span className="text-xs md:text-sm font-bold tracking-wide uppercase text-indigo-500/80">Personal Note</span>
                </div>
                <h1 className="text-xl md:text-4xl font-bold text-slate-900 mb-2 md:mb-4 leading-tight">{book.title}</h1>

                {/* Tags */}
                <div className="flex flex-wrap gap-1.5 md:gap-2 mb-2">
                  {book.tags.map((tag, idx) => (
                    <span key={idx} className="px-1.5 py-0.5 md:px-2 md:py-1 bg-slate-50 text-slate-600 text-[10px] md:text-xs rounded border border-slate-100">
                      #{tag}
                    </span>
                  ))}
                  <span className="px-1.5 py-0.5 md:px-2 md:py-1 text-slate-400 text-[10px] md:text-xs flex items-center gap-1">
                    <Calendar size={10} className="md:w-3 md:h-3" />
                    {new Date(book.addedAt).toLocaleDateString()}
                  </span>
                </div>
              </div>
              <div className="flex gap-1 md:gap-2 ml-2 md:ml-4 flex-shrink-0">
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onEdit(); }}
                  className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-full transition-colors"
                  title="Edit Note"
                >
                  <Edit2 size={18} className="md:w-5 md:h-5" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-full transition-colors"
                  title="Delete Note"
                >
                  <Trash2 size={18} className="md:w-5 md:h-5" />
                </button>
              </div>
            </div>
          ) : (
            // --- STANDARD HEADER FOR LIBRARY ITEMS ---
            <div className="flex flex-col md:flex-row gap-4 md:gap-8">

              {/* Top Section (Mobile: Side-by-side Cover & Info | Desktop: Just Cover) */}
              <div className="flex gap-4 md:block md:shrink-0">
                {/* Cover Placeholder */}
                <div className="w-20 h-32 md:w-34 md:h-52 bg-slate-200 rounded-lg shadow-inner flex-shrink-0 flex items-center justify-center text-slate-400 self-center md:self-start overflow-hidden relative border border-slate-100">
                  {book.type === 'BOOK' && book.coverUrl ? (
                    <img src={book.coverUrl} alt={book.title} className="w-full h-full object-cover" />
                  ) : (
                    book.type === 'BOOK' ? <BookOpen size={32} className="md:w-12 md:h-12" /> :
                      book.type === 'ARTICLE' ? <FileText size={32} className="md:w-12 md:h-12" /> :
                        <Globe size={32} className="md:w-12 md:h-12" />
                  )}
                </div>

                {/* Mobile-Only Info Column (Right of Cover) */}
                <div className="md:hidden flex-1 flex flex-col justify-center min-w-0 py-1">
                  <h1 className="text-lg font-bold text-slate-900 mb-1 leading-snug line-clamp-3">{book.title}</h1>
                  <p className="text-sm text-slate-600 mb-2 line-clamp-2">{book.author}</p>
                  {book.url && book.type !== 'BOOK' && (
                    <a href={book.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-indigo-600 hover:underline max-w-full">
                      <LinkIcon size={12} />
                      <span className="text-xs truncate">{new URL(book.url).hostname}</span>
                    </a>
                  )}
                </div>
              </div>

              {/* Desktop-Only Info Column (Middle) */}
              <div className="hidden md:block flex-1 min-w-0">
                <h1 className="text-3xl md:text-4xl font-bold text-slate-900 mb-2 leading-tight">{book.title}</h1>
                <p className="text-xl text-slate-600 mb-4">{book.author}</p>

                {/* Tags */}
                <div className="flex flex-wrap gap-2 mb-6">
                  {book.tags.map((tag, idx) => (
                    <span key={idx} className="px-2 py-1 bg-slate-50 text-slate-600 text-xs rounded border border-slate-100">
                      #{tag}
                    </span>
                  ))}
                </div>

                {/* Links */}
                {book.url && book.type !== 'BOOK' && (
                  <div className="mb-6">
                    <a href={book.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-indigo-600 hover:underline">
                      <LinkIcon size={16} />
                      <span className="text-sm">{book.url}</span>
                    </a>
                  </div>
                )}
              </div>

              {/* Mobile-Only Tags Row (Below Cover/Info) */}
              <div className="md:hidden flex flex-wrap gap-1.5 -mt-1 mb-1">
                {book.tags.map((tag, idx) => (
                  <span key={idx} className="px-1.5 py-0.5 bg-slate-50 text-slate-600 text-[10px] rounded border border-slate-100">
                    #{tag}
                  </span>
                ))}
              </div>

              {/* Right Column: Status Boxes & Actions (Responsive) */}
              <div className="w-full md:w-64 flex-shrink-0 flex flex-col gap-2 md:gap-3">

                {/* Status Grid (2 cols on mobile, 1 col on desktop) */}
                <div className="grid grid-cols-2 md:flex md:flex-col gap-2 md:gap-3">
                  {/* Reading Status */}
                  {readingConfig && (
                    <div className={(!physicalConfig || book.type !== 'BOOK') ? "col-span-2 md:col-span-1" : "col-span-1"}>
                      {renderStatusCard(readingConfig, 'Status', book.readingStatus)}
                    </div>
                  )}

                  {/* Inventory Status - Books Only */}
                  {physicalConfig && book.type === 'BOOK' && (
                    <div className="col-span-1">
                      {renderStatusCard(physicalConfig, 'Inventory', book.status)}
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="grid grid-cols-2 gap-2 mt-1 md:mt-2">
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onEdit(); }}
                    className="flex items-center justify-center gap-2 px-3 py-2 md:px-4 bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 rounded-lg text-slate-600 transition-colors text-xs md:text-sm font-medium"
                  >
                    <Edit2 size={14} className="md:w-4 md:h-4" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onDelete(); }}
                    className="flex items-center justify-center gap-2 px-3 py-2 md:px-4 bg-white border border-slate-200 hover:border-red-300 hover:text-red-600 rounded-lg text-slate-600 transition-colors text-xs md:text-sm font-medium"
                  >
                    <Trash2 size={14} className="md:w-4 md:h-4" /> Delete
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Tabs - Hidden for Personal Notes */}
        {!isNote && (
          <div className="flex border-b border-slate-100">
            <button
              onClick={() => setActiveTab('info')}
              className={`flex-1 py-3 md:py-4 text-xs md:text-sm font-medium text-center border-b-2 transition-colors ${activeTab === 'info' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
            >
              Details & Notes
            </button>
            <button
              onClick={() => setActiveTab('highlights')}
              className={`flex-1 py-3 md:py-4 text-xs md:text-sm font-medium text-center border-b-2 transition-colors ${activeTab === 'highlights' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
            >
              Highlights ({book.highlights.length})
            </button>
          </div>
        )}

        {/* Tab Content */}
        <div className="p-4 md:p-8 bg-slate-50/50 min-h-[400px]">
          {(activeTab === 'info' || isNote) && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
              <div className={isNote ? "md:col-span-3" : "md:col-span-2 space-y-6"}>
                {/* General Notes / Content */}
                <div className={`bg-white p-4 md:p-6 rounded-xl border border-slate-100 shadow-sm ${isNote ? 'min-h-[300px]' : ''}`}>
                  {!isNote && (
                    <h3 className="text-base md:text-lg font-semibold text-slate-800 mb-3 md:mb-4 flex items-center gap-2">
                      <StickyNote size={18} className="text-indigo-500 md:w-5 md:h-5" />
                      General Notes
                    </h3>
                  )}
                  {book.generalNotes ? (
                    <p className="text-slate-600 whitespace-pre-wrap leading-relaxed text-sm md:text-lg">{book.generalNotes}</p>
                  ) : (
                    <p className="text-slate-400 italic text-sm">No content added.</p>
                  )}
                </div>
              </div>

              {!isNote && (
                <div className="space-y-4 md:space-y-6">
                  {/* Metadata Card */}
                  <div className="bg-white p-4 md:p-6 rounded-xl border border-slate-100 shadow-sm space-y-4">
                    <h3 className="text-xs md:text-sm font-semibold text-slate-900 uppercase tracking-wider mb-2 md:mb-4">Information</h3>

                    {(book.publisher) && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500">{book.type === 'ARTICLE' ? 'Journal' : 'Publisher'}</span>
                        <span className="text-sm font-medium text-slate-800">{book.publisher}</span>
                      </div>
                    )}

                    {book.publicationYear && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500">Year</span>
                        <span className="text-sm font-medium text-slate-800">{book.publicationYear}</span>
                      </div>
                    )}

                    {book.translator && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500">Translator</span>
                        <span className="text-sm font-medium text-slate-800">{book.translator}</span>
                      </div>
                    )}

                    {book.isbn && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500">ISBN</span>
                        <span className="text-sm font-medium text-slate-800 font-mono">{book.isbn}</span>
                      </div>
                    )}

                    {book.code && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500">Shelf Code</span>
                        <div className="flex items-center gap-2">
                          <Hash size={12} className="text-slate-400 md:w-3.5 md:h-3.5" />
                          <span className="text-sm font-medium text-slate-800">{book.code}</span>
                        </div>
                      </div>
                    )}

                    <div className="flex flex-col gap-0.5 md:gap-1">
                      <span className="text-[10px] md:text-xs text-slate-500">Added</span>
                      <div className="flex items-center gap-2">
                        <Calendar size={12} className="text-slate-400 md:w-3.5 md:h-3.5" />
                        <span className="text-sm font-medium text-slate-800">
                          {new Date(book.addedAt).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {!isNote && activeTab === 'highlights' && (
            <div className="space-y-6">
              {book.highlights.length > 0 && (
                <div className="flex justify-end">
                  <button
                    onClick={handleAnalyze}
                    disabled={isAnalyzing}
                    className="text-xs md:text-sm text-indigo-600 hover:text-indigo-800 flex items-center gap-2 disabled:opacity-50"
                  >
                    <Sparkles size={14} className="md:w-4 md:h-4" />
                    {isAnalyzing ? 'Analyzing...' : 'Analyze Highlights with AI'}
                  </button>
                </div>
              )}

              {aiSummary && (
                <div className="bg-indigo-50 border border-indigo-100 p-3 md:p-4 rounded-lg mb-4 animate-in fade-in slide-in-from-top-2">
                  <h4 className="text-indigo-800 font-semibold text-xs md:text-sm mb-2 flex items-center gap-2">
                    <Sparkles size={14} /> AI Analysis
                  </h4>
                  <p className="text-indigo-900 text-xs md:text-sm leading-relaxed italic">
                    "{aiSummary}"
                  </p>
                </div>
              )}

              <HighlightSection
                highlights={book.highlights}
                onUpdate={onUpdateHighlights}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
});