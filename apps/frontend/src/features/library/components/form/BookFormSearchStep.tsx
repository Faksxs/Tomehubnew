import React from 'react';
import { Camera, ChevronRight, Loader2, Plus, Search, SkipForward } from 'lucide-react';
import { BarcodeScanner } from '../../../../components/BarcodeScanner';
import { ItemDraft } from '../../../../services/geminiService';
import { MediaSearchItem } from '../../../../services/backendApiService';
import { ResourceType } from '../../../../types';

interface BookFormSearchStepProps {
    isMedia: boolean;
    mediaLibraryEnabled: boolean;
    resourceType: ResourceType;
    searchQuery: string;
    onSearchQueryChange: (value: string) => void;
    isSearching: boolean;
    onSubmitSearch: (e: React.FormEvent) => void;
    onResourceTypeChange: (value: ResourceType) => void;
    showScanner: boolean;
    onOpenScanner: () => void;
    onCloseScanner: () => void;
    onBarcodeDetected: (code: string) => void;
    mediaPickerError: string;
    searchError: string;
    searchResults: Array<ItemDraft & Partial<MediaSearchItem>>;
    onSelectItem: (draft: ItemDraft & Partial<MediaSearchItem>) => void;
    hasMoreResults: boolean;
    onLoadMore: () => void;
    onManualEntry: () => void;
}

export const BookFormSearchStep: React.FC<BookFormSearchStepProps> = ({
    isMedia,
    mediaLibraryEnabled,
    resourceType,
    searchQuery,
    onSearchQueryChange,
    isSearching,
    onSubmitSearch,
    onResourceTypeChange,
    showScanner,
    onOpenScanner,
    onCloseScanner,
    onBarcodeDetected,
    mediaPickerError,
    searchError,
    searchResults,
    onSelectItem,
    hasMoreResults,
    onLoadMore,
    onManualEntry,
}) => {
    return (
        <div className="p-6 flex flex-col h-full overflow-y-auto">
            {isMedia && mediaLibraryEnabled && (
                <div className="mb-3">
                    <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Type</label>
                    <select
                        value={resourceType}
                        onChange={(e) => onResourceTypeChange(e.target.value as ResourceType)}
                        className="w-full border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#CC561E] focus:border-[#CC561E] bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                    >
                        <option value="MOVIE">Movie</option>
                        <option value="SERIES">Series</option>
                    </select>
                </div>
            )}

            <form onSubmit={onSubmitSearch} className="relative mb-4">
                <input
                    autoFocus
                    type="text"
                    value={searchQuery}
                    onChange={(e) => onSearchQueryChange(e.target.value)}
                    placeholder={isMedia ? 'Enter title, director, cast...' : (resourceType === 'ARTICLE' ? 'Enter Title, DOI, Author...' : 'Enter Title, ISBN, Author...')}
                    className="w-full pl-5 pr-28 py-4 text-lg border-2 border-slate-200 dark:border-slate-700 rounded-xl focus:border-[#CC561E] dark:focus:border-[#CC561E] focus:ring-4 focus:ring-[#CC561E]/10 outline-none transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                    {resourceType === 'BOOK' && (
                        <button
                            type="button"
                            onClick={onOpenScanner}
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
                    onDetected={onBarcodeDetected}
                    onClose={onCloseScanner}
                />
            )}

            {mediaPickerError && (
                <p className="mt-2 text-xs text-red-600 dark:text-red-400">{mediaPickerError}</p>
            )}
            {!isMedia && searchError && (
                <p className="mt-2 text-xs text-red-600 dark:text-red-400">{searchError}</p>
            )}

            <div className="space-y-3 flex-1 mt-6">
                {searchResults.length > 0 ? (
                    <>
                        <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Matches Found</p>
                        {searchResults.map((draft, idx) => (
                            <button
                                key={idx}
                                onClick={() => onSelectItem(draft)}
                                className="w-full text-left p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-[#CC561E]/50 dark:hover:border-[#CC561E]/50 hover:shadow-md hover:bg-[rgba(204,86,30,0.05)] dark:hover:bg-[rgba(204,86,30,0.1)] transition-all group flex justify-between items-center"
                            >
                                <div>
                                    <h3 className="font-bold text-slate-900 dark:text-white">
                                        {draft.originalTitle && draft.originalTitle.trim().toLowerCase() !== draft.title.trim().toLowerCase()
                                            ? `${draft.title} (${draft.originalTitle})`
                                            : draft.title}
                                    </h3>
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

                        {isMedia && hasMoreResults && (
                            <button
                                type="button"
                                onClick={onLoadMore}
                                disabled={isSearching}
                                className="w-full py-3 px-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-[#CC561E] hover:text-[#CC561E] dark:hover:border-[#f3a47b] dark:hover:text-[#f3a47b] transition-all flex items-center justify-center gap-2 font-medium"
                            >
                                {isSearching ? (
                                    <>
                                        <Loader2 size={18} className="animate-spin" />
                                        <span>Daha Fazla Yukleniyor...</span>
                                    </>
                                ) : (
                                    <>
                                        <Plus size={18} />
                                        <span>Daha Fazla Yukle</span>
                                    </>
                                )}
                            </button>
                        )}
                    </>
                ) : (
                    !isSearching && searchQuery && !(isMedia ? mediaPickerError : searchError) && (
                        <div className="text-center py-10 text-slate-500">
                            <p>{isMedia ? `No TMDb results found matching "${searchQuery}".` : `No AI results found matching "${searchQuery}".`}</p>
                            <p className="text-sm mt-2">Try entering details manually.</p>
                        </div>
                    )
                )}
            </div>

            <div className="mt-6 pt-6 border-t border-slate-100 dark:border-slate-800 flex justify-center">
                <button
                    onClick={onManualEntry}
                    className="text-slate-500 dark:text-slate-400 hover:text-[#CC561E] dark:hover:text-[#f3a47b] text-sm font-medium flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                    <span>Don't see it? Enter details manually</span>
                    <SkipForward size={16} />
                </button>
            </div>
        </div>
    );
};
