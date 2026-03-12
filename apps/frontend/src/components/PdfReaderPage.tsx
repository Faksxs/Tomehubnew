import React from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCcw,
} from 'lucide-react';
import { API_BASE_URL, getFirebaseIdToken } from '../services/apiClient';
import { getBookPdfMetadata, type PdfMetadataResponse } from '../services/backendApiService';
import { useAuth } from '../contexts/AuthContext';

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

export const PdfReaderPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { bookId = '' } = useParams();
  const { user } = useAuth();
  const [metadata, setMetadata] = React.useState<PdfMetadataResponse | null>(null);
  const [pdfUrl, setPdfUrl] = React.useState<string>('');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [reloadKey, setReloadKey] = React.useState(0);
  const requestedTitle = React.useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('title') || '';
  }, [location.search]);

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
                Open Native
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
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Tips</div>
                <ul className="mt-2 space-y-1.5 text-sm leading-5 text-slate-600 sm:space-y-2 sm:leading-6">
                  <li>Use the browser PDF controls for zoom and search.</li>
                  <li>If the embed fails, use `Open Native`.</li>
                  <li>The file is streamed from TomeHub storage, not local disk.</li>
                </ul>
              </div>
            </div>
          </aside>

          <section className="relative min-h-[70vh] overflow-hidden rounded-[32px] border border-black/5 bg-[#f6f1e8] shadow-[0_30px_80px_rgba(15,23,42,0.1)]">
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
    </div>
  );
};

export default PdfReaderPage;
