import React, { useState, useEffect } from 'react';
import { LibraryItem, PhysicalStatus, ReadingStatus, ResourceType } from '../types';
import { X, Loader2, Search, ChevronRight, Book as BookIcon, SkipForward, Image as ImageIcon, FileText, Globe, PenTool, Wand2, RefreshCw, Sparkles, Calendar } from 'lucide-react';
import { searchResourcesAI, ItemDraft, generateTagsForNote } from '../services/geminiService';

interface BookFormProps {
  initialData?: LibraryItem;
  initialType: ResourceType;
  onSave: (item: Omit<LibraryItem, 'id' | 'highlights'>) => void;
  onCancel: () => void;
}

export const BookForm: React.FC<BookFormProps> = ({ initialData, initialType, onSave, onCancel }) => {
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
  const [isGeneratingTags, setIsGeneratingTags] = useState(false);

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
    addedAt: new Date().toISOString().split('T')[0] // Format YYYY-MM-DD
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
        addedAt: new Date(initialData.addedAt).toISOString().split('T')[0]
      });
    } else if (initialType === 'PERSONAL_NOTE') {
      // Defaults for personal notes
      setFormData(prev => ({ ...prev, author: 'Self', status: 'On Shelf', readingStatus: 'Finished' }));
    }
  }, [initialData, initialType]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchResults([]);

    // Use optimized search for books
    if (initialType === 'BOOK') {
      const { searchBooks } = await import('../services/bookSearchService');
      const result = await searchBooks(searchQuery);
      setSearchResults(result.results);

      // Log search performance
      console.log(`📚 Search source: ${result.source}, cached: ${result.cached}`);
    } else {
      // Use existing service for articles/websites
      const results = await searchResourcesAI(searchQuery, initialType);
      setSearchResults(results);
    }

    setIsSearching(false);
  };

  const handleGenerateTags = async () => {
    if (!formData.generalNotes) return;
    setIsGeneratingTags(true);
    const tags = await generateTagsForNote(formData.generalNotes);
    if (tags.length > 0) {
      setFormData(prev => ({
        ...prev,
        tags: tags.join(', ')
      }));
    }
    setIsGeneratingTags(false);
  };

  // Robust Cover Finder Logic with Fallback Strategy
  const findBestCover = async (title: string, author: string, isbn: string): Promise<string | null> => {
    const cleanIsbn = isbn ? isbn.replace(/[^0-9X]/gi, '') : '';

    // Helper to fetch from Google Books
    const searchGoogle = async (query: string) => {
      try {
        const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=${query}&maxResults=1`);

        // Check for service unavailable or other errors
        if (!res.ok) {
          if (res.status === 503) {
            console.warn('Google Books returned 503 (Service Unavailable)');
          }
          return null;
        }

        const data = await res.json();
        const item = data.items?.[0];
        const links = item?.volumeInfo?.imageLinks;
        if (links?.thumbnail || links?.smallThumbnail) {
          let url = links.thumbnail || links.smallThumbnail;
          // Force HTTPS and remove curling effect
          url = url.replace(/^http:\/\//i, 'https://').replace('&edge=curl', '');
          return url;
        }
      } catch (e) {
        console.warn('Google Books fetch error:', e);
        // Continue to fallback
      }
      return null;
    };

    // 1. Try Google Books by ISBN (Highest Accuracy)
    if (cleanIsbn) {
      const url = await searchGoogle(`isbn:${cleanIsbn}`);
      if (url) return url;
    }

    // 2. Try Google Books by Title + Author
    if (title && author) {
      const query = `intitle:${encodeURIComponent(title)}+inauthor:${encodeURIComponent(author)}`;
      const url = await searchGoogle(query);
      if (url) return url;
    }

    // 3. Try Google Books by just Title (Broad search)
    if (title) {
      const url = await searchGoogle(`intitle:${encodeURIComponent(title)}`);
      if (url) return url;
    }

    // 4. Fallback to OpenLibrary ISBN (Direct URL)
    if (cleanIsbn) {
      try {
        const coverUrl = `https://covers.openlibrary.org/b/isbn/${cleanIsbn}-L.jpg`;
        const response = await fetch(coverUrl, { method: 'HEAD' });
        if (response.ok) {
          console.log('✓ Cover found via OpenLibrary ISBN (fallback)');
          return coverUrl;
        }
      } catch (e) {
        console.warn('OpenLibrary cover fetch failed:', e);
      }
    }

    // 5. Try OpenLibrary search as last resort
    if (title) {
      try {
        const query = author ? `${title} ${author}` : title;
        const apiUrl = `https://openlibrary.org/search.json?q=${encodeURIComponent(query)}&limit=1`;
        const response = await fetch(apiUrl);

        if (response.ok) {
          const data = await response.json();
          const doc = data.docs?.[0];
          if (doc?.cover_i) {
            const coverUrl = `https://covers.openlibrary.org/b/id/${doc.cover_i}-L.jpg`;
            console.log('✓ Cover found via OpenLibrary search (fallback)');
            return coverUrl;
          }
        }
      } catch (e) {
        console.warn('OpenLibrary search failed:', e);
      }
    }

    console.warn('All cover lookup sources failed');
    return null;
  };

  // Triggered manually or on select
  const triggerCoverFetch = async (title: string, author: string, isbn: string) => {
    setIsFetchingCover(true);
    const cover = await findBestCover(title, author, isbn);
    if (cover) {
      setFormData(prev => ({ ...prev, coverUrl: cover }));
    }
    setIsFetchingCover(false);
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
      coverUrl: '',
      // Only populate URL for websites/articles
      url: (initialType === 'WEBSITE' || initialType === 'ARTICLE') ? (draft.url || '') : ''
    }));

    setMode('edit');

    // 2. Automatically fetch cover for Books
    if (initialType === 'BOOK') {
      await triggerCoverFetch(draft.title, draft.author, draft.isbn || '');
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const lentInfo = initialType === 'BOOK' && formData.status === 'Lent Out' && formData.lentToName
      ? { borrowerName: formData.lentToName, lentDate: formData.lentDate || new Date().toISOString().split('T')[0] }
      : undefined;

    // Parse addedAt date from input, or fallback to now
    const addedAtTimestamp = formData.addedAt ? new Date(formData.addedAt).getTime() : Date.now();

    onSave({
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
      coverUrl: formData.coverUrl,
      lentInfo,
      addedAt: addedAtTimestamp
    });
  };

  const getIcon = () => {
    switch (initialType) {
      case 'ARTICLE': return <FileText className="text-indigo-500" size={24} />;
      case 'WEBSITE': return <Globe className="text-indigo-500" size={24} />;
      case 'PERSONAL_NOTE': return <PenTool className="text-indigo-500" size={24} />;
      default: return <BookIcon className="text-indigo-500" size={24} />;
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

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">

        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-white z-10">
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            {mode === 'search' ? (
              <>
                <Search className="text-indigo-500" size={24} />
                Find {initialType === 'ARTICLE' ? 'Article' : 'Book'}
              </>
            ) : (
              <>
                {getIcon()}
                {getTitle()}
              </>
            )}
          </h2>
          <button onClick={onCancel} className="text-slate-400 hover:text-slate-600 p-1 hover:bg-slate-100 rounded-full transition-colors">
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
                className="w-full pl-5 pr-14 py-4 text-lg border-2 border-slate-200 rounded-xl focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 outline-none transition-all placeholder:text-slate-400"
              />
              <button
                type="submit"
                disabled={isSearching || !searchQuery.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:hover:bg-indigo-600 transition-colors"
              >
                {isSearching ? <Loader2 className="animate-spin" size={20} /> : <Search size={20} />}
              </button>
            </form>

            <div className="space-y-3 flex-1 mt-6">
              {searchResults.length > 0 ? (
                <>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Matches Found</p>
                  {searchResults.map((draft, idx) => (
                    <button
                      key={idx}
                      onClick={() => selectItem(draft)}
                      className="w-full text-left p-4 rounded-xl border border-slate-200 hover:border-indigo-300 hover:shadow-md hover:bg-indigo-50/30 transition-all group flex justify-between items-center"
                    >
                      <div>
                        <h3 className="font-bold text-slate-900">{draft.title}</h3>
                        <p className="text-slate-600 text-sm">{draft.author}</p>
                        <div className="flex gap-3 mt-1 text-xs text-slate-400">
                          {draft.publisher && <span>{draft.publisher}</span>}
                          {draft.publishedDate && <span>{draft.publishedDate}</span>}
                          {draft.isbn && <span className="font-mono tracking-tight">ISBN: {draft.isbn}</span>}
                        </div>
                      </div>
                      <ChevronRight className="text-slate-300 group-hover:text-indigo-500" size={20} />
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

            <div className="mt-6 pt-6 border-t border-slate-100 flex justify-center">
              <button
                onClick={() => setMode('edit')}
                className="text-slate-500 hover:text-indigo-600 text-sm font-medium flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <span>Don't see it? Enter details manually</span>
                <SkipForward size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Mode: Edit Form */}
        {mode === 'edit' && (
          <form onSubmit={handleSubmit} className="p-6 overflow-y-auto flex-1">
            {/* Basic Info */}
            <div className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className={isNote ? "md:col-span-2" : "md:col-span-2"}>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Title *</label>
                  <input
                    required
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder={isNote ? "Note Title" : (initialType === 'WEBSITE' ? 'Page Title or Site Name' : 'e.g. The Stranger')}
                  />
                </div>

                {!isNote && (
                  <div className={initialType === 'WEBSITE' ? 'md:col-span-2' : ''}>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      {initialType === 'WEBSITE' ? 'Author / Organization' : 'Author *'}
                    </label>
                    <input
                      required={initialType !== 'WEBSITE'}
                      name="author"
                      value={formData.author}
                      onChange={handleChange}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      placeholder="e.g. Albert Camus"
                    />
                  </div>
                )}

                {isNote && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1 flex items-center gap-1">
                      <Calendar size={14} className="text-slate-400" />
                      Date
                    </label>
                    <input
                      type="date"
                      name="addedAt"
                      value={formData.addedAt}
                      onChange={handleChange}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    />
                  </div>
                )}

                {initialType === 'BOOK' && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Translator</label>
                    <input
                      name="translator"
                      value={formData.translator}
                      onChange={handleChange}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    />
                  </div>
                )}
              </div>

              {!isNote && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {initialType !== 'WEBSITE' && (
                    <div className={initialType === 'ARTICLE' ? 'md:col-span-2' : ''}>
                      <label className="block text-sm font-medium text-slate-700 mb-1">
                        {initialType === 'ARTICLE' ? 'Journal / Publisher' : 'Publisher'}
                      </label>
                      <input
                        name="publisher"
                        value={formData.publisher}
                        onChange={handleChange}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                  )}

                  {initialType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">ISBN</label>
                      <input
                        name="isbn"
                        value={formData.isbn}
                        onChange={handleChange}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 font-mono"
                      />
                    </div>
                  )}

                  {initialType === 'ARTICLE' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Year</label>
                      <input
                        name="publicationYear"
                        value={formData.publicationYear}
                        onChange={handleChange}
                        placeholder="YYYY"
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                  )}

                  {initialType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Shelf Code</label>
                      <input
                        name="code"
                        value={formData.code}
                        onChange={handleChange}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                        placeholder="e.g. A-12"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* URL Field for Website or Article */}
              {(initialType === 'WEBSITE' || initialType === 'ARTICLE') && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">URL</label>
                  <input
                    name="url"
                    value={formData.url}
                    onChange={handleChange}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-indigo-600"
                    placeholder="https://..."
                  />
                </div>
              )}

              {initialType === 'BOOK' && (
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1 flex items-center justify-between">
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
                        className="w-full border border-slate-300 rounded-lg pl-3 pr-24 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm text-slate-600"
                      />
                      <button
                        type="button"
                        onClick={() => triggerCoverFetch(formData.title, formData.author, formData.isbn)}
                        disabled={isFetchingCover || (!formData.title && !formData.isbn)}
                        className="absolute right-1 top-1 bottom-1 px-3 bg-indigo-100 hover:bg-indigo-200 text-indigo-700 rounded text-xs font-semibold flex items-center gap-1 transition-colors"
                        title="Auto-find cover based on Title/ISBN"
                      >
                        {isFetchingCover ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
                        Auto-Find
                      </button>
                    </div>
                    <div className="w-16 h-20 bg-slate-50 rounded-lg border border-slate-200 flex items-center justify-center overflow-hidden flex-shrink-0 shadow-sm relative group">
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
                          <Loader2 size={16} className="animate-spin text-indigo-500" />
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
                      className="text-xs text-slate-400 hover:text-indigo-600 hover:underline flex items-center gap-1"
                    >
                      Manual Search on Google Images <Search size={10} />
                    </a>
                  </div>
                </div>
              )}
            </div>

            <hr className="my-6 border-slate-100" />

            {/* Notes Section moved UP for Personal Notes to prioritize writing */}
            {isNote && (
              <div className="mb-6 flex-1 flex flex-col">
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Content
                </label>
                <textarea
                  name="generalNotes"
                  rows={8}
                  value={formData.generalNotes}
                  onChange={handleChange}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-none leading-relaxed flex-1 font-lora"
                  placeholder="Write your note here..."
                />
              </div>
            )}

            {/* Status & Tags */}
            <div className="space-y-5">
              {!isNote && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Reading Status *</label>
                    <select
                      name="readingStatus"
                      value={formData.readingStatus}
                      onChange={handleChange}
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      <option value="To Read">To Read</option>
                      <option value="Reading">Reading</option>
                      <option value="Finished">Finished</option>
                    </select>
                  </div>

                  {/* Inventory Status - Books Only */}
                  {initialType === 'BOOK' && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Inventory Status *</label>
                      <select
                        name="status"
                        value={formData.status}
                        onChange={handleChange}
                        className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
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
                <label className="block text-sm font-medium text-slate-700 mb-1 flex justify-between">
                  Tags (comma separated)
                  {isNote && (
                    <button
                      type="button"
                      onClick={handleGenerateTags}
                      disabled={isGeneratingTags || !formData.generalNotes}
                      className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 disabled:opacity-50"
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
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
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

            <hr className="my-6 border-slate-100" />

            {/* Notes (Only for non-notes) */}
            {!isNote && (
              <div className="mb-4 flex-1 flex flex-col">
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  General Notes & Summary
                </label>
                <textarea
                  name="generalNotes"
                  rows={4}
                  value={formData.generalNotes}
                  onChange={handleChange}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-none leading-relaxed flex-1"
                  placeholder={initialType === 'WEBSITE' ? "Why did you save this website?" : "Your thoughts..."}
                />
              </div>
            )}

            <div className="flex justify-between items-center pt-2 mt-auto">
              {!initialData && initialType !== 'WEBSITE' && !isNote && (
                <button
                  type="button"
                  onClick={() => setMode('search')}
                  className="text-sm text-slate-500 hover:text-indigo-600 underline decoration-indigo-200 hover:decoration-indigo-600"
                >
                  Back to Search
                </button>
              )}
              <div className="flex gap-3 ml-auto">
                <button
                  type="button"
                  onClick={onCancel}
                  className="px-5 py-2 text-slate-700 hover:bg-slate-100 rounded-lg transition-colors font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-indigo-600 text-white hover:bg-indigo-700 rounded-lg shadow transition-colors font-medium"
                >
                  Save {initialType === 'ARTICLE' ? 'Article' : (initialType === 'WEBSITE' ? 'Website' : (initialType === 'PERSONAL_NOTE' ? 'Note' : 'Book'))}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
