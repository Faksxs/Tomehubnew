import React, { useState, useEffect } from 'react';
import { LibraryItem, PersonalNoteCategory, PhysicalStatus, ReadingStatus, ResourceType, ContentLanguageMode } from '../types';
import { X, Loader2, Search, ChevronRight, Book as BookIcon, SkipForward, Image as ImageIcon, FileText, Globe, PenTool, Wand2, RefreshCw, Sparkles, Calendar, Upload, FilePlus, AlertCircle, CheckCircle } from 'lucide-react';
import { searchResourcesAI, ItemDraft, generateTagsForNote } from '../services/geminiService';
import { useAuth } from '../contexts/AuthContext';
import { ingestDocument, extractMetadata } from '../services/backendApiService';
import { PersonalNoteEditor } from './PersonalNoteEditor';
import { extractPersonalNoteText, hasMeaningfulPersonalNoteContent } from '../lib/personalNoteRender';

interface BookFormProps {
  initialData?: LibraryItem;
  initialType: ResourceType;
  noteDefaults?: {
    personalNoteCategory?: PersonalNoteCategory;
    personalFolderId?: string;
    folderPath?: string;
  };
  onSave: (item: Omit<LibraryItem, 'id' | 'highlights'>) => void;
  onCancel: () => void;
}

