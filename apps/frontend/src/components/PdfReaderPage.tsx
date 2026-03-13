import React from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Clipboard,
  Download,
  ExternalLink,
  FileText,
  Hash,
  Loader2,
  MessageSquare,
  RefreshCcw,
  StickyNote,
  Tag,
  X,
} from 'lucide-react';
import { API_BASE_URL, getFirebaseIdToken } from '../services/apiClient';
import {
  getBookPdfMetadata,
  readPdfReaderLaunchContext,
  syncHighlights,
  syncPersonalNote,
  type PdfMetadataResponse,
} from '../services/backendApiService';
import { fetchItemsForUser, saveItemForUser } from '../services/oracleLibraryService';
import { useAuth } from '../contexts/AuthContext';
import { useUiFeedback } from '../shared/ui/feedback/useUiFeedback';
import { appendRecognizedText } from '../lib/ocrHelpers';
import { findPersonalNoteTemplate } from '../lib/personalNoteTemplates';
import {
  buildBookNoteHtml,
  buildCaptureHighlight,
  buildPersonalNoteItem,
  captureDraftTagsToList,
  createEmptyReaderCaptureDraft,
  mergeCaptureTags,
  type ReaderCaptureDraft,
} from '../lib/pdfReaderCapture';
import type { Highlight } from '../types';

const formatBytes = (value?: number | null) => {
  if (!value || value <= 0) return null;
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 100 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
};

const stripPdfExtension = (value: string) => String(value || '').replace(/\.pdf$/i, '').trim();
const MAX_HIGHLIGHT_TEXT_LENGTH = 6000;
const MAX_HIGHLIGHT_COMMENT_LENGTH = 2000;
const MAX_NOTE_TITLE_LENGTH = 220;

const isIosMobileDevice = () => {
  if (typeof navigator === 'undefined') return false;
  const userAgent = navigator.userAgent || '';
  const platform = navigator.platform || '';
  const maxTouchPoints = navigator.maxTouchPoints || 0;
  return /iPad|iPhone|iPod/i.test(userAgent)
    || (platform === 'MacIntel' && maxTouchPoints > 1);
};

type ReaderUiSessionState = {
  captureOpen: boolean;
  captureDraft: ReaderCaptureDraft;
  lastUsedPageNumber: string;
};

const buildReaderUiSessionKey = (sourceBookId: string) =>
  `tomehub:pdf-reader-ui:${sourceBookId}`;

