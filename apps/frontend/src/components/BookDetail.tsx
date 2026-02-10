import React, { useState } from 'react';
import { LibraryItem, PhysicalStatus, ReadingStatus, Highlight } from '../types';
import { ArrowLeft, Edit2, Trash2, BookOpen, FileText, Globe, StickyNote, Sparkles, Hash, Calendar, Link as LinkIcon, PenTool, CheckCircle, Clock, Library, AlertTriangle, Archive, Upload, Loader2, AlertCircle, FilePlus } from 'lucide-react';
import { HighlightSection } from './HighlightSection';
import { analyzeHighlightsAI, enrichBookWithAI, libraryItemToDraft, mergeEnrichedDraftIntoItem } from '../services/geminiService';
import { useAuth } from '../contexts/AuthContext';
import { getIngestionStatus, ingestDocument, IngestResponse, IngestionStatusResponse } from '../services/backendApiService';
import { saveItemForUser } from '../services/firestoreService';
import { getPersonalNoteCategory } from '../lib/personalNotePolicy';
import { toPersonalNotePreviewHtml } from '../lib/personalNoteRender';

interface BookDetailProps {
  book: LibraryItem;
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onUpdateHighlights: (highlights: Highlight[]) => void;
  initialTab?: 'info' | 'highlights'; // Optional prop to set initial tab
  autoEditHighlightId?: string; // Optional: highlight ID to auto-edit
  onIngestSuccess?: () => void;
  onBookUpdated?: (book: LibraryItem) => void;
}

