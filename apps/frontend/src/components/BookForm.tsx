import React, { useState, useEffect, useRef } from 'react';
import { LibraryItem, PersonalNoteCategory, PhysicalStatus, ReadingStatus, ResourceType, ContentLanguageMode } from '../types';
import { X, Loader2, Search, ChevronRight, Book as BookIcon, SkipForward, Image as ImageIcon, FileText, Globe, PenTool, Wand2, Sparkles, Calendar, Upload, Camera, Film, Tv } from 'lucide-react';
import StarRating from './StarRating';
import { BarcodeScanner } from './BarcodeScanner';
import { searchResourcesAI, ItemDraft, generateTagsForNote } from '../services/geminiService';
import { useAuth } from '../contexts/AuthContext';
import { ingestDocument, extractMetadata, searchMedia, getMediaDetails, type MediaSearchItem } from '../services/backendApiService';
import { PersonalNoteEditor } from './PersonalNoteEditor';
import { extractPersonalNoteText, hasMeaningfulPersonalNoteContent } from '../lib/personalNoteRender';
import { PERSONAL_NOTE_TEMPLATES, findPersonalNoteTemplate } from '../lib/personalNoteTemplates';


interface BookFormProps {
  initialData?: LibraryItem;
  initialType: ResourceType;
  noteDefaults?: {
    personalNoteCategory?: PersonalNoteCategory;
    personalFolderId?: string;
    folderPath?: string;
  };
  onSave: (item: Omit<LibraryItem, 'highlights'>) => void;
  onCancel: () => void;
}