const readReaderUiSession = (sourceBookId: string): ReaderUiSessionState | null => {
  if (!sourceBookId || typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(buildReaderUiSessionKey(sourceBookId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ReaderUiSessionState> | null;
    if (!parsed || typeof parsed !== 'object') return null;
    return {
      captureOpen: Boolean(parsed.captureOpen),
      captureDraft: parsed.captureDraft
        ? {
          text: String(parsed.captureDraft.text || ''),
          pageNumber: String(parsed.captureDraft.pageNumber || ''),
          comment: String(parsed.captureDraft.comment || ''),
          tags: String(parsed.captureDraft.tags || ''),
        }
        : createEmptyReaderCaptureDraft(''),
      lastUsedPageNumber: String(parsed.lastUsedPageNumber || ''),
    };
  } catch (error) {
    console.warn('Failed to read PDF reader UI session:', error);
    return null;
  }
};

const writeReaderUiSession = (sourceBookId: string, state: ReaderUiSessionState) => {
  if (!sourceBookId || typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(buildReaderUiSessionKey(sourceBookId), JSON.stringify(state));
  } catch (error) {
    console.warn('Failed to persist PDF reader UI session:', error);
  }
};

export const PdfReaderPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { bookId = '' } = useParams();
  const { user } = useAuth();
  const { showToast } = useUiFeedback();
  const uiSession = React.useMemo(() => readReaderUiSession(bookId), [bookId]);

  const [metadata, setMetadata] = React.useState<PdfMetadataResponse | null>(null);
  const [pdfUrl, setPdfUrl] = React.useState<string>('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [reloadKey, setReloadKey] = React.useState(0);
  const [captureOpen, setCaptureOpen] = React.useState(Boolean(uiSession?.captureOpen));
  const [captureDraft, setCaptureDraft] = React.useState<ReaderCaptureDraft>(() => (
    uiSession?.captureDraft ?? createEmptyReaderCaptureDraft('')
  ));
  const [captureError, setCaptureError] = React.useState<string | null>(null);
  const [lastUsedPageNumber, setLastUsedPageNumber] = React.useState(uiSession?.lastUsedPageNumber || '');
  const [submittingAction, setSubmittingAction] = React.useState<'highlight' | 'note' | null>(null);
  const [sourceHighlights, setSourceHighlights] = React.useState<Highlight[]>([]);
  const [isIosMobile] = React.useState(() => isIosMobileDevice());

  const requestedTitle = React.useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('title') || '';
  }, [location.search]);

  const sourceBookId = React.useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('sourceBookId') || bookId;
  }, [bookId, location.search]);

  const sourceTitleFromUrl = React.useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('sourceTitle') || '';
  }, [location.search]);

  const sourceAuthorFromUrl = React.useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('sourceAuthor') || '';
  }, [location.search]);

  const persistedContext = React.useMemo(
    () => readPdfReaderLaunchContext(sourceBookId),
    [sourceBookId],
  );

  const displayBookTitle = React.useMemo(
    () => sourceTitleFromUrl || persistedContext?.sourceTitle || requestedTitle || stripPdfExtension(metadata?.file_name || ''),
    [metadata?.file_name, persistedContext?.sourceTitle, requestedTitle, sourceTitleFromUrl],
  );

  React.useEffect(() => {
    setSourceHighlights(Array.isArray(persistedContext?.sourceHighlights) ? persistedContext.sourceHighlights : []);
  }, [persistedContext]);

  React.useEffect(() => {
    writeReaderUiSession(bookId, {
      captureOpen,
      captureDraft,
      lastUsedPageNumber,
    });
  }, [bookId, captureDraft, captureOpen, lastUsedPageNumber]);

  React.useEffect(() => {
    if (!bookId || !user?.uid) return;

    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [meta, token] = await Promise.all([
          getBookPdfMetadata(bookId, user.uid, requestedTitle),
          getFirebaseIdToken(),
        ]);
        if (cancelled) return;

        const resolvedBookId = meta?.book_id || bookId;
        const url = new URL(`${API_BASE_URL}/api/books/${encodeURIComponent(resolvedBookId)}/pdf/content`);
        url.searchParams.set('auth_token', token);
        url.searchParams.set('inline', '1');
        if (requestedTitle) {
          url.searchParams.set('title', requestedTitle);
        }

        setMetadata(meta);
        setPdfUrl(url.toString());
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'PDF could not be loaded');
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [bookId, user?.uid, reloadKey, requestedTitle]);

  const handleOpenNative = () => {
    if (!pdfUrl) return;
    window.open(pdfUrl, '_blank', 'noopener,noreferrer');
  };

  const handleDownload = () => {
    if (!pdfUrl) return;
    const anchor = document.createElement('a');
    anchor.href = pdfUrl;
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    anchor.download = metadata?.file_name || `${bookId}.pdf`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  const resetCaptureDraft = React.useCallback((pageNumber = lastUsedPageNumber) => {
    setCaptureDraft(createEmptyReaderCaptureDraft(pageNumber));
    setCaptureError(null);
  }, [lastUsedPageNumber]);

  const openCapturePanel = React.useCallback(() => {
    setCaptureOpen(true);
    setCaptureError(null);
    setCaptureDraft((current) => {
      if (current.text || current.comment || current.tags) {
        return current;
      }
      return createEmptyReaderCaptureDraft(lastUsedPageNumber);
    });
  }, [lastUsedPageNumber]);

  const handlePasteFromClipboard = async () => {
    setCaptureError(null);
    openCapturePanel();

    if (typeof navigator === 'undefined' || !navigator.clipboard?.readText) {
      setCaptureError('Clipboard access is not available here. Paste manually.');
      return;
    }

    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (!text) {
        throw new Error('Clipboard is empty');
      }
      setCaptureDraft((current) => ({
        ...current,
        text: appendRecognizedText(current.text, text),
        pageNumber: current.pageNumber || lastUsedPageNumber,
      }));
      showToast({
        title: 'Clipboard pasted',
        description: 'Selected text is ready to be saved.',
        tone: 'success',
        durationMs: 2400,
      });
    } catch (err) {
      setCaptureError(err instanceof Error ? err.message : 'Clipboard text could not be read');
    }
  };

  const resolveSourceBook = React.useCallback(async (requireFreshHighlights: boolean) => {
    let resolvedTitle = displayBookTitle || stripPdfExtension(metadata?.file_name || '') || 'Untitled';
    let resolvedAuthor = sourceAuthorFromUrl || persistedContext?.sourceAuthor || 'Unknown Author';
    let resolvedHighlights = sourceHighlights;
    let resolvedBookId = sourceBookId || bookId;

    const shouldFetchFromLibrary = Boolean(user?.uid) && (
      requireFreshHighlights ||
      !resolvedTitle ||
      !sourceAuthorFromUrl && !persistedContext?.sourceAuthor
    );

    if (shouldFetchFromLibrary && user?.uid) {
      const { items } = await fetchItemsForUser(user.uid);
      const sourceItem = items.find((item) => item.id === resolvedBookId) || items.find((item) => item.id === bookId);
      if (sourceItem) {
        resolvedBookId = sourceItem.id;
        resolvedTitle = sourceItem.title;
        resolvedAuthor = sourceItem.author || resolvedAuthor;
        resolvedHighlights = sourceItem.highlights || [];
        setSourceHighlights(resolvedHighlights);
      }
    }

    if (!resolvedBookId || !resolvedTitle) {
      throw new Error('Current book context could not be resolved');
    }

    return {
      bookId: resolvedBookId,
      title: resolvedTitle,
      author: resolvedAuthor || 'Unknown Author',
      highlights: resolvedHighlights,
    };
  }, [
    bookId,
    displayBookTitle,
    metadata?.file_name,
    persistedContext?.sourceAuthor,
    sourceAuthorFromUrl,
    sourceBookId,
    sourceHighlights,
    user?.uid,
  ]);

  const handleCaptureFieldChange = (field: keyof ReaderCaptureDraft, value: string) => {
    setCaptureDraft((current) => ({ ...current, [field]: value }));
    if (captureError) setCaptureError(null);
  };

  const handleSubmitHighlight = async () => {
    if (!user?.uid) return;
    const cleanText = captureDraft.text.trim();
    if (!cleanText) {
      setCaptureError('Text is required before saving.');
      return;
    }
    if (cleanText.length > MAX_HIGHLIGHT_TEXT_LENGTH) {
      setCaptureError(`Text is too long. Limit is ${MAX_HIGHLIGHT_TEXT_LENGTH} characters.`);
      return;
    }
    if (captureDraft.comment.trim().length > MAX_HIGHLIGHT_COMMENT_LENGTH) {
      setCaptureError(`Comment is too long. Limit is ${MAX_HIGHLIGHT_COMMENT_LENGTH} characters.`);
      return;
    }

    setSubmittingAction('highlight');
    setCaptureError(null);
    const submittedPageNumber = captureDraft.pageNumber.trim();

    try {
      const sourceBook = await resolveSourceBook(true);
      const createdAt = Date.now();
      const nextHighlight = buildCaptureHighlight(
        { ...captureDraft, text: cleanText },
        createdAt,
      );
      const mergedHighlights = [nextHighlight, ...(sourceBook.highlights || [])];

      await syncHighlights(
        user.uid,
        sourceBook.bookId,
        sourceBook.title,
        sourceBook.author,
        'BOOK',
        mergedHighlights,
      );

      setSourceHighlights(mergedHighlights);
      if (submittedPageNumber) {
        setLastUsedPageNumber(submittedPageNumber);
      }
      resetCaptureDraft(submittedPageNumber || lastUsedPageNumber);
      showToast({
        title: 'Highlight saved',
        description: 'The selected text was added to the current book.',
        tone: 'success',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Highlight could not be saved';
      setCaptureError(message);
      showToast({
        title: 'Highlight save failed',
        description: message,
        tone: 'error',
      });
    } finally {
      setSubmittingAction(null);
    }
  };

  const handleSubmitPersonalNote = async () => {
    if (!user?.uid) return;
    const cleanText = captureDraft.text.trim();
    if (!cleanText) {
      setCaptureError('Text is required before saving.');
      return;
    }
    if (captureDraft.comment.trim().length > MAX_HIGHLIGHT_COMMENT_LENGTH) {
      setCaptureError(`Comment is too long. Limit is ${MAX_HIGHLIGHT_COMMENT_LENGTH} characters.`);
      return;
    }

    setSubmittingAction('note');
    setCaptureError(null);
    const submittedPageNumber = captureDraft.pageNumber.trim();

    try {
      const sourceBook = await resolveSourceBook(false);
      const template = findPersonalNoteTemplate('book_note');
      if (!template) {
        throw new Error('Book note template is not available');
      }

      const noteHtml = buildBookNoteHtml({
        templateHtml: template.htmlContent,
        bookTitle: sourceBook.title,
        bookAuthor: sourceBook.author,
        quoteText: cleanText,
        pageNumber: submittedPageNumber,
        comment: captureDraft.comment.trim(),
      });
      const mergedTags = mergeCaptureTags(
        template.defaultTags,
        captureDraftTagsToList(captureDraft.tags),
      );
      const addedAt = Date.now();
      const draftTitle = sourceBook.title
        ? `${template.suggestedTitle} - ${sourceBook.title}`
        : template.suggestedTitle;
      const safeDraftTitle = draftTitle.slice(0, MAX_NOTE_TITLE_LENGTH).trim();
      const localNoteId = `note-${addedAt}-${Math.random().toString(36).slice(2, 8)}`;
      const noteItem = buildPersonalNoteItem({
        id: localNoteId,
        title: safeDraftTitle,
        htmlContent: noteHtml,
        tags: mergedTags,
        addedAt,
        category: template.defaultCategory,
      });

      const savedNoteId = await saveItemForUser(user.uid, noteItem);
      await syncPersonalNote(user.uid, savedNoteId, {
        title: noteItem.title,
        author: noteItem.author,
        content: noteHtml,
        tags: mergedTags,
        category: template.defaultCategory,
      });

      if (submittedPageNumber) {
        setLastUsedPageNumber(submittedPageNumber);
      }
      resetCaptureDraft(submittedPageNumber || lastUsedPageNumber);
      showToast({
        title: 'Personal note created',
        description: 'The copied quote was saved with the book-note template.',
        tone: 'success',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Personal note could not be created';
      setCaptureError(message);
      showToast({
        title: 'Personal note failed',
        description: message,
        tone: 'error',
      });
    } finally {
      setSubmittingAction(null);
    }
  };

  const capturePanelBody = (
    <div className="rounded-[28px] border border-slate-200/80 bg-white/95 p-4 shadow-[0_24px_70px_rgba(15,23,42,0.18)] backdrop-blur">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-600">
            <StickyNote size={12} />
            Capture
          </div>
          <h3 className="mt-3 text-base font-semibold text-slate-900">Save without leaving the PDF</h3>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Copy text in the PDF viewer, then paste or edit it here before sending.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCaptureOpen(false)}
          className="rounded-xl border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
          aria-label="Close capture panel"
        >
          <X size={16} />
        </button>
      </div>

      <div className="mt-4 space-y-3">
        <button
          type="button"
          onClick={() => void handlePasteFromClipboard()}
          disabled={submittingAction !== null}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Clipboard size={15} />
          Paste from Clipboard
        </button>

        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Text</span>
          <textarea
            value={captureDraft.text}
            onChange={(event) => handleCaptureFieldChange('text', event.target.value)}
            rows={6}
            placeholder="Paste the copied PDF text here"
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-800 shadow-inner outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              <Hash size={12} />
              Page Number
            </span>
            <input
              value={captureDraft.pageNumber}
              onChange={(event) => handleCaptureFieldChange('pageNumber', event.target.value)}
              inputMode="numeric"
              placeholder={lastUsedPageNumber || 'Optional'}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              <Tag size={12} />
              Tags
            </span>
            <input
              value={captureDraft.tags}
              onChange={(event) => handleCaptureFieldChange('tags', event.target.value)}
              placeholder="ethics, quote, reading"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
            />
          </label>
        </div>

        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <MessageSquare size={12} />
            Comment
          </span>
          <textarea
            value={captureDraft.comment}
            onChange={(event) => handleCaptureFieldChange('comment', event.target.value)}
            rows={3}
            placeholder="Optional context or why this quote matters"
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-800 shadow-inner outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
          />
        </label>

        {captureError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {captureError}
          </div>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => void handleSubmitHighlight()}
            disabled={submittingAction !== null}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submittingAction === 'highlight' ? <Loader2 size={16} className="animate-spin" /> : <BookOpen size={16} />}
            Add to Highlights
          </button>
          <button
            type="button"
            onClick={() => void handleSubmitPersonalNote()}
            disabled={submittingAction !== null}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submittingAction === 'note' ? <Loader2 size={16} className="animate-spin" /> : <StickyNote size={16} />}
            Send to Personal Note
          </button>
        </div>
      </div>
    </div>
  );

  const renderIosReaderFallback = !loading && !error && isIosMobile;

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(13,148,136,0.12),_transparent_28%),linear-gradient(180deg,_#f7f4ed_0%,_#efe7da_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-3 py-3 sm:px-4 lg:px-6">
        <header className="mb-3 overflow-hidden rounded-[24px] border border-black/5 bg-white/75 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur sm:rounded-[28px]">
          <div className="flex flex-col gap-3 px-3 py-3 sm:gap-4 sm:px-6 sm:py-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-700 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700 sm:h-11 sm:w-11 sm:rounded-2xl"
                aria-label="Back"
              >
                <ArrowLeft size={16} className="sm:h-[18px] sm:w-[18px]" />
              </button>
              <div className="min-w-0">
                <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-teal-700 sm:mb-2 sm:gap-2 sm:px-3 sm:text-[11px] sm:tracking-[0.24em]">
                  <BookOpen size={12} />
                  PDF Reader
                </div>
                <h1 className="truncate text-lg font-semibold sm:text-2xl">
                  {metadata?.file_name || 'Document Reader'}
                </h1>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600 sm:gap-x-3 sm:text-sm">
                  {metadata?.size_bytes ? <span>{formatBytes(metadata.size_bytes)}</span> : null}
                  {metadata?.updated_at ? <span>Updated {new Date(metadata.updated_at).toLocaleString()}</span> : null}
                  {metadata?.parse_path ? <span>{metadata.parse_path}</span> : null}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={openCapturePanel}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-800 transition hover:border-teal-300 hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-60 sm:rounded-2xl sm:px-4 sm:py-2.5"
              >
                <StickyNote size={16} />
                Capture
              </button>
              <button
                type="button"
                onClick={() => setReloadKey((value) => value + 1)}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 sm:rounded-2xl sm:px-4 sm:py-2.5"
              >
                <RefreshCcw size={16} />
                Reload
              </button>
              <button
                type="button"
                onClick={handleDownload}
                disabled={!pdfUrl}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 sm:rounded-2xl sm:px-4 sm:py-2.5"
              >
                <Download size={16} />
                Download
              </button>
              <button
                type="button"
                onClick={handleOpenNative}
                disabled={!pdfUrl}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 sm:rounded-2xl sm:px-4 sm:py-2.5"
              >
                <ExternalLink size={16} />
                {isIosMobile ? 'Open Full PDF' : 'Open Native'}
              </button>
            </div>
          </div>
        </header>

        <div className="grid flex-1 gap-3 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="rounded-[24px] border border-black/5 bg-white/75 p-3.5 shadow-[0_20px_60px_rgba(15,23,42,0.06)] backdrop-blur sm:rounded-[28px] sm:p-5">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600 sm:mb-4 sm:px-3 sm:text-[11px] sm:tracking-[0.22em]">
              <FileText size={12} />
              Reading Session
            </div>
            <div className="space-y-3 sm:space-y-4">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Status</div>
                <div className="mt-1 text-sm text-slate-800">
                  {loading ? 'Loading...' : (error ? 'Failed' : (metadata?.parse_status || 'Ready'))}
                </div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">File</div>
                <div className="mt-1 break-words text-sm text-slate-800">{metadata?.file_name || '-'}</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Target Book</div>
                <div className="mt-1 break-words text-sm text-slate-800">{displayBookTitle || '-'}</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Tips</div>
                <ul className="mt-2 space-y-1.5 text-sm leading-5 text-slate-600 sm:space-y-2 sm:leading-6">
                  <li>Copy text inside the PDF viewer, then use Capture.</li>
                  <li>Page number is optional and stays prefilled from your last save.</li>
                  <li>The file is streamed from TomeHub storage, not local disk.</li>
                </ul>
              </div>
            </div>
          </aside>

          <section className="relative min-h-[70vh] overflow-hidden rounded-[32px] border border-black/5 bg-[#f6f1e8] shadow-[0_30px_80px_rgba(15,23,42,0.1)]">
            {captureOpen ? (
              <div className="absolute right-4 top-4 z-20 hidden w-full max-w-md sm:block">
                {capturePanelBody}
              </div>
            ) : null}

            {loading ? (
              <div className="flex h-full min-h-[70vh] items-center justify-center">
                <div className="flex items-center gap-3 rounded-2xl bg-white/80 px-5 py-4 text-slate-700 shadow-lg backdrop-blur">
                  <Loader2 size={20} className="animate-spin" />
                  <span className="text-sm font-medium">Preparing reader...</span>
                </div>
              </div>
            ) : error ? (
              <div className="flex h-full min-h-[70vh] items-center justify-center p-6">
                <div className="max-w-md rounded-[28px] border border-red-200 bg-white px-6 py-8 text-center shadow-xl">
                  <h2 className="text-lg font-semibold text-slate-900">PDF could not be loaded</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{error}</p>
                  <div className="mt-5 flex justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => setReloadKey((value) => value + 1)}
                      className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-medium text-white"
                    >
                      Retry
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate(-1)}
                      className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700"
                    >
                      Go Back
                    </button>
                  </div>
                </div>
              </div>
            ) : renderIosReaderFallback ? (
              <div className="flex h-full min-h-[70vh] items-center justify-center p-4 sm:p-6">
                <div className="max-w-lg rounded-[28px] border border-slate-200 bg-white/90 p-6 text-center shadow-xl backdrop-blur">
                  <div className="mx-auto inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                    <BookOpen size={12} />
                    iPhone / iPad
                  </div>
                  <h2 className="mt-4 text-xl font-semibold text-slate-900">Use the full PDF viewer on iOS</h2>
                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    Safari does not reliably render multi-page PDFs inside this embedded reader. Open the full PDF,
                    copy the text you need, then switch back to TomeHub and save it with Capture.
                  </p>
                  <div className="mt-5 flex flex-col items-center justify-center gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={handleOpenNative}
                      disabled={!pdfUrl}
                      className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <ExternalLink size={16} />
                      Open Full PDF
                    </button>
                    <button
                      type="button"
                      onClick={openCapturePanel}
                      className="inline-flex items-center gap-2 rounded-2xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm font-medium text-teal-800 transition hover:border-teal-300 hover:bg-teal-100"
                    >
                      <StickyNote size={16} />
                      Open Capture
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <iframe
                key={pdfUrl}
                src={pdfUrl}
                title={metadata?.file_name || 'PDF Reader'}
                className="h-[70vh] w-full border-0 lg:h-[calc(100vh-180px)]"
              />
            )}
          </section>
        </div>
      </div>

      {captureOpen ? (
        <div className="fixed inset-0 z-[120] sm:hidden">
          <button
            type="button"
            aria-label="Close capture overlay"
            className="absolute inset-0 bg-slate-950/35 backdrop-blur-[1px]"
            onClick={() => setCaptureOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[82vh] overflow-y-auto rounded-t-[28px] bg-transparent p-3">
            {capturePanelBody}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default PdfReaderPage;