export const BookForm: React.FC<BookFormProps> = ({ initialData, initialType, noteDefaults, onSave, onCancel }) => {
  // 'search' mode is for finding the item first. 'edit' mode is the actual form.
  // Websites and Personal Notes default directly to 'edit'.
  const [mode, setMode] = useState<'search' | 'edit'>(
    initialData ? 'edit' : ((initialType === 'WEBSITE' || initialType === 'PERSONAL_NOTE') ? 'edit' : 'search')
  );

  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ItemDraft[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isFetchingCover, setIsFetchingCover] = useState(false);
  const [isEnriching, setIsEnriching] = useState(false);
  const [isGeneratingTags, setIsGeneratingTags] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isExtractingMetadata, setIsExtractingMetadata] = useState(false);
  const [selectedPdf, setSelectedPdf] = useState<File | null>(null);
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
    folderPath: ''
  });

  useEffect(() => {
    if (initialData) {
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
        folderPath: initialData.folderPath || ''
      });
    } else if (initialType === 'PERSONAL_NOTE') {
      // Defaults for personal notes
      setFormData(prev => ({
        ...prev,
        author: 'Self',
        status: 'On Shelf',
        readingStatus: 'Finished',
        personalNoteCategory: noteDefaults?.personalNoteCategory || 'DAILY',
        personalFolderId: noteDefaults?.personalFolderId || '',
        folderPath: noteDefaults?.folderPath || ''
      }));
    }
  }, [initialData, initialType, noteDefaults]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchResults([]);

    try {
      // Unified search via geminiService (handles books, articles, etc.)
      const results = await searchResourcesAI(searchQuery, initialType);
      setSearchResults(results);

      if (initialType === 'BOOK') {
        console.log(`📚 Search completed for book: "${searchQuery}"`);
      }
    } catch (error) {
      console.error("Search failed:", error);
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
        generalNotes: enriched.summary && enriched.summary.length > 0 ? `AI Summary: ${enriched.summary}` : prev.generalNotes,
        publisher: enriched.publisher || prev.publisher,
        publicationYear: enriched.publishedDate ? String(enriched.publishedDate) : prev.publicationYear,
        isbn: enriched.isbn || prev.isbn,
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

  const selectItem = async (draft: ItemDraft) => {
    // 1. Populate basic data immediately
    setFormData(prev => ({
      ...prev,
      title: draft.title,
      author: draft.author,
      publisher: draft.publisher || '',
      isbn: draft.isbn || '',
      publicationYear: draft.publishedDate || '',
      translator: draft.translator || '',
      tags: draft.tags ? draft.tags.join(', ') : '',
      generalNotes: draft.summary ? `AI Summary: ${draft.summary}` : '',
      coverUrl: draft.coverUrl || '',
      // Only populate URL for websites/articles
      url: (initialType === 'WEBSITE' || initialType === 'ARTICLE') ? (draft.url || '') : '',
      pageCount: draft.pageCount?.toString() || '',
      contentLanguageMode: (draft.contentLanguageMode || formData.contentLanguageMode || 'AUTO') as ContentLanguageMode,
      contentLanguageResolved: ((draft.contentLanguageResolved || '').toLowerCase() === 'tr' ? 'tr' : ((draft.contentLanguageResolved || '').toLowerCase() === 'en' ? 'en' : '')) as '' | 'tr' | 'en',
      sourceLanguageHint: ((draft.sourceLanguageHint || '').toLowerCase() === 'tr' ? 'tr' : ((draft.sourceLanguageHint || '').toLowerCase() === 'en' ? 'en' : '')) as '' | 'tr' | 'en'
    }));

    setMode('edit');

    // 2. Automatically fetch cover for Books
    if (initialType === 'BOOK') {
      triggerCoverFetch(draft.title, draft.author, draft.isbn || '');

      // 3. Auto-Enrich if missing details or language may need normalization
      if (!draft.summary || !draft.tags || draft.tags.length === 0 || !!draft.sourceLanguageHint) {
        triggerEnrichment(draft);
      }
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => {
      if (name === 'contentLanguageMode') {
        return { ...prev, [name]: value, contentLanguageResolved: '' };
      }
      return { ...prev, [name]: value };
    });
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
          if (!formData.title && meta.title && initialType === 'BOOK' && !formData.coverUrl) {
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

    const lentInfo = initialType === 'BOOK' && formData.status === 'Lent Out' && formData.lentToName
      ? { borrowerName: formData.lentToName, lentDate: formData.lentDate || new Date().toISOString().split('T')[0] }
      : undefined;

    // Parse addedAt date from input, or fallback to now
    const addedAtTimestamp = formData.addedAt ? new Date(formData.addedAt).getTime() : Date.now();

    onSave({
      id: newBookId, // Pass the ID we used for ingestion
      type: initialType,
      title: formData.title,
      author: formData.author,
      translator: formData.translator,
      publisher: formData.publisher,
      publicationYear: formData.publicationYear,
      isbn: formData.isbn,
      // Explicitly ensure URL is empty for Books to prevent data pollution
      url: (initialType === 'WEBSITE' || initialType === 'ARTICLE') ? formData.url : '',
      code: formData.code,
      status: formData.status as PhysicalStatus,
      readingStatus: formData.readingStatus as ReadingStatus,
      tags: formData.tags.split(',').map(t => t.trim()).filter(t => t.length > 0),
      generalNotes: formData.generalNotes,
      contentLanguageMode: formData.contentLanguageMode,
      contentLanguageResolved: (formData.contentLanguageResolved || undefined) as 'tr' | 'en' | undefined,
      sourceLanguageHint: (formData.sourceLanguageHint || undefined) as 'tr' | 'en' | undefined,
      personalNoteCategory: isNote ? formData.personalNoteCategory : undefined,
      personalFolderId: isNote ? (formData.personalFolderId.trim() || undefined) : undefined,
      folderPath: isNote ? (formData.folderPath.trim() || undefined) : undefined,
      coverUrl: formData.coverUrl,
      lentInfo,
      addedAt: addedAtTimestamp,
      pageCount: formData.pageCount ? parseInt(formData.pageCount) : undefined
    });
  };

  const getIcon = () => {
    switch (initialType) {
      case 'ARTICLE': return <FileText className="text-[#CC561E]" size={24} />;
      case 'WEBSITE': return <Globe className="text-[#CC561E]" size={24} />;
      case 'PERSONAL_NOTE': return <PenTool className="text-[#CC561E]" size={24} />;
      default: return <BookIcon className="text-[#CC561E]" size={24} />;
    }
  }

  const getTitle = () => {
    if (initialData) return 'Edit Details';
    switch (initialType) {
      case 'ARTICLE': return 'New Article';
      case 'WEBSITE': return 'New Website Resource';
      case 'PERSONAL_NOTE': return 'New Note';
      default: return 'New Book';
    }
  }

  const isNote = initialType === 'PERSONAL_NOTE';
  const noteLabelClass = isNote ? 'text-slate-900 dark:text-slate-900' : 'text-slate-700 dark:text-slate-300';
  const noteSubLabelClass = isNote ? 'text-slate-800 dark:text-slate-900' : 'text-slate-700 dark:text-slate-300';
  const noteHelperClass = isNote ? 'text-slate-700 dark:text-slate-700' : 'text-slate-500 dark:text-slate-400';

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className={`bg-white rounded-xl shadow-2xl w-full overflow-hidden flex flex-col ${isNote ? 'max-w-3xl max-h-[94vh]' : 'max-w-2xl max-h-[90vh]'}`}>

        {/* Header */}
        <div className={`${isNote ? 'p-4' : 'p-5'} border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-white dark:bg-slate-900 z-10`}>
          <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center gap-2">
            {mode === 'search' ? (
              <>
                <Search className="text-[#CC561E]" size={24} />
                Find {initialType === 'ARTICLE' ? 'Article' : 'Book'}
              </>
            ) : (
              <>
                {getIcon()}
                {getTitle()}
              </>
            )}
          </h2>
          <button onClick={onCancel} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Mode: Search */}
        {mode === 'search' && (
          <div className="p-6 flex flex-col h-full overflow-y-auto">
            <form onSubmit={handleSearch} className="relative mb-4">
              <input
                autoFocus
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={initialType === 'ARTICLE' ? "Enter Title, DOI, Author..." : "Enter Title, ISBN, Author..."}
                className="w-full pl-5 pr-14 py-4 text-lg border-2 border-slate-200 dark:border-slate-700 rounded-xl focus:border-[#CC561E] dark:focus:border-[#CC561E] focus:ring-4 focus:ring-[#CC561E]/10 outline-none transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
              />
              <button
                type="submit"
                disabled={isSearching || !searchQuery.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 bg-[#CC561E] text-white p-2 rounded-lg hover:bg-[#b34b1a] disabled:opacity-50 disabled:hover:bg-[#CC561E] transition-colors"
              >
                {isSearching ? <Loader2 className="animate-spin" size={20} /> : <Search size={20} />}
              </button>
            </form>

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
                    <p>No AI results found matching "{searchQuery}".</p>
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
          <form onSubmit={handleSubmit} className={`${isNote ? 'p-4 md:p-5' : 'p-6'} overflow-y-auto flex-1`}>
            {/* Basic Info */}
            <div className={isNote ? 'space-y-3' : 'space-y-5'}>
              <div className={`grid grid-cols-1 md:grid-cols-2 ${isNote ? 'gap-3' : 'gap-4'}`}>
                <div className={isNote ? "md:col-span-2" : "md:col-span-2"}>
                  <label className={`block text-sm font-medium mb-1 ${noteLabelClass}`}>Title *</label>
                  <input
                    required
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    className={`w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 ${isNote ? 'py-1.5 text-sm' : 'py-2'} focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white`}
                    placeholder={isNote ? "Note Title" : (initialType === 'WEBSITE' ? 'Page Title or Site Name' : 'e.g. The Stranger')}
                  />
                </div>

                {!isNote && (
                  <div className={initialType === 'WEBSITE' ? 'md:col-span-2' : ''}>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                      {initialType === 'WEBSITE' ? 'Author / Organization' : 'Author *'}
                    </label>
                    <input
                      required={initialType !== 'WEBSITE'}
                      name="author"
                      value={formData.author}
                      onChange={handleChange}
                      className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      placeholder="e.g. Albert Camus"
                    />
                  </div>
                )}

                {isNote && (
                  <>
                    <div>
                      <label className={`block text-[13px] font-medium mb-1 flex items-center gap-1 ${noteSubLabelClass}`}>
                        <Calendar size={14} className="text-slate-400" />
                        Date
                      </label>
                      <input
                        type="date"
                        name="addedAt"
                        value={formData.addedAt}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className={`block text-[13px] font-medium mb-1 ${noteSubLabelClass}`}>
                        Category
                      </label>
                      <select
                        name="personalNoteCategory"
                        value={formData.personalNoteCategory}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      >
                        <option value="PRIVATE">Private</option>
                        <option value="DAILY">Daily</option>
                        <option value="IDEAS">Ideas</option>
                      </select>
                      <p className={`mt-0.5 text-[10px] leading-tight ${noteHelperClass}`}>
                        Private/Daily sadece local aramada kalir. Ideas AI aramalara da katilir.
                      </p>
                    </div>
                  </>
                )}

                {initialType === 'BOOK' && (
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

                {initialType === 'BOOK' && (
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
                  {initialType !== 'WEBSITE' && (
                    <div className={initialType === 'ARTICLE' ? 'md:col-span-2' : ''}>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        {initialType === 'ARTICLE' ? 'Journal / Publisher' : 'Publisher'}
                      </label>
                      <input
                        name="publisher"
                        value={formData.publisher}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                  )}

                  {initialType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">ISBN</label>
                      <input
                        name="isbn"
                        value={formData.isbn}
                        onChange={handleChange}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] font-mono bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                      />
                    </div>
                  )}

                  {initialType === 'ARTICLE' && (
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

                  {initialType === 'BOOK' && (
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

                  {initialType === 'BOOK' && (
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
              {(initialType === 'WEBSITE' || initialType === 'ARTICLE') && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">URL</label>
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
                  <label className={`block text-sm font-medium mb-1 ${noteLabelClass}`}>
                    Sub-file (optional)
                  </label>
                  <input
                    name="folderPath"
                    value={formData.folderPath}
                    onChange={handleChange}
                    className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    placeholder="e.g. Sermon Ideas or Journal-2026-Week1"
                  />
                </div>
              )}

              {initialType === 'BOOK' && (
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
                        placeholder="Paste image URL or Auto-Find ->"
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg pl-3 pr-24 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] text-sm text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950"
                      />
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
                </div>
              )}

              {/* PDF Upload Section - For Books and Articles */}
              {(initialType === 'BOOK' || initialType === 'ARTICLE') && (
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
                />
                <p className={`mt-1 text-[10px] ${noteHelperClass}`}>
                  Toolbar supports heading, bold, underline, bullet list, numbered list and checklist.
                </p>
              </div>
            )}

            {/* Status & Tags */}
            <div className={isNote ? 'space-y-3' : 'space-y-5'}>
              {!isNote && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Reading Status *</label>
                    <select
                      name="readingStatus"
                      value={formData.readingStatus}
                      onChange={handleChange}
                      className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    >
                      <option value="To Read">To Read</option>
                      <option value="Reading">Reading</option>
                      <option value="Finished">Finished</option>
                    </select>
                  </div>

                  {/* Inventory Status - Books Only */}
                  {initialType === 'BOOK' && (
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
                  placeholder={isNote ? "Use AI to generate tags..." : "Ideas, Todo, Research"}
                />
              </div>

              {/* Lent Out Conditional Fields - Books Only */}
              {initialType === 'BOOK' && formData.status === 'Lent Out' && (
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
                  name="generalNotes"
                  rows={4}
                  value={formData.generalNotes}
                  onChange={handleChange}
                  className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] resize-none leading-relaxed flex-1 bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                  placeholder={initialType === 'WEBSITE' ? "Why did you save this website?" : "Your thoughts..."}
                />
              </div>
            )}

            <div className={`flex justify-between items-center ${isNote ? 'pt-1' : 'pt-2'} mt-auto`}>
              {!initialData && initialType !== 'WEBSITE' && !isNote && (
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
                      Save {initialType === 'ARTICLE' ? 'Article' : (initialType === 'WEBSITE' ? 'Website' : (initialType === 'PERSONAL_NOTE' ? 'Note' : 'Book'))}
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