export const BookForm: React.FC<BookFormProps> = ({ initialData, initialType, noteDefaults, onSave, onCancel }) => {
  const mediaLibraryEnabled = import.meta.env.VITE_MEDIA_LIBRARY_ENABLED === 'true';
  const isMediaType = (type: ResourceType) => type === 'MOVIE' || type === 'SERIES';

  // 'search' mode is for finding the item first. 'edit' mode is the actual form.
  // Websites and Personal Notes default directly to 'edit'.
  const [mode, setMode] = useState<'search' | 'edit'>(
    initialData ? 'edit' : ((initialType === 'WEBSITE' || initialType === 'PERSONAL_NOTE') ? 'edit' : 'search')
  );
  const [resourceType, setResourceType] = useState<ResourceType>(initialData?.type || initialType);
  const isMedia = isMediaType(resourceType);

  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<ItemDraft & Partial<MediaSearchItem>>>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isFetchingCover, setIsFetchingCover] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isGeneratingTags, setIsGeneratingTags] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isExtractingMetadata, setIsExtractingMetadata] = useState(false);
  const [selectedPdf, setSelectedPdf] = useState<File | null>(null);
  const [showScanner, setShowScanner] = useState(false);
  const [categoryManuallyEdited, setCategoryManuallyEdited] = useState(false);
  const [mediaPickerError, setMediaPickerError] = useState('');
  const initKeyRef = useRef<string | null>(null);
  const { user } = useAuth();

  // Form State
  const [formData, setFormData] = useState({
    title: '',
    author: '',
    translator: '',
    publisher: '', // Journal for articles
    publicationYear: '',
    isbn: '',
    url: '',
    code: '',
    status: 'On Shelf' as PhysicalStatus,
    readingStatus: 'To Read' as ReadingStatus,
    tags: '',
    generalNotes: '',
    summaryText: '',
    coverUrl: '',
    lentToName: '',
    lentDate: '',
    addedAt: new Date().toISOString().split('T')[0], // Format YYYY-MM-DD
    pageCount: '',
    contentLanguageMode: 'AUTO' as ContentLanguageMode,
    contentLanguageResolved: '' as '' | 'tr' | 'en',
    sourceLanguageHint: '' as '' | 'tr' | 'en',
    personalNoteCategory: 'DAILY' as PersonalNoteCategory,
    personalFolderId: '',
    folderPath: '',
    castTop: '',
    rating: 0
  });

  useEffect(() => {
    const initKey = initialData
      ? `edit:${initialData.id}`
      : `new:${initialType}:${noteDefaults?.personalNoteCategory || ''}:${noteDefaults?.personalFolderId || ''}:${noteDefaults?.folderPath || ''}`;
    if (initKeyRef.current === initKey) return;
    initKeyRef.current = initKey;
    setResourceType(initialData?.type || initialType);
    setMediaPickerError('');

    if (initialData) {
      setCategoryManuallyEdited(false);
      setFormData({
        title: initialData.title,
        author: initialData.author,
        translator: initialData.translator || '',
        publisher: initialData.publisher || '',
        publicationYear: initialData.publicationYear || '',
        isbn: initialData.isbn || '',
        url: initialData.url || '',
        code: initialData.code || '',
        status: initialData.status,
        readingStatus: initialData.readingStatus,
        tags: initialData.tags.join(', '),
        generalNotes: initialData.generalNotes || '',
        summaryText: initialData.summaryText || '',
        coverUrl: initialData.coverUrl || '',
        lentToName: initialData.lentInfo?.borrowerName || '',
        lentDate: initialData.lentInfo?.lentDate || '',
        addedAt: new Date(initialData.addedAt).toISOString().split('T')[0],
        pageCount: initialData.pageCount?.toString() || '',
        contentLanguageMode: initialData.contentLanguageMode || 'AUTO',
        contentLanguageResolved: initialData.contentLanguageResolved || '',
        sourceLanguageHint: (initialData.sourceLanguageHint as '' | 'tr' | 'en') || '',
        personalNoteCategory: initialData.personalNoteCategory || 'DAILY',
        personalFolderId: initialData.personalFolderId || '',
        folderPath: initialData.folderPath || '',
        castTop: Array.isArray(initialData.castTop) ? initialData.castTop.join(', ') : '',
        rating: initialData.rating ?? 0
      });
      return;
    }

    if (initialType === 'PERSONAL_NOTE') {
      setCategoryManuallyEdited(false);
      setFormData(prev => ({
        ...prev,
        author: 'Self',
        status: 'On Shelf',
        readingStatus: 'Finished',
        personalNoteCategory: noteDefaults?.personalNoteCategory || 'DAILY',
        personalFolderId: noteDefaults?.personalFolderId || '',
        folderPath: noteDefaults?.folderPath || '',
        castTop: ''
      }));
      return;
    }

    if (isMediaType(initialType)) {
      setFormData(prev => ({
        ...prev,
        status: 'On Shelf',
        readingStatus: 'To Read',
        castTop: ''
      }));
    }
  }, [
    initialData?.id,
    initialData?.type,
    initialType,
    noteDefaults?.personalNoteCategory,
    noteDefaults?.personalFolderId,
    noteDefaults?.folderPath,
  ]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchResults([]);
    setMediaPickerError('');

    try {
      if (isMedia && mediaLibraryEnabled) {
        const kind = resourceType === 'MOVIE' ? 'movie' : (resourceType === 'SERIES' ? 'tv' : 'multi');
        const results = await searchMedia(searchQuery, kind, 1);
        const mapped = results.map((item) => ({
          title: item.title,
          author: '',
          summary: item.summary || undefined,
          coverUrl: item.coverUrl || null,
          publishedDate: item.year || '',
          isbn: item.tmdbToken,
          tmdbId: item.tmdbId,
          tmdbKind: item.tmdbKind,
          type: item.type,
        })) as Array<ItemDraft & Partial<MediaSearchItem>>;
        setSearchResults(mapped);
        return;
      }

      const results = await searchResourcesAI(searchQuery, resourceType);
      setSearchResults(results as Array<ItemDraft & Partial<MediaSearchItem>>);
    } catch (error) {
      console.error("Search failed:", error);
      if (isMedia && mediaLibraryEnabled) {
        setMediaPickerError(error instanceof Error ? error.message : 'Media search failed');
      }
    } finally {
      setIsSearching(false);
    }
  };

  const handleGenerateTags = async () => {
    const noteText = extractPersonalNoteText(formData.generalNotes);
    if (!noteText) return;
    setIsGeneratingTags(true);
    const tags = await generateTagsForNote(noteText);
    if (tags.length > 0) {
      setFormData(prev => ({
        ...prev,
        tags: tags.join(', ')
      }));
    }
    setIsGeneratingTags(false);
  };

  // Triggered manually or on select
  const triggerCoverFetch = async (title: string, author: string, isbn: string) => {
    setIsFetchingCover(true);
    try {
      // Use centralized robust cover fetcher
      const { fetchBookCover } = await import('../services/geminiService');
      const cover = await fetchBookCover(title, author, isbn);
      if (cover) {
        setFormData(prev => ({ ...prev, coverUrl: cover }));
      }
    } catch (error) {
      console.error("Cover fetch failed:", error);
    } finally {
      setIsFetchingCover(false);
    }
  };

  // Trigger Enrichment if needed
  const triggerEnrichment = async (draft: ItemDraft, forceRegenerate: boolean = false) => {
    setIsEnriching(true);
    try {
      const { enrichBookWithAI } = await import('../services/geminiService');
      const enriched = await enrichBookWithAI(
        {
          ...draft,
          contentLanguageMode: formData.contentLanguageMode,
          sourceLanguageHint: formData.sourceLanguageHint || draft.sourceLanguageHint,
        },
        { forceRegenerate: forceRegenerate }
      );

      setFormData(prev => ({
        ...prev,
        tags: enriched.tags && enriched.tags.length > 0 ? enriched.tags.join(', ') : prev.tags,
        summaryText: enriched.summary && enriched.summary.length > 0 ? enriched.summary : prev.summaryText,
        publisher: enriched.publisher || prev.publisher,
        publicationYear: enriched.publishedDate ? String(enriched.publishedDate) : prev.publicationYear,
        // Keep ISBN unchanged; LLM enrichment must not write ISBN.
        isbn: prev.isbn,
        pageCount: enriched.pageCount ? String(enriched.pageCount) : prev.pageCount,
        translator: enriched.translator || prev.translator,
        contentLanguageResolved:
          ((enriched as any).content_language_resolved || enriched.contentLanguageResolved || prev.contentLanguageResolved || '') as '' | 'tr' | 'en'
      }));
    } catch (e) {
      console.error("Enrichment failed", e);
    } finally {
      setIsEnriching(false);
    }
  };

  const selectItem = async (draft: ItemDraft & Partial<MediaSearchItem>) => {
    if (isMedia && mediaLibraryEnabled && draft.tmdbId && draft.tmdbKind) {
      try {
        const details = await getMediaDetails(draft.tmdbKind, draft.tmdbId);
        if (details?.deleted) {
          setMediaPickerError('This TMDb record is no longer available. You can still save manually.');
        }
        if (details) {
          const nextType = (details.type || resourceType) as ResourceType;
          if (isMediaType(nextType)) {
            setResourceType(nextType);
          }
          setFormData(prev => ({
            ...prev,
            title: prev.title || details.title || draft.title || '',
            author: prev.author || details.author || '',
            publicationYear: prev.publicationYear || details.publicationYear || '',
            summaryText: prev.summaryText || details.summaryText || draft.summary || '',
            coverUrl: prev.coverUrl || details.coverUrl || draft.coverUrl || '',
            url: prev.url || details.url || '',
            isbn: details.tmdbToken || draft.tmdbToken || prev.isbn || '',
            tags: prev.tags || (details.tags && details.tags.length > 0 ? details.tags.join(', ') : draft.tags ? draft.tags.join(', ') : ''),
            castTop: prev.castTop || ((details.castTop || []).join(', ')),
          }));
          setMode('edit');
          return;
        }
      } catch (e) {
        console.error('Media details fetch failed:', e);
        setMediaPickerError(e instanceof Error ? e.message : 'Media details fetch failed');
      }
    }

    setFormData(prev => ({
      ...prev,
      title: draft.title,
      author: draft.author,
      publisher: draft.publisher || '',
      isbn: draft.isbn || '',
      publicationYear: draft.publishedDate || '',
      translator: draft.translator || '',
      tags: draft.tags ? draft.tags.join(', ') : '',
      summaryText: draft.summary || '',
      coverUrl: draft.coverUrl || '',
      url: (resourceType === 'WEBSITE' || resourceType === 'ARTICLE' || isMedia) ? (draft.url || '') : '',
      pageCount: draft.pageCount?.toString() || '',
      contentLanguageMode: (draft.contentLanguageMode || formData.contentLanguageMode || 'AUTO') as ContentLanguageMode,
      contentLanguageResolved: ((draft.contentLanguageResolved || '').toLowerCase() === 'tr' ? 'tr' : ((draft.contentLanguageResolved || '').toLowerCase() === 'en' ? 'en' : '')) as '' | 'tr' | 'en',
      sourceLanguageHint: ((draft.sourceLanguageHint || '').toLowerCase() === 'tr' ? 'tr' : ((draft.sourceLanguageHint || '').toLowerCase() === 'en' ? 'en' : '')) as '' | 'tr' | 'en'
    }));

    setMode('edit');

    if (resourceType === 'BOOK') {
      triggerCoverFetch(draft.title, draft.author, draft.isbn || '');
      if (!draft.summary || !draft.tags || draft.tags.length === 0 || !!draft.sourceLanguageHint) {
        triggerEnrichment(draft);
      }
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    if (name === 'personalNoteCategory') {
      setCategoryManuallyEdited(true);
    }
    setFormData(prev => {
      if (name === 'contentLanguageMode') {
        return { ...prev, [name]: value as ContentLanguageMode, contentLanguageResolved: '' };
      }
      return { ...prev, [name]: value };
    });
  };

  const applyTemplateById = (templateId: string) => {
    if (!isNote || !templateId) return;
    const template = findPersonalNoteTemplate(templateId);
    if (!template) return;

    setFormData(prev => {
      const mergedTags = new Set([
        ...prev.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
        ...template.defaultTags,
      ]);
      const nextCategory = (!categoryManuallyEdited && !initialData)
        ? template.defaultCategory
        : prev.personalNoteCategory;

      return {
        ...prev,
        title: prev.title.trim() ? prev.title : template.suggestedTitle,
        tags: Array.from(mergedTags).join(', '),
        generalNotes: prev.generalNotes.trim()
          ? `${prev.generalNotes}<p></p>${template.htmlContent}`
          : template.htmlContent,
        personalNoteCategory: nextCategory,
      };
    });
  };

  const insertLinkedNoteTokenById = (_noteId: string) => {
    // wiki link feature removed
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.type === 'application/pdf') {
        setSelectedPdf(file);

        // EXTRACTION: If it's a new entry and some fields are empty, auto-fill from PDF metadata
        setIsExtractingMetadata(true);
        try {
          const meta = await extractMetadata(file);

          setFormData(prev => ({
            ...prev,
            title: prev.title || meta.title || '',
            author: prev.author || meta.author || '',
            pageCount: prev.pageCount || meta.page_count?.toString() || ''
          }));

          // If we found a title via PDF but didn't have one, maybe trigger a cover fetch too
          if (!formData.title && meta.title && resourceType === 'BOOK' && !formData.coverUrl) {
            triggerCoverFetch(meta.title, meta.author || '', '');
          }

        } catch (err) {
          console.error("Failed to extract PDF metadata:", err);
        } finally {
          setIsExtractingMetadata(false);
        }
      } else {
        alert('Please select a PDF file');
        e.target.value = '';
      }
    }
  };

  const isNote = resourceType === 'PERSONAL_NOTE';
  const noteLabelClass = isNote ? 'text-slate-900 dark:text-white' : 'text-slate-700 dark:text-slate-300';
  const noteSubLabelClass = isNote ? 'text-slate-800 dark:text-slate-200' : 'text-slate-700 dark:text-slate-300';
  const noteHelperClass = isNote ? 'text-slate-700 dark:text-slate-400' : 'text-slate-500 dark:text-slate-400';


  const normalizeForSearch = (value: string): string =>
    String(value || '')
      .toLocaleLowerCase('tr-TR')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim();

  const resolveSlashCommand = (token: string): 'template' | null => {
    const raw = token.toLocaleLowerCase('tr-TR');
    if (raw === '/task' || raw === '/template') return 'template';
    return null;
  };

  const findTemplateByQuery = (query?: string) => {
    const normalizedQuery = normalizeForSearch(query || '');
    if (!normalizedQuery) return null;
    const exactMatches = PERSONAL_NOTE_TEMPLATES.filter((template) => {
      const candidates = [template.id, template.name, template.suggestedTitle];
      return candidates.some((value) => normalizeForSearch(value) === normalizedQuery);
    });
    if (exactMatches.length === 1) return exactMatches[0];
    if (exactMatches.length > 1) return null;

    const partialMatches = PERSONAL_NOTE_TEMPLATES.filter((template) => {
      const candidates = [template.id, template.name, template.suggestedTitle];
      return candidates.some((value) => normalizeForSearch(value).includes(normalizedQuery));
    });
    if (partialMatches.length === 1) return partialMatches[0];
    return null;
  };



  const handleSlashCommand = ({ command, query, selectedId }: { command: 'template' | 'link'; query?: string; selectedId?: string }) => {
    if (!isNote) return;
    if (command === 'template') {
      if (selectedId) {
        applyTemplateById(selectedId);
        return;
      }
      const templateFromQuery = findTemplateByQuery(query);
      if (templateFromQuery) {
        applyTemplateById(templateFromQuery.id);
        return;
      }
      window.alert('Şablon eklemek için /task <şablon-adı> yaz. Örnek: /task kitap');
      return;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Generate ID for new books to ensure Backend Ingestion and Frontend Item match
    const newBookId = initialData ? initialData.id : Date.now().toString();

    if (selectedPdf && user) {
      setIsIngesting(true);
      try {
        await ingestDocument(selectedPdf, formData.title, formData.author, user.uid, newBookId, formData.tags);
      } catch (err) {
        console.error("PDF Ingestion failed:", err);
        // We still continue to save the metadata even if PDF fails
      } finally {
        setIsIngesting(false);
      }
    }

    const lentInfo = resourceType === 'BOOK' && formData.status === 'Lent Out' && formData.lentToName
      ? { borrowerName: formData.lentToName, lentDate: formData.lentDate || new Date().toISOString().split('T')[0] }
      : undefined;

    // Parse addedAt date from input, or fallback to now
    const addedAtTimestamp = formData.addedAt ? new Date(formData.addedAt).getTime() : Date.now();
    let preparedGeneralNotes = formData.generalNotes;

    onSave({
      id: newBookId, // Pass the ID we used for ingestion
      type: resourceType,
      title: formData.title,
      author: formData.author,
      translator: formData.translator,
      publisher: isMedia ? '' : formData.publisher,
      publicationYear: formData.publicationYear,
      isbn: formData.isbn,
      url: (resourceType === 'WEBSITE' || resourceType === 'ARTICLE' || isMedia) ? formData.url : '',
      code: formData.code,
      status: formData.status as PhysicalStatus,
      readingStatus: formData.readingStatus as ReadingStatus,
      tags: formData.tags.split(',').map(t => t.trim()).filter(t => t.length > 0),
      generalNotes: isNote ? preparedGeneralNotes : '',
      summaryText: isNote ? '' : formData.summaryText,
      contentLanguageMode: formData.contentLanguageMode,
      contentLanguageResolved: (formData.contentLanguageResolved || undefined) as 'tr' | 'en' | undefined,
      sourceLanguageHint: (formData.sourceLanguageHint || undefined) as 'tr' | 'en' | undefined,
      personalNoteCategory: isNote ? formData.personalNoteCategory : undefined,
      personalFolderId: isNote ? (formData.personalFolderId.trim() || undefined) : undefined,
      folderPath: isNote ? (formData.folderPath.trim() || undefined) : undefined,
      coverUrl: formData.coverUrl,
      castTop: isMedia ? formData.castTop.split(',').map(t => t.trim()).filter(Boolean).slice(0, 6) : undefined,
      lentInfo,
      addedAt: addedAtTimestamp,
      pageCount: resourceType === 'BOOK' && formData.pageCount ? parseInt(formData.pageCount) : undefined,
      rating: !isNote && formData.rating > 0 ? formData.rating : undefined,
    });
  };

  const getIcon = () => {
    const size = isNote ? 20 : 24;
    switch (resourceType) {
      case 'ARTICLE': return <FileText className="text-[#CC561E]" size={size} />;
      case 'WEBSITE': return <Globe className="text-[#CC561E]" size={size} />;
      case 'PERSONAL_NOTE': return <PenTool className="text-[#CC561E]" size={size} />;
      case 'MOVIE': return <Film className="text-[#CC561E]" size={size} />;
      case 'SERIES': return <Tv className="text-[#CC561E]" size={size} />;
      default: return <BookIcon className="text-[#CC561E]" size={size} />;
    }
  }

  const getTitle = () => {
    if (initialData) return 'Edit Details';
    switch (resourceType) {
      case 'ARTICLE': return 'New Article';
      case 'WEBSITE': return 'New Website Resource';
      case 'PERSONAL_NOTE': return 'New Note';
      case 'MOVIE': return 'New Movie';
      case 'SERIES': return 'New Series';
      default: return 'New Book';
    }
  }

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className={`bg-white dark:bg-slate-900 rounded-xl shadow-2xl w-full overflow-hidden flex flex-col ${isNote ? 'max-w-3xl max-h-[94vh]' : 'max-w-2xl max-h-[90vh]'}`}>

        {/* Header */}
        <div className={`${isNote ? 'p-3 md:p-4' : 'p-5'} border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-white dark:bg-slate-900 z-10`}>
          <h2 className={`${isNote ? 'text-lg' : 'text-xl'} font-bold text-slate-800 dark:text-white flex items-center gap-2`}>
            {mode === 'search' ? (
              <>
                <Search className="text-[#CC561E]" size={24} />
                Find {resourceType === 'ARTICLE' ? 'Article' : (isMedia ? 'Media' : 'Book')}
              </>
            ) : (
              <>
                {getIcon()}
                {getTitle()}
              </>
            )}
          </h2>
          <button onClick={onCancel} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors">
            <X size={isNote ? 20 : 24} />
          </button>
        </div>

        {/* Mode: Search */}
        {mode === 'search' && (
          <div className="p-6 flex flex-col h-full overflow-y-auto">
            {isMedia && mediaLibraryEnabled && (
              <div className="mb-3">
                <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Type</label>
                <select
                  value={resourceType}
                  onChange={(e) => setResourceType(e.target.value as ResourceType)}
                  className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                >
                  <option value="MOVIE">Movie</option>
                  <option value="SERIES">Series</option>
                </select>
              </div>
            )}
            <form onSubmit={handleSearch} className="relative mb-4">
              <input
                autoFocus
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={isMedia ? "Enter title, director, cast..." : (resourceType === 'ARTICLE' ? "Enter Title, DOI, Author..." : "Enter Title, ISBN, Author...")}
                className="w-full pl-5 pr-28 py-4 text-lg border-2 border-slate-200 dark:border-slate-700 rounded-xl focus:border-[#CC561E] dark:focus:border-[#CC561E] focus:ring-4 focus:ring-[#CC561E]/10 outline-none transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                {resourceType === 'BOOK' && (
                  <button
                    type="button"
                    onClick={() => setShowScanner(true)}
                    className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 p-2 rounded-lg hover:bg-[#CC561E]/10 hover:text-[#CC561E] dark:hover:bg-[#CC561E]/20 dark:hover:text-[#f3a47b] transition-colors"
                    title="Scan ISBN barcode with camera"
                  >
                    <Camera size={20} />
                  </button>
                )}
                <button
                  type="submit"
                  disabled={isSearching || !searchQuery.trim()}
                  className="bg-[#CC561E] text-white p-2 rounded-lg hover:bg-[#b34b1a] disabled:opacity-50 disabled:hover:bg-[#CC561E] transition-colors"
                >
                  {isSearching ? <Loader2 className="animate-spin" size={20} /> : <Search size={20} />}
                </button>
              </div>
            </form>

            {showScanner && (
              <BarcodeScanner
                onDetected={(code) => {
                  setShowScanner(false);
                  setSearchQuery(code);
                  // Auto-trigger search with the scanned ISBN
                  setIsSearching(true);
                  setSearchResults([]);
                  searchResourcesAI(code, resourceType)
                    .then((results) => setSearchResults(results))
                    .catch((err) => console.error('Barcode search failed:', err))
                    .finally(() => setIsSearching(false));
                }}
                onClose={() => setShowScanner(false)}
              />
            )}

            {mediaPickerError && (
              <p className="mt-2 text-xs text-red-600 dark:text-red-400">{mediaPickerError}</p>
            )}
            <div className="space-y-3 flex-1 mt-6">
              {searchResults.length > 0 ? (
                <>
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Matches Found</p>
                  {searchResults.map((draft, idx) => (
                    <button
                      key={idx}
                      onClick={() => selectItem(draft)}
                      className="w-full text-left p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-[#CC561E]/50 dark:hover:border-[#CC561E]/50 hover:shadow-md hover:bg-[rgba(204,86,30,0.05)] dark:hover:bg-[rgba(204,86,30,0.1)] transition-all group flex justify-between items-center"
                    >
                      <div>
                        <h3 className="font-bold text-slate-900 dark:text-white">{draft.title}</h3>
                        <p className="text-slate-600 dark:text-slate-400 text-sm">{draft.author}</p>
                        <div className="flex gap-3 mt-1 text-xs text-slate-400">
                          {draft.publisher && <span>{draft.publisher}</span>}
                          {draft.publishedDate && <span>{draft.publishedDate}</span>}
                          {draft.isbn && <span className="font-mono tracking-tight">ISBN: {draft.isbn}</span>}
                        </div>
                      </div>
                      <ChevronRight className="text-slate-300 dark:text-slate-600 group-hover:text-[#CC561E]" size={20} />
                    </button>
                  ))}
                </>
              ) : (
                !isSearching && searchQuery && (
                  <div className="text-center py-10 text-slate-500">
                    <p>{isMedia ? `No TMDb results found matching "${searchQuery}".` : `No AI results found matching "${searchQuery}".`}</p>
                    <p className="text-sm mt-2">Try entering details manually.</p>
                  </div>
                )
              )}
            </div>

            <div className="mt-6 pt-6 border-t border-slate-100 dark:border-slate-800 flex justify-center">
              <button
                onClick={() => setMode('edit')}
                className="text-slate-500 dark:text-slate-400 hover:text-[#CC561E] dark:hover:text-[#f3a47b] text-sm font-medium flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
              >
                <span>Don't see it? Enter details manually</span>
                <SkipForward size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Mode: Edit Form */}
        {mode === 'edit' && (
          <form onSubmit={handleSubmit} className={`${isNote ? 'p-3 md:p-5' : 'p-6'} overflow-y-auto flex-1`}>
            {/* Basic Info */}
            <div className={isNote ? 'space-y-2' : (isMedia ? 'space-y-3.5' : 'space-y-5')}>
              <div className={`grid grid-cols-1 md:grid-cols-2 ${isNote ? 'gap-2' : (isMedia ? 'gap-3.5' : 'gap-4')}`}>
                {isMedia && (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Media Type</label>
                      <select
                        value={resourceType}
                        onChange={(e) => setResourceType(e.target.value as ResourceType)}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      >
                        <option value="MOVIE">Movie</option>
                        <option value="SERIES">Series</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Year</label>
                      <input
                        name="publicationYear"
                        value={formData.publicationYear}
                        onChange={handleChange}
                        placeholder="YYYY"
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                  </>
                )}
                <div className="md:col-span-2">
                  <label className={`block text-[12px] font-medium mb-0.5 ${noteLabelClass}`}>Title *</label>
                  <input
                    required
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    className={`w-full border border-slate-300 dark:border-slate-700 rounded-lg px-2.5 ${isNote ? 'py-1.5 text-sm' : 'py-2'} focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white`}
                    placeholder={isNote ? "Note Title" : (resourceType === 'WEBSITE' ? 'Page Title or Site Name' : (isMedia ? 'e.g. The Matrix' : 'e.g. The Stranger'))}
                  />
                </div>

                {!isNote && (
                  <div className={(resourceType === 'WEBSITE' || isMedia) ? 'md:col-span-2' : ''}>
                    <div className={isMedia ? "grid grid-cols-2 gap-3.5" : ""}>
                      <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                          {isMedia ? 'Director / Creator *' : (resourceType === 'WEBSITE' ? 'Author / Organization' : 'Author *')}
                        </label>
                        <input
                          required={resourceType !== 'WEBSITE'}
                          name="author"
                          value={formData.author}
                          onChange={handleChange}
                          className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                          placeholder={isMedia ? 'e.g. Christopher Nolan' : 'e.g. Albert Camus'}
                        />
                      </div>
                      {isMedia && (
                        <div>
                          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Watch Status *</label>
                          <select
                            name="readingStatus"
                            value={formData.readingStatus}
                            onChange={handleChange}
                            className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                          >
                            <option value="To Read">Watchlist</option>
                            <option value="Reading">Watching</option>
                            <option value="Finished">Watched</option>
                          </select>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {isNote && (
                  <div className="md:col-span-2 grid grid-cols-2 gap-3">
                    <div>
                      <label className={`block text-[12px] font-medium mb-0.5 flex items-center gap-1 ${noteSubLabelClass}`}>
                        <Calendar size={12} className="text-slate-400" />
                        Date
                      </label>
                      <input
                        type="date"
                        name="addedAt"
                        value={formData.addedAt}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className={`block text-[12px] font-medium mb-0.5 ${noteSubLabelClass}`}>
                        Category
                      </label>
                      <select
                        name="personalNoteCategory"
                        value={formData.personalNoteCategory}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      >
                        <option value="PRIVATE">Private</option>
                        <option value="DAILY">Daily</option>
                        <option value="IDEAS">Ideas</option>
                      </select>
                    </div>
                    <p className={`col-span-2 text-[10px] leading-tight ${noteHelperClass}`}>
                      Private/Daily sadece local aramada kalir. Ideas AI aramalara da katilir.
                    </p>
                  </div>
                )}

                {resourceType === 'BOOK' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Translator</label>
                    <input
                      name="translator"
                      value={formData.translator}
                      onChange={handleChange}
                      className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    />
                  </div>
                )}

                {resourceType === 'BOOK' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Content Language</label>
                    <select
                      name="contentLanguageMode"
                      value={formData.contentLanguageMode}
                      onChange={handleChange}
                      className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    >
                      <option value="AUTO">AUTO (Recommended)</option>
                      <option value="TR">TR</option>
                      <option value="EN">EN</option>
                    </select>
                    {(formData.contentLanguageResolved || formData.sourceLanguageHint) && (
                      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                        Resolved: {formData.contentLanguageResolved || '-'} | Source Hint: {formData.sourceLanguageHint || '-'}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {!isNote && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {resourceType !== 'WEBSITE' && !isMedia && (
                    <div className={resourceType === 'ARTICLE' ? 'md:col-span-2' : ''}>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        {resourceType === 'ARTICLE' ? 'Journal / Publisher' : 'Publisher'}
                      </label>
                      <input
                        name="publisher"
                        value={formData.publisher}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                  )}

                  {resourceType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">ISBN</label>
                      <div className="flex gap-1.5">
                        <input
                          name="isbn"
                          value={formData.isbn}
                          onChange={handleChange}
                          className="flex-1 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] font-mono bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                        />
                        <button
                          type="button"
                          onClick={() => setShowScanner(true)}
                          className="px-2.5 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-500 dark:text-slate-400 hover:text-[#CC561E] hover:border-[#CC561E]/50 dark:hover:text-[#f3a47b] dark:hover:border-[#CC561E]/50 transition-colors"
                          title="Scan ISBN barcode"
                        >
                          <Camera size={18} />
                        </button>
                      </div>
                      {showScanner && (
                        <BarcodeScanner
                          onDetected={(code) => {
                            setShowScanner(false);
                            setFormData(prev => ({ ...prev, isbn: code }));
                          }}
                          onClose={() => setShowScanner(false)}
                        />
                      )}
                    </div>
                  )}

                  {resourceType === 'ARTICLE' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Year</label>
                      <input
                        name="publicationYear"
                        value={formData.publicationYear}
                        onChange={handleChange}
                        placeholder="YYYY"
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                  )}

                  {resourceType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Page Count</label>
                      <input
                        type="number"
                        name="pageCount"
                        value={formData.pageCount}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                        placeholder="e.g. 250"
                      />
                    </div>
                  )}

                  {resourceType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Shelf Code</label>
                      <input
                        name="code"
                        value={formData.code}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                        placeholder="e.g. A-12"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* URL Field for Website or Article */}
              {(resourceType === 'WEBSITE' || resourceType === 'ARTICLE' || isMedia) && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{isMedia ? 'IMDb / Source URL' : 'URL'}</label>
                  <input
                    name="url"
                    value={formData.url}
                    onChange={handleChange}
                    className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] text-[#CC561E] dark:text-[#f3a47b] bg-white dark:bg-slate-950"
                    placeholder="https://..."
                  />
                </div>
              )}

              {isNote && (
                <div>
                  <label className={`block text-[12px] font-medium mb-0.5 ${noteLabelClass}`}>
                    Sub-file (optional)
                  </label>
                  <input
                    name="folderPath"
                    value={formData.folderPath}
                    onChange={handleChange}
                    className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    placeholder="e.g. Sermon Ideas or Journal-2026-Week1"
                  />
                </div>
              )}

              {(resourceType === 'BOOK' || isMedia) && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ImageIcon size={16} />
                      Cover Image URL
                    </div>
                  </label>

                  <div className="flex gap-4 items-start">
                    <div className="flex-1 relative">
                      <input
                        name="coverUrl"
                        value={formData.coverUrl}
                        onChange={handleChange}
                        placeholder={isMedia ? "Paste poster image URL" : "Paste image URL or Auto-Find ->"}
                        className={`w-full border border-slate-300 dark:border-slate-700 rounded-lg pl-3 ${isMedia ? 'pr-3' : 'pr-24'} py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] text-sm text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950`}
                      />
                      {!isMedia && (
                        <button
                          type="button"
                          onClick={() => triggerCoverFetch(formData.title, formData.author, formData.isbn)}
                          disabled={isFetchingCover || (!formData.title && !formData.isbn)}
                          className="absolute right-1 top-1 bottom-1 px-3 bg-[rgba(204,86,30,0.1)] dark:bg-[rgba(204,86,30,0.2)] hover:bg-[rgba(204,86,30,0.15)] dark:hover:bg-[rgba(204,86,30,0.25)] text-[#CC561E] dark:text-[#f3a47b] rounded text-xs font-semibold flex items-center gap-1 transition-colors"
                          title="Auto-find cover based on Title/ISBN"
                        >
                          {isFetchingCover ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
                          Auto-Find
                        </button>
                      )}
                    </div>
                    <div className="w-16 h-20 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center overflow-hidden flex-shrink-0 shadow-sm relative group">
                      {formData.coverUrl ? (
                        <img
                          src={formData.coverUrl}
                          alt="Preview"
                          className="w-full h-full object-cover"
                          onError={(e) => e.currentTarget.style.display = 'none'}
                        />
                      ) : (
                        <ImageIcon className="text-slate-300" size={20} />
                      )}
                      {isFetchingCover && (
                        <div className="absolute inset-0 bg-white/50 flex items-center justify-center backdrop-blur-[1px]">
                          <Loader2 size={16} className="animate-spin text-[#CC561E]" />
                        </div>
                      )}
                      {!isFetchingCover && !formData.coverUrl && (
                        <div className="absolute inset-0 bg-black/5 hidden group-hover:flex items-center justify-center">
                          <Search size={12} className="text-slate-500" />
                        </div>
                      )}
                    </div>
                  </div>
                  {!isMedia && (
                    <div className="mt-1 flex justify-end">
                      <a
                        href={`https://www.google.com/search?tbm=isch&q=book+cover+${encodeURIComponent(formData.title + ' ' + formData.author)}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-slate-400 dark:text-slate-500 hover:text-[#CC561E] dark:hover:text-[#f3a47b] hover:underline flex items-center gap-1"
                      >
                        Manual Search on Google Images <Search size={10} />
                      </a>
                    </div>
                  )}
                </div>
              )}

              {isMedia && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Top Cast (max 6, comma separated)</label>
                  <input
                    name="castTop"
                    value={formData.castTop}
                    onChange={handleChange}
                    className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    placeholder="e.g. Cillian Murphy, Emily Blunt"
                  />
                </div>
              )}

              {/* PDF Upload Section - For Books and Articles */}
              {(resourceType === 'BOOK' || resourceType === 'ARTICLE') && (
                <div className="bg-[rgba(204,86,30,0.05)] dark:bg-[rgba(204,86,30,0.1)] p-4 rounded-xl border border-[#CC561E]/10 dark:border-[#CC561E]/20">
                  <label className="block text-sm font-semibold text-[#CC561E] dark:text-[#f3a47b] mb-2 flex items-center gap-2">
                    <Upload size={16} />
                    Upload PDF Document to Library
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="file"
                      accept=".pdf"
                      onChange={handleFileChange}
                      className="flex-1 text-sm text-slate-600 dark:text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-[#CC561E] file:text-white hover:file:bg-[#b34b1a] transition-all cursor-pointer"
                    />
                    {selectedPdf && (
                      <button
                        type="button"
                        onClick={() => setSelectedPdf(null)}
                        className="text-red-500 hover:text-red-600 p-2"
                        title="Remove PDF"
                      >
                        <X size={18} />
                      </button>
                    )}
                    {isExtractingMetadata && (
                      <div className="flex items-center gap-1.5 text-xs text-[#CC561E] font-medium animate-pulse">
                        <Loader2 size={14} className="animate-spin" />
                        Verifying metadata...
                      </div>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-2">
                    PDF content will be vectorized and added to your searchable AI library.
                  </p>
                </div>
              )}
            </div>

            <hr className={`${isNote ? 'my-3' : 'my-6'} border-slate-100 dark:border-slate-800`} />

            {/* Notes Section moved UP for Personal Notes to prioritize writing */}
            {isNote && (
              <div className="mb-4 flex-1 flex flex-col">
                <label className={`block text-sm font-medium mb-1 ${noteLabelClass}`}>
                  Content
                </label>
                <PersonalNoteEditor
                  value={formData.generalNotes}
                  onChange={(next) => setFormData(prev => ({ ...prev, generalNotes: next }))}
                  minHeight={420}
                  onSlashCommand={handleSlashCommand}
                  slashTemplateItems={PERSONAL_NOTE_TEMPLATES.map((template) => ({ id: template.id, label: template.name }))}
                />
                <p className={`mt-1 text-[10px] ${noteHelperClass}`}>
                  Toolbar supports heading, bold, underline, bullet list, numbered list and checklist.
                  Hızlı şablon için: /task &lt;şablon-adı&gt; (örn: /task kitap)
                </p>
              </div>
            )}

            {/* Status & Tags */}
            <div className={isNote ? 'space-y-3' : (isMedia ? 'space-y-3.5' : 'space-y-5')}>
              {!isNote && !isMedia && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{isMedia ? 'Watch Status *' : 'Reading Status *'}</label>
                    <select
                      name="readingStatus"
                      value={formData.readingStatus}
                      onChange={handleChange}
                      className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    >
                      <option value="To Read">{isMedia ? 'Watchlist' : 'To Read'}</option>
                      <option value="Reading">{isMedia ? 'Watching' : 'Reading'}</option>
                      <option value="Finished">{isMedia ? 'Watched' : 'Finished'}</option>
                    </select>
                  </div>

                  {/* Inventory Status - Books Only */}
                  {resourceType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Inventory Status *</label>
                      <select
                        name="status"
                        value={formData.status}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      >
                        <option value="On Shelf">On Shelf</option>
                        <option value="Lent Out">Lent Out</option>
                        <option value="Lost">Lost</option>
                      </select>
                    </div>
                  )}
                </div>
              )}

              <div className="relative">
                <label className={`block text-sm font-medium mb-1 flex justify-between ${noteLabelClass}`}>
                  <div className="flex items-center gap-2">
                    Tags (comma separated)
                    {isEnriching && (
                      <span className="text-xs text-[#CC561E] animate-pulse flex items-center gap-1">
                        <Sparkles size={10} /> AI Enriching...
                      </span>
                    )}
                  </div>
                  {isNote && (
                    <button
                      type="button"
                      onClick={handleGenerateTags}
                      disabled={isGeneratingTags || !hasMeaningfulPersonalNoteContent(formData.generalNotes)}
                      className="text-xs text-[#CC561E] dark:text-[#f3a47b] hover:text-[#b34b1a] dark:hover:text-white flex items-center gap-1 disabled:opacity-50"
                    >
                      {isGeneratingTags ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                      AI Auto-Tag
                    </button>
                  )}
                </label>
                <input
                  name="tags"
                  value={formData.tags}
                  onChange={handleChange}
                  className={`w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 ${isNote ? 'py-1.5 text-sm' : 'py-2'} focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white`}
                  placeholder={isNote ? "Use AI to generate tags..." : (isMedia ? "Sci-Fi, Mind-bending, Rewatch" : "Ideas, Todo, Research")}
                />
              </div>

              {/* Star Rating - for all non-note types */}
              {!isNote && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                    {isMedia ? 'Your Rating' : 'Rating'}
                  </label>
                  <StarRating
                    value={formData.rating || undefined}
                    onChange={(rating) => setFormData(prev => ({ ...prev, rating }))}
                    size={22}
                  />
                  {formData.rating > 0 && (
                    <button
                      type="button"
                      onClick={() => setFormData(prev => ({ ...prev, rating: 0 }))}
                      className="mt-1 text-xs text-slate-400 dark:text-slate-500 hover:text-red-400 transition-colors"
                    >
                      Clear rating
                    </button>
                  )}
                </div>
              )}

              {/* Lent Out Conditional Fields - Books Only */}
              {resourceType === 'BOOK' && formData.status === 'Lent Out' && (
                <div className="bg-amber-50 p-4 rounded-lg border border-amber-200 grid grid-cols-1 md:grid-cols-2 gap-4 animate-in slide-in-from-top-2">
                  <div>
                    <label className="block text-sm font-medium text-amber-800 mb-1">Lent To (Name) *</label>
                    <input
                      required
                      name="lentToName"
                      value={formData.lentToName}
                      onChange={handleChange}
                      className="w-full border border-amber-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-amber-800 mb-1">Date</label>
                    <input
                      type="date"
                      name="lentDate"
                      value={formData.lentDate}
                      onChange={handleChange}
                      className="w-full border border-amber-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-amber-500"
                    />
                  </div>
                </div>
              )}
            </div>

            <hr className={`${isNote ? 'my-3' : 'my-6'} border-slate-100 dark:border-slate-800`} />

            {/* Notes (Only for non-notes) */}
            {!isNote && (
              <div className="mb-4 flex-1 flex flex-col">
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Summary
                </label>
                <textarea
                  name="summaryText"
                  rows={4}
                  value={formData.summaryText}
                  onChange={handleChange}
                  className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] resize-none leading-relaxed flex-1 bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                  placeholder={resourceType === 'WEBSITE' ? "Why did you save this website?" : (isMedia ? "Your review and key takeaways..." : "Your thoughts...")}
                />
              </div>
            )}

            <div className={`flex justify-between items-center ${isNote ? 'pt-1' : 'pt-2'} mt-auto`}>
              {!initialData && resourceType !== 'WEBSITE' && !isNote && (
                <button
                  type="button"
                  onClick={() => setMode('search')}
                  className="text-sm text-slate-500 dark:text-slate-400 hover:text-[#CC561E] dark:hover:text-[#f3a47b] underline decoration-[#CC561E]/30 dark:decoration-[#CC561E]/50 hover:decoration-[#CC561E] dark:hover:decoration-[#CC561E]"
                >
                  Back to Search
                </button>
              )}
              <div className="flex gap-3 ml-auto">
                <button
                  type="button"
                  onClick={onCancel}
                  className="px-5 py-2 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isIngesting}
                  className="px-5 py-2 bg-[#CC561E] text-white hover:bg-[#b34b1a] rounded-lg shadow-lg shadow-[#CC561E]/20 transition-all font-medium flex items-center gap-2 active:scale-95"
                >
                  {isIngesting ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />
                      Ingesting PDF...
                    </>
                  ) : (
                    <>
                      Save {resourceType === 'ARTICLE'
                        ? 'Article'
                        : (resourceType === 'WEBSITE'
                          ? 'Website'
                          : (resourceType === 'PERSONAL_NOTE'
                            ? 'Note'
                            : (resourceType === 'MOVIE' ? 'Movie' : (resourceType === 'SERIES' ? 'Series' : 'Book'))))}
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