export const BookDetail: React.FC<BookDetailProps> = React.memo(({ book, onBack, onEdit, onDelete, onUpdateHighlights, initialTab = 'info', autoEditHighlightId, onBookUpdated }) => {
  const [activeTab, setActiveTab] = useState<'info' | 'highlights'>(initialTab);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [enrichError, setEnrichError] = useState<string | null>(null);
  const [ingestResult, setIngestResult] = useState<IngestResponse | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [pdfStatus, setPdfStatus] = useState<IngestionStatusResponse | null>(null);
  const [pdfStatusError, setPdfStatusError] = useState<string | null>(null);
  const [pdfStatusRefresh, setPdfStatusRefresh] = useState(0);

  const { user } = useAuth();
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const isNote = book.type === 'PERSONAL_NOTE';

  // Helper for Turkish character normalization only
  const normalize = (str: any) => {
    if (!str || typeof str !== 'string') return '';
    return str
      .toLowerCase()
      .replace(/ı/g, 'i')
      .replace(/İ/g, 'i')
      .replace(/ğ/g, 'g')
      .replace(/Ğ/g, 'g')
      .replace(/ü/g, 'u')
      .replace(/Ü/g, 'u')
      .replace(/ş/g, 's')
      .replace(/Ş/g, 's')
      .replace(/ö/g, 'o')
      .replace(/Ö/g, 'o')
      .replace(/ç/g, 'c')
      .replace(/Ç/g, 'c')
      .trim();
  };



  const formatPdfName = (name?: string | null) => {
    if (!name) return '';
    const cleaned = name.replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
    const maxLen = 24;
    if (cleaned.length <= maxLen) return cleaned;
    return `${cleaned.slice(0, maxLen).trimEnd()}...`;
  };

  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !user) return;

    if (file.type !== 'application/pdf') {
      setIngestError('Please select a PDF file');
      return;
    }

    setIsIngesting(true);
    setIngestError(null);
    setIngestResult(null);
    setPdfStatus({
      status: 'PROCESSING',
      file_name: file.name,
      chunk_count: null,
      embedding_count: null,
      updated_at: new Date().toISOString()
    });
    setPdfStatusRefresh((v) => v + 1);

    try {
      const response = await ingestDocument(file, book.title, book.author, user.uid, book.id);
      setIngestResult(response);
      // Optional: Clear success message after some time
      setTimeout(() => setIngestResult(null), 5000);
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : 'Ingestion failed');
    } finally {
      setIsIngesting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const getReadingStatusConfig = (status: ReadingStatus) => {
    switch (status) {
      case 'Reading': return { icon: BookOpen, color: 'text-[#38BDF8]', bg: 'bg-[#38BDF8]/12', border: 'border-[#38BDF8]/45' };
      case 'Finished': return { icon: CheckCircle, color: 'text-[#22C55E]', bg: 'bg-[#22C55E]/12', border: 'border-[#22C55E]/45' };
      case 'To Read': return { icon: Clock, color: 'text-[#94A3B8]', bg: 'bg-[#94A3B8]/12', border: 'border-[#94A3B8]/40' };
      default: return { icon: BookOpen, color: 'text-[#94A3B8]', bg: 'bg-[#94A3B8]/12', border: 'border-[#94A3B8]/40' };
    }
  };

  const getPhysicalStatusConfig = (status: PhysicalStatus) => {
    switch (status) {
      case 'Lent Out': return { icon: AlertTriangle, color: 'text-[#F59E0B]', bg: 'bg-[#F59E0B]/15', border: 'border-[#F59E0B]/45' };
      case 'Lost': return { icon: AlertTriangle, color: 'text-[#F43F5E]', bg: 'bg-[#F43F5E]/15', border: 'border-[#F43F5E]/45' };
      case 'On Shelf':
      default:
        return { icon: Library, color: 'text-[#14B8A6]', bg: 'bg-[#14B8A6]/15', border: 'border-[#14B8A6]/45' };
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

  const handleGenerateSummaryAndTags = async () => {
    if (!user?.uid || isEnriching) return;
    setIsEnriching(true);
    setEnrichError(null);
    try {
      const draft = libraryItemToDraft(book);
      const enriched = await enrichBookWithAI(draft);
      const mergedItem = mergeEnrichedDraftIntoItem(book, enriched);

      await saveItemForUser(user.uid, mergedItem);
      onBookUpdated?.(mergedItem);
      if (mergedItem.generalNotes) setAiSummary(mergedItem.generalNotes);
    } catch (e) {
      console.error("Enrich failed", e);
      setEnrichError(e instanceof Error ? e.message : 'Failed to generate with AI');
    } finally {
      setIsEnriching(false);
    }
  };

  const readingConfig = !isNote ? getReadingStatusConfig(book.readingStatus) : null;
  const physicalConfig = !isNote ? getPhysicalStatusConfig(book.status) : null;
  const pdfIndexed = pdfStatus?.status === 'COMPLETED';
  const pdfProcessing = pdfStatus?.status === 'PROCESSING';
  const pdfFailed = pdfStatus?.status === 'FAILED';
  const pdfDisableUpload = pdfIndexed || pdfProcessing || isIngesting;

  React.useEffect(() => {
    if (!user?.uid || !book?.id || isNote) {
      setPdfStatus(null);
      setPdfStatusError(null);
      return;
    }

    let cancelled = false;
    let attempts = 0;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const fetchStatus = async () => {
      try {
        const status = await getIngestionStatus(book.id, user.uid);
        if (cancelled) return;
        setPdfStatus(status);
        setPdfStatusError(null);
        if (status.status === 'COMPLETED' && !book.isIngested) {
          const updated = { ...book, isIngested: true };
          await saveItemForUser(user.uid, updated);
          onBookUpdated?.(updated);
        }
        if (status.status === 'PROCESSING' && attempts < 30) {
          attempts += 1;
          timeoutId = setTimeout(fetchStatus, 10000);
        }
      } catch (e) {
        if (cancelled) return;
        setPdfStatusError(e instanceof Error ? e.message : 'Failed to fetch ingestion status');
      }
    };

    fetchStatus();

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [book.id, user?.uid, isNote, pdfStatusRefresh]);

  // Helper to render status cards compactly
  const renderStatusCard = (config: any, label: string, value: string) => (
    <div className={`p-2 md:p-4 rounded-lg md:rounded-xl border-2 ${config.bg} ${config.border} flex items-center gap-2 md:gap-3 shadow-sm h-full`}>
      <div className={`p-1.5 md:p-2 rounded-full bg-white/50 dark:bg-black/20 ${config.color} flex-shrink-0`}>
        <config.icon size={16} className="md:w-5 md:h-5" />
      </div>
      <div className="min-w-0 flex-1">
        <span className="block text-[9px] md:text-[10px] uppercase tracking-wider font-bold text-[#111827] dark:text-white/60 truncate">{label}</span>
        <span className="font-bold text-xs md:text-base leading-tight text-[#111827] dark:text-white truncate block">{value}</span>
      </div>
    </div>
  );

  return (
    <div className="max-w-[1100px] w-full mx-auto p-3 md:p-4 pb-20 animate-in fade-in duration-300">
      {/* Header Navigation */}
      <button onClick={onBack} className="mb-2 md:mb-6 flex items-center text-slate-500 dark:text-slate-400 hover:text-[#262D40] dark:hover:text-white transition-colors group text-base md:text-base">
        <ArrowLeft size={18} className="mr-1.5 md:mr-1 md:w-5 md:h-5 group-hover:-translate-x-1 transition-transform" />
        Back to {isNote ? 'Notes' : 'Library'}
      </button>

      <div className="bg-white dark:bg-slate-900 rounded-xl md:rounded-2xl shadow-sm border border-[#E6EAF2] dark:border-slate-800 overflow-hidden">

        {/* Book Header Content */}
        <div className="p-4 md:p-8 border-b border-[#E6EAF2] dark:border-slate-800">
          {isNote ? (
            // --- SIMPLIFIED HEADER FOR NOTES ---
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 md:gap-3 mb-2 md:mb-4 text-[#262D40]/90 dark:text-white/85">
                  <PenTool size={18} className="md:w-6 md:h-6" />
                  <span className="text-xs md:text-sm font-bold tracking-wide uppercase text-[#262D40]/80 dark:text-white">Personal Note</span>
                  <span className="px-2 py-0.5 rounded-md bg-[#CC561E]/10 text-[#CC561E] text-[10px] md:text-xs font-bold tracking-wide">
                    {getPersonalNoteCategory(book)}
                  </span>
                  {book.folderPath && (
                    <span className="px-2 py-0.5 rounded-md bg-[#F3F5FA] dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[10px] md:text-xs border border-[#E6EAF2] dark:border-slate-700">
                      {book.folderPath}
                    </span>
                  )}
                </div>
                <h1 className="text-xl md:text-4xl font-bold text-slate-900 dark:text-white mb-2 md:mb-4 leading-tight">{book.title}</h1>

                {/* Tags */}
                <div className="flex flex-wrap gap-1.5 md:gap-2 mb-2">
                  {/* Badge removed as per user request */}
                  {book.tags.map((tag, idx) => (
                    <span key={idx} className="px-1.5 py-0.5 md:px-2 md:py-1 bg-[#F3F5FA] dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[10px] md:text-xs rounded border border-[#E6EAF2] dark:border-slate-700">
                      #{tag}
                    </span>
                  ))}
                  <span className="px-1.5 py-0.5 md:px-2 md:py-1 text-slate-400 dark:text-slate-500 text-[10px] md:text-xs flex items-center gap-1">
                    <Calendar size={10} className="md:w-3 md:h-3" />
                    {new Date(book.addedAt).toLocaleDateString()}
                  </span>
                </div>
              </div>
              <div className="flex gap-1 md:gap-2 ml-2 md:ml-4 flex-shrink-0">
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept=".pdf"
                  onChange={handlePdfUpload}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={pdfDisableUpload}
                  className="p-2 text-slate-400 dark:text-slate-500 hover:text-[#262D40] dark:hover:text-[#262D40]/82 hover:bg-[#262D40]/5 dark:hover:bg-[#262D40]/30 rounded-full transition-colors relative"
                  title={pdfIndexed ? `PDF already indexed: ${pdfStatus?.file_name || ''}` : "Upload PDF"}
                >
                  {isIngesting ? <Loader2 size={18} className="md:w-5 md:h-5 animate-spin text-[#262D40]/90" /> : <Upload size={18} className="md:w-5 md:h-5" />}
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onEdit(); }}
                  className="p-2 text-slate-400 dark:text-slate-500 hover:text-[#262D40] dark:hover:text-[#262D40]/82 hover:bg-[#262D40]/5 dark:hover:bg-[#262D40]/30 rounded-full transition-colors"
                  title="Edit Note"
                >
                  <Edit2 size={18} className="md:w-5 md:h-5" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  className="p-2 text-slate-400 dark:text-slate-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-full transition-colors"
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
                <div className="w-20 h-32 md:w-34 md:h-52 bg-slate-200 dark:bg-slate-800 rounded-lg shadow-inner flex-shrink-0 flex items-center justify-center text-slate-400 dark:text-slate-600 self-center md:self-start overflow-hidden relative border border-[#E6EAF2] dark:border-slate-700">
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
                  <h1 className="text-lg font-bold text-slate-900 dark:text-white mb-1 leading-snug line-clamp-3">{book.title}</h1>
                  <p className="text-sm text-slate-600 dark:text-slate-400 mb-2 line-clamp-2">{book.author}</p>
                  {book.url && book.type !== 'BOOK' && (
                    <a href={book.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-[#262D40] dark:text-[#262D40]/82 hover:underline max-w-full">
                      <LinkIcon size={12} />
                      <span className="text-xs truncate">{new URL(book.url).hostname}</span>
                    </a>
                  )}
                </div>
              </div>

              {/* Desktop-Only Info Column (Middle) */}
              <div className="hidden md:block flex-1 min-w-0">
                <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-2 leading-tight">{book.title}</h1>
                <p className="text-xl text-slate-600 dark:text-slate-400 mb-4">{book.author}</p>

                {/* Tags */}
                <div className="flex flex-wrap gap-2 mb-6">
                  {book.tags.map((tag, idx) => (
                    <span key={idx} className="px-2 py-1 bg-[#F3F5FA] dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs rounded border border-[#E6EAF2] dark:border-slate-700">
                      #{tag}
                    </span>
                  ))}
                </div>

                {/* Links */}
                {book.url && book.type !== 'BOOK' && (
                  <div className="mb-6">
                    <a href={book.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-[#262D40] dark:text-[#262D40]/82 hover:underline">
                      <LinkIcon size={16} />
                      <span className="text-sm">{book.url}</span>
                    </a>
                  </div>
                )}
              </div>

              {/* Mobile-Only Tags Row (Below Cover/Info) */}
              <div className="md:hidden flex flex-wrap gap-1.5 -mt-1 mb-1">
                {book.tags.map((tag, idx) => (
                  <span key={idx} className="px-1.5 py-0.5 bg-[#F3F5FA] dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-[10px] rounded border border-[#E6EAF2] dark:border-slate-700">
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
                <div className="grid grid-cols-3 gap-2 mt-1 md:mt-2">
                  <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    accept=".pdf"
                    onChange={handlePdfUpload}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={pdfDisableUpload}
                    className="flex items-center justify-center gap-2 px-2 py-2 bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-700 hover:border-[#262D40]/18 dark:hover:border-[#262D40]/30 hover:text-[#262D40] dark:hover:text-[#262D40]/82 rounded-lg text-slate-600 dark:text-slate-400 transition-colors text-xs font-medium disabled:opacity-50"
                    title={pdfIndexed ? `PDF already indexed: ${pdfStatus?.file_name || ''}` : "Upload PDF"}
                  >
                    {isIngesting ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                    <span className="hidden lg:inline">PDF</span>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onEdit(); }}
                    className="flex items-center justify-center gap-2 px-2 py-2 bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-700 hover:border-[#262D40]/18 dark:hover:border-[#262D40]/30 hover:text-[#262D40] dark:hover:text-[#262D40]/82 rounded-lg text-slate-600 dark:text-slate-400 transition-colors text-xs font-medium"
                  >
                    <Edit2 size={14} /> <span className="hidden lg:inline">Edit</span>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onDelete(); }}
                    className="flex items-center justify-center gap-2 px-2 py-2 bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-700 hover:border-red-300 dark:hover:border-red-500 hover:text-red-600 dark:hover:text-red-400 rounded-lg text-slate-600 dark:text-slate-400 transition-colors text-xs font-medium"
                  >
                    <Trash2 size={14} /> <span className="hidden lg:inline">Delete</span>
                  </button>
                </div>

                {/* Status Messages */}
                {ingestResult && (
                  <div className="mt-2 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1 animate-in fade-in slide-in-from-top-1">
                    <CheckCircle size={10} /> PDF Ingested!
                  </div>
                )}
                {ingestError && (
                  <div className="mt-2 text-[10px] text-red-600 dark:text-red-400 font-medium flex items-center gap-1 animate-in fade-in slide-in-from-top-1">
                    <AlertCircle size={10} /> {ingestError}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Tabs - Hidden for Personal Notes */}
        {!isNote && (
          <div className="flex border-b border-[#E6EAF2] dark:border-slate-800">
            <button
              onClick={() => setActiveTab('info')}
              className={`flex-1 py-3 md:py-4 text-xs md:text-sm font-medium text-center border-b-2 transition-colors ${activeTab === 'info' ? 'border-[#262D40] dark:border-white text-[#262D40] dark:text-white' : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
            >
              Details
            </button>
            <button
              onClick={() => setActiveTab('highlights')}
              className={`flex-1 py-3 md:py-4 text-xs md:text-sm font-medium text-center border-b-2 transition-colors ${activeTab === 'highlights' ? 'border-[#262D40] dark:border-white text-[#262D40] dark:text-white' : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
            >
              Highlights ({book.highlights.length})
            </button>
          </div>
        )}

        {/* Tab Content */}
        <div className="p-4 md:p-8 bg-[#F7F8FB] dark:bg-slate-900/50 min-h-[400px]">
          {(activeTab === 'info' || isNote) && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
              <div className={isNote ? "md:col-span-3" : "md:col-span-2 space-y-6"}>
                {/* Summary / Content */}
                <div className={`bg-white dark:bg-slate-900 p-4 md:p-6 rounded-xl border border-[#E6EAF2] dark:border-slate-800 shadow-sm ${isNote ? 'min-h-[300px]' : ''}`}>
                  {!isNote && (
                    <div className="flex items-start justify-between gap-3 mb-3 md:mb-4">
                      <div className="flex items-center gap-2">
                        <StickyNote size={18} className="text-[#262D40]/90 dark:text-[#262D40]/82 md:w-5 md:h-5" />
                        <h3 className="text-base md:text-lg font-semibold text-slate-800 dark:text-slate-200">Summary</h3>
                      </div>
                      <button
                        type="button"
                        onClick={handleGenerateSummaryAndTags}
                        disabled={isEnriching}
                        className="flex items-center gap-1.5 text-[11px] md:text-xs font-semibold text-white px-2 py-1 rounded-lg border border-[#262D40] bg-[#262D40] hover:bg-[#1d2333] disabled:opacity-60"
                      >
                        {isEnriching ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                        {isEnriching ? 'Generating...' : 'Generate with AI'}
                      </button>
                    </div>
                  )}
                  {book.generalNotes ? (
                    isNote ? (
                      <div
                        className="personal-note-render text-slate-700 dark:text-slate-300 leading-relaxed text-sm md:text-base max-w-none"
                        dangerouslySetInnerHTML={{ __html: toPersonalNotePreviewHtml(book.generalNotes) }}
                      />
                    ) : (
                      <p className="text-slate-600 dark:text-slate-300 whitespace-pre-wrap leading-relaxed text-sm md:text-lg">{book.generalNotes}</p>
                    )
                  ) : (
                    <p className="text-slate-400 dark:text-slate-500 italic text-sm">No content added.</p>
                  )}
                  {enrichError && (
                    <p className="text-xs text-red-600 dark:text-red-400 mt-2 flex items-center gap-1">
                      <AlertCircle size={12} /> {enrichError}
                    </p>
                  )}
                </div>
              </div>

              {!isNote && (
                <div className="space-y-4 md:space-y-6">
                  {/* Metadata Card */}
                  <div className="bg-white dark:bg-slate-900 p-4 md:p-6 rounded-xl border border-[#E6EAF2] dark:border-slate-800 shadow-sm space-y-4">
                    <h3 className="text-xs md:text-sm font-semibold text-slate-900 dark:text-white uppercase tracking-wider mb-2 md:mb-4">Information</h3>

                    {(book.publisher) && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">{book.type === 'ARTICLE' ? 'Journal' : 'Publisher'}</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{book.publisher}</span>
                      </div>
                    )}

                    {book.publicationYear && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">Year</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{book.publicationYear}</span>
                      </div>
                    )}

                    {book.translator && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">Translator</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{book.translator}</span>
                      </div>
                    )}

                    {book.isbn && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">ISBN</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200 font-mono">{book.isbn}</span>
                      </div>
                    )}

                    {book.pageCount && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">Page Count</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{book.pageCount} pages</span>
                      </div>
                    )}

                    {pdfStatus && pdfStatus.status !== 'NOT_FOUND' && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">PDF</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
                          {pdfProcessing && "Processing..."}
                          {pdfFailed && "Failed - please re-upload"}
                          {pdfIndexed && (
                            <>
                              {pdfStatus.file_name ? (
                                <span title={pdfStatus.file_name}>
                                  {`Indexed: ${formatPdfName(pdfStatus.file_name)}`}
                                </span>
                              ) : (
                                "Indexed"
                              )}
                              {pdfStatus.chunk_count !== null ? ` (${pdfStatus.chunk_count} chunks)` : ""}
                            </>
                          )}
                        </span>
                        {pdfStatusError && (
                          <span className="text-[10px] md:text-xs text-red-600 dark:text-red-400">{pdfStatusError}</span>
                        )}
                      </div>
                    )}

                    {book.code && (
                      <div className="flex flex-col gap-0.5 md:gap-1">
                        <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">Shelf Code</span>
                        <div className="flex items-center gap-2">
                          <Hash size={12} className="text-slate-400 dark:text-slate-500 md:w-3.5 md:h-3.5" />
                          <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{book.code}</span>
                        </div>
                      </div>
                    )}





                    <div className="flex flex-col gap-0.5 md:gap-1">
                      <span className="text-[10px] md:text-xs text-slate-500 dark:text-slate-400">Added</span>
                      <div className="flex items-center gap-2">
                        <Calendar size={12} className="text-slate-400 dark:text-slate-500 md:w-3.5 md:h-3.5" />
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
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
                    className="text-xs md:text-sm text-[#262D40] dark:text-[#262D40]/82 hover:text-[#262D40] dark:hover:text-[#262D40]/78 flex items-center gap-2 disabled:opacity-50"
                  >
                    <Sparkles size={14} className="md:w-4 md:h-4" />
                    {isAnalyzing ? 'Analyzing...' : 'Analyze Highlights with AI'}
                  </button>
                </div>
              )}

              {aiSummary && (
                <div className="bg-[#262D40]/5 dark:bg-[#262D40]/20 border border-[#262D40]/8 dark:border-[#262D40]/70 p-3 md:p-4 rounded-lg mb-4 animate-in fade-in slide-in-from-top-2">
                  <h4 className="text-[#262D40] dark:text-[#262D40]/78 font-semibold text-xs md:text-sm mb-2 flex items-center gap-2">
                    <Sparkles size={14} /> AI Analysis
                  </h4>
                  <p className="text-[#262D40] dark:text-[#262D40]/75 text-xs md:text-sm leading-relaxed italic">
                    "{aiSummary}"
                  </p>
                </div>
              )}

              <HighlightSection
                highlights={book.highlights}
                onUpdate={onUpdateHighlights}
                autoEditHighlightId={autoEditHighlightId}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
