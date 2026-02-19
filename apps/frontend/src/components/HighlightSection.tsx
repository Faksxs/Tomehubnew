import React, { useState } from 'react';
import { Highlight } from '../types';
import { Plus, Trash2, Quote, MapPin, FileText, Edit2, Save, X, StickyNote, Calendar, Sparkles, Loader2, Hash, Camera } from 'lucide-react';
import { generateTagsForNote } from '../services/geminiService';
import { isInsightType, normalizeHighlightType } from '../lib/highlightType';
import { CameraOcrModal } from './CameraOcrModal';
import { appendRecognizedText, shouldEnableMobileCameraOcr } from '../lib/ocrHelpers';

interface HighlightSectionProps {
  highlights: Highlight[];
  onUpdate: (highlights: Highlight[]) => void;
  autoEditHighlightId?: string; // Optional: auto-open edit for this highlight
}

export const HighlightSection: React.FC<HighlightSectionProps> = ({ highlights, onUpdate, autoEditHighlightId }) => {
  // State for managing the form
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<Partial<Highlight>>({});
  const [entryType, setEntryType] = useState<'highlight' | 'insight'>('highlight');
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [mobileCameraEnabled, setMobileCameraEnabled] = useState(false);
  const [isOcrProcessing, setIsOcrProcessing] = useState(false);
  const [ocrTextDraft, setOcrTextDraft] = useState('');
  const [ocrError, setOcrError] = useState<string | null>(null);

  // New State for Date and Tags
  const [dateInput, setDateInput] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [isGeneratingTags, setIsGeneratingTags] = useState(false);

  // Auto-open edit mode if autoEditHighlightId is provided
  React.useEffect(() => {
    if (autoEditHighlightId) {
      const highlight = highlights.find(h => h.id === autoEditHighlightId);
      if (highlight) {
        handleEdit(highlight);
      }
    }
  }, [autoEditHighlightId]); // Only run when autoEditHighlightId changes

  React.useEffect(() => {
    const evaluateMobileOcr = () => {
      if (typeof window === 'undefined') {
        setMobileCameraEnabled(false);
        return;
      }
      const hasCoarsePointer =
        typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches;
      const maxTouchPoints = typeof navigator !== 'undefined' ? Number(navigator.maxTouchPoints || 0) : 0;
      setMobileCameraEnabled(
        shouldEnableMobileCameraOcr({
          viewportWidth: window.innerWidth || 0,
          maxTouchPoints,
          hasCoarsePointer,
        })
      );
    };

    evaluateMobileOcr();
    window.addEventListener('resize', evaluateMobileOcr);
    return () => window.removeEventListener('resize', evaluateMobileOcr);
  }, []);

  const handleAddNew = () => {
    setEditingId(null);
    setFormData({});
    setEntryType('highlight');
    // Default to today
    setDateInput(new Date().toISOString().split('T')[0]);
    setTagsInput('');
    setIsCameraOpen(false);
    setOcrError(null);
    setOcrTextDraft('');
    setIsFormOpen(true);
  };

  const handleEdit = (h: Highlight) => {
    setEditingId(h.id);
    setFormData({ ...h });
    setEntryType(normalizeHighlightType(h.type));
    // Initialize date and tags
    setDateInput(new Date(h.createdAt).toISOString().split('T')[0]);
    setTagsInput(h.tags ? h.tags.join(', ') : '');
    setIsCameraOpen(false);
    setOcrError(null);
    setOcrTextDraft('');
    setIsFormOpen(true);
  };

  const handleCancel = () => {
    setIsFormOpen(false);
    setEditingId(null);
    setFormData({});
    setTagsInput('');
    setDateInput('');
    setIsCameraOpen(false);
    setOcrError(null);
    setOcrTextDraft('');
    setIsOcrProcessing(false);
  };

  const handleApplyOcrText = React.useCallback((recognizedText: string) => {
    setFormData((prev) => ({
      ...prev,
      text: appendRecognizedText(String(prev.text || ''), recognizedText),
    }));
    setOcrTextDraft(recognizedText);
    setOcrError(null);
    setIsCameraOpen(false);
  }, []);

  const handleGenerateTags = async () => {
    if (!formData.text) return;
    setIsGeneratingTags(true);

    // Combine text and comment for context
    const contentToAnalyze = `"${formData.text}"\n${formData.comment ? `Context: ${formData.comment}` : ''}`;

    const tags = await generateTagsForNote(contentToAnalyze);

    if (tags.length > 0) {
      const currentTags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(Boolean) : [];
      // Merge and deduplicate
      const uniqueTags = Array.from(new Set([...currentTags, ...tags]));
      setTagsInput(uniqueTags.join(', '));
    }
    setIsGeneratingTags(false);
  };

  const handleSave = () => {
    if (!formData.text) return;

    const tagsArray = tagsInput.split(',').map(t => t.trim()).filter(t => t.length > 0);
    const timestamp = dateInput ? new Date(dateInput).getTime() : Date.now();

    const highlightData: Highlight = {
      id: editingId || Date.now().toString(),
      text: formData.text,
      type: entryType,
      pageNumber: formData.pageNumber,
      paragraphNumber: formData.paragraphNumber,
      chapterTitle: formData.chapterTitle,
      comment: formData.comment,
      createdAt: timestamp, // Use editable date
      tags: tagsArray // Add tags
    };

    if (editingId) {
      // Update existing highlight
      const updatedHighlights = highlights.map(h =>
        h.id === editingId ? highlightData : h
      );
      onUpdate(updatedHighlights);
    } else {
      // Create new highlight
      onUpdate([highlightData, ...highlights]);
    }

    handleCancel();
  };

  const handleDelete = (id: string) => {
    if (window.confirm('Delete this item?')) {
      onUpdate(highlights.filter(h => h.id !== id));
    }
  };

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Add Button - Hidden when form is open */}
      {!isFormOpen && (
        <button
          onClick={handleAddNew}
          className="w-full py-3 md:py-4 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl text-slate-500 dark:text-slate-400 hover:border-[#262D40]/24 hover:text-[#262D40] hover:bg-[#262D40]/30 dark:hover:bg-white/5 transition-all flex flex-col items-center gap-1 md:gap-2"
        >
          <Plus size={20} className="md:w-6 md:h-6" />
          <span className="text-sm md:text-base font-medium">Add Highlight or Insights</span>
        </button>
      )}

      {/* Form (Add or Edit) */}
      {isFormOpen && (
        <div className="bg-white dark:bg-slate-900 p-4 md:p-6 rounded-xl shadow-lg border border-[#262D40]/8 dark:border-white/10 animate-in fade-in zoom-in-95 duration-200 relative ring-1 ring-[#262D40]/5 dark:ring-white/5">
          <div className="flex items-center justify-between mb-3 md:mb-4">
            <h4 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 text-sm md:text-base">
              {editingId ? <Edit2 size={16} className="md:w-[18px] md:h-[18px] text-[#262D40] dark:text-orange-500" /> : <Plus size={16} className="md:w-[18px] md:h-[18px] text-[#262D40] dark:text-orange-500" />}
              {editingId ? (entryType === 'highlight' ? 'Edit Highlight' : 'Edit Note') : 'New Entry'}
            </h4>
            <div className="flex items-center gap-2">
              {entryType === 'highlight' && mobileCameraEnabled && (
                <button
                  type="button"
                  onClick={() => {
                    setOcrError(null);
                    setOcrTextDraft('');
                    setIsCameraOpen(true);
                  }}
                  disabled={isOcrProcessing}
                  className="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700 transition-colors hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-sky-700 dark:bg-sky-950/35 dark:text-sky-200 dark:hover:bg-sky-950/55"
                  title="Kamera ile metin tara"
                >
                  {isOcrProcessing ? <Loader2 size={12} className="animate-spin" /> : <Camera size={12} />}
                  Tara
                </button>
              )}
              <button onClick={handleCancel} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                <X size={18} className="md:w-5 md:h-5" />
              </button>
            </div>
          </div>

          {/* Type Toggle */}
          <div className="flex bg-[#F3F5FA] dark:bg-white/5 p-1 rounded-lg mb-4 md:mb-5">
            <button
              type="button"
              onClick={() => {
                if (entryType !== 'highlight') {
                  setEntryType('highlight');
                  setFormData({}); // Clear form when switching
                  setTagsInput('');
                  setOcrError(null);
                  setOcrTextDraft('');
                }
              }}
              className={`flex-1 flex items-center justify-center gap-2 py-1.5 md:py-2 text-xs md:text-sm font-medium rounded-md transition-all ${entryType === 'highlight'
                ? 'bg-white dark:bg-white/10 text-[#262D40] dark:text-orange-500 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                }`}
            >
              <Quote size={14} className="md:w-4 md:h-4" />
              Highlight
            </button>
            <button
              type="button"
              onClick={() => {
                if (entryType !== 'insight') {
                  setEntryType('insight');
                  setFormData({}); // Clear form when switching
                  setTagsInput('');
                  setIsCameraOpen(false);
                  setOcrError(null);
                  setOcrTextDraft('');
                }
              }}
              className={`flex-1 flex items-center justify-center gap-2 py-1.5 md:py-2 text-xs md:text-sm font-medium rounded-md transition-all ${entryType === 'insight'
                ? 'bg-white dark:bg-white/10 text-[#262D40] dark:text-orange-500 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                }`}
            >
              <StickyNote size={14} className="md:w-4 md:h-4" />
              Insights
            </button>
          </div>

          <div className="space-y-3 md:space-y-4">
            <div>
              <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase">
                {entryType === 'highlight' ? 'Highlight Text *' : 'Insight Content *'}
              </label>
              <textarea
                autoFocus
                rows={8}
                className={`w-full border rounded-lg p-2 md:p-3 text-sm md:text-base text-slate-800 dark:text-white focus:ring-2 focus:ring-[#262D40]/30 dark:focus:ring-orange-500/30 focus:border-[#262D40]/30 dark:focus:border-orange-500/30 font-lora ${entryType === 'highlight' ? 'bg-[#F3F5FA] border-[#E6EAF2] dark:bg-slate-800/50 dark:border-white/10' : 'bg-[#F3F5FA] border-[#E6EAF2] dark:bg-slate-800/50 dark:border-white/10'
                  }`}
                placeholder={entryType === 'highlight' ? "Type the text exactly as it appears..." : "Write your thoughts, summary, or key takeaway..."}
                value={formData.text || ''}
                onChange={e => setFormData(prev => ({ ...prev, text: e.target.value }))}
              ></textarea>
              {entryType === 'highlight' && ocrTextDraft && (
                <p className="mt-1 text-[10px] md:text-xs text-sky-700 dark:text-sky-300">
                  OCR metni eklendi. Kaydetmeden once metni kontrol edebilirsiniz.
                </p>
              )}
              {entryType === 'highlight' && ocrError && (
                <p className="mt-1 text-[10px] md:text-xs text-red-600 dark:text-red-400">{ocrError}</p>
              )}
            </div>

            {/* Comment input only for Highlights */}
            {entryType === 'highlight' && (
              <div>
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase">Comment</label>
                <input
                  type="text"
                  className="w-full border border-[#E6EAF2] dark:border-white/10 rounded-lg p-2 text-xs md:text-sm bg-white dark:bg-slate-800/50 text-slate-800 dark:text-white focus:ring-2 focus:ring-orange-500/30"
                  placeholder="Why is this quote important?"
                  value={formData.comment || ''}
                  onChange={e => setFormData(prev => ({ ...prev, comment: e.target.value }))}
                />
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
              <div>
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase">Page #</label>
                <input
                  type="number"
                  className="w-full border border-[#E6EAF2] dark:border-white/10 rounded-lg p-2 text-xs md:text-sm bg-white dark:bg-slate-800/50 text-slate-800 dark:text-white focus:ring-2 focus:ring-orange-500/30"
                  value={formData.pageNumber || ''}
                  onChange={e => setFormData(prev => ({ ...prev, pageNumber: parseInt(e.target.value) || undefined }))}
                />
              </div>
              <div>
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase">Paragraph #</label>
                <input
                  type="number"
                  className="w-full border border-[#E6EAF2] dark:border-white/10 rounded-lg p-2 text-xs md:text-sm bg-white dark:bg-slate-800/50 text-slate-800 dark:text-white focus:ring-2 focus:ring-orange-500/30"
                  value={formData.paragraphNumber || ''}
                  onChange={e => setFormData(prev => ({ ...prev, paragraphNumber: parseInt(e.target.value) || undefined }))}
                />
              </div>
              <div className="col-span-2 md:col-span-1">
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase">Chapter</label>
                <input
                  type="text"
                  className="w-full border border-[#E6EAF2] dark:border-white/10 rounded-lg p-2 text-xs md:text-sm bg-white dark:bg-slate-800/50 text-slate-800 dark:text-white focus:ring-2 focus:ring-orange-500/30"
                  placeholder="Title or No."
                  value={formData.chapterTitle || ''}
                  onChange={e => setFormData(prev => ({ ...prev, chapterTitle: e.target.value }))}
                />
              </div>
            </div>

            {/* Date & Tags Section */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4 pt-2 border-t border-slate-50 dark:border-white/5">
              <div className="md:col-span-1">
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase flex items-center gap-1">
                  <Calendar size={10} className="md:w-3 md:h-3" /> Date
                </label>
                <input
                  type="date"
                  value={dateInput}
                  onChange={(e) => setDateInput(e.target.value)}
                  className="w-full border border-[#E6EAF2] dark:border-white/10 rounded-lg p-2 text-xs md:text-sm bg-white dark:bg-slate-800/50 text-slate-800 dark:text-white focus:ring-2 focus:ring-orange-500/30"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 dark:text-slate-400 mb-1 uppercase flex items-center justify-between">
                  <span>Tags</span>
                  <button
                    type="button"
                    onClick={handleGenerateTags}
                    disabled={isGeneratingTags || !formData.text}
                    className="text-[#262D40] dark:text-orange-500 hover:text-[#262D40] dark:hover:text-orange-400 flex items-center gap-1 disabled:opacity-50 text-[10px] font-bold tracking-wide"
                  >
                    {isGeneratingTags ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                    AI AUTO-TAG
                  </button>
                </label>
                <input
                  type="text"
                  value={tagsInput}
                  onChange={(e) => setTagsInput(e.target.value)}
                  placeholder="Separate with commas..."
                  className="w-full border border-[#E6EAF2] dark:border-white/10 rounded-lg p-2 text-xs md:text-sm bg-white dark:bg-slate-800/50 text-slate-800 dark:text-white focus:ring-2 focus:ring-orange-500/30"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2 mt-2">
              <button
                onClick={handleCancel}
                className="px-3 md:px-4 py-2 text-xs md:text-sm text-slate-600 dark:text-slate-400 hover:bg-[#F3F5FA] dark:hover:bg-white/5 rounded-lg flex items-center gap-2"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!formData.text}
                className="px-3 md:px-4 py-2 text-xs md:text-sm bg-[#262D40]/40 dark:bg-orange-600/40 text-white rounded-lg hover:bg-[#262D40]/55 dark:hover:bg-orange-600/60 disabled:opacity-50 shadow-sm flex items-center gap-2"
              >
                <Save size={14} className="md:w-4 md:h-4" />
                {editingId ? 'Update Entry' : 'Save Entry'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* List of Highlights/Notes */}
      <div className="space-y-3 md:space-y-4">
        {highlights.map((h) => {
          const isNote = isInsightType(h.type);
          return (
            <div
              key={h.id}
              className={`p-3 md:p-6 rounded-xl border transition-all relative group ${isNote
                ? 'bg-white dark:bg-slate-900/50 border-[#E6EAF2] dark:border-white/10 hover:border-[#262D40]/12 dark:hover:border-orange-500/30 hover:shadow-md'
                : 'bg-white dark:bg-slate-900/50 border-[#E6EAF2] dark:border-white/10 hover:border-[#262D40]/12 dark:hover:border-orange-500/30 hover:shadow-md'
                }`}
            >
              {/* Action Buttons: Transparent & Compact on Mobile */}
              <div className="absolute top-1 right-1 md:top-4 md:right-4 flex gap-0.5 md:gap-2 md:bg-white/80 md:dark:bg-slate-800/90 md:backdrop-blur-sm p-0 md:p-1 rounded-lg md:shadow-sm md:border md:border-[#E6EAF2] md:dark:border-white/10 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity z-10">
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleEdit(h); }}
                  className="p-1.5 text-slate-400/70 dark:text-slate-500/70 hover:text-[#262D40] dark:hover:text-orange-500 hover:bg-[#262D40]/5 dark:hover:bg-white/5 rounded-md transition-colors"
                  title="Edit"
                >
                  <Edit2 size={14} className="md:w-4 md:h-4" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleDelete(h.id); }}
                  className="p-1.5 text-slate-400/70 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                  title="Delete"
                >
                  <Trash2 size={14} className="md:w-4 md:h-4" />
                </button>
              </div>

              {/* Content */}
              <div className="flex gap-3 md:gap-4">
                <div className="flex-shrink-0 mt-0.5 md:mt-1">
                  {isNote ? (
                    <StickyNote size={16} className="text-[#262D40]/82 fill-[#262D40]/85 md:w-5 md:h-5" />
                  ) : (
                    <Quote size={16} className="text-yellow-400 fill-yellow-200 md:w-5 md:h-5" />
                  )}
                </div>
                <div className="flex-1">
                  <p className={`text-sm md:text-lg leading-relaxed mb-2 md:mb-3 pr-0 md:pr-16 whitespace-pre-wrap font-lora ${isNote ? 'text-slate-700 dark:text-slate-300' : 'text-slate-900 dark:text-white'}`}>
                    {h.text}
                  </p>

                  <div className="flex flex-wrap items-center gap-2 md:gap-3 text-[10px] md:text-xs text-slate-500 dark:text-slate-400 mb-2">
                    {(h.pageNumber || h.paragraphNumber) && (
                      <div className="flex items-center gap-1 px-1.5 py-0.5 md:px-2 md:py-1 rounded border bg-[#F3F5FA] dark:bg-white/5 border-[#E6EAF2] dark:border-white/10 text-slate-600 dark:text-slate-400">
                        <MapPin size={10} className="md:w-3 md:h-3" />
                        {h.pageNumber && <span>Pg {h.pageNumber}</span>}
                        {h.pageNumber && h.paragraphNumber && <span>•</span>}
                        {h.paragraphNumber && <span>Para {h.paragraphNumber}</span>}
                      </div>
                    )}

                    {h.chapterTitle && (
                      <div className="flex items-center gap-1">
                        <FileText size={10} className="md:w-3 md:h-3" />
                        <span>{h.chapterTitle}</span>
                      </div>
                    )}

                    <div className="flex items-center gap-1 ml-auto">
                      <Calendar size={10} className="md:w-3 md:h-3" />
                      <span>{new Date(h.createdAt).toLocaleDateString()}</span>
                    </div>
                  </div>

                  {/* Tags for Highlights */}
                  {h.tags && h.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 md:gap-2 mb-2">
                      {h.tags.map((tag, i) => (
                        <span key={i} className="px-1.5 py-0.5 bg-[#F3F5FA] dark:bg-white/5 border border-[#E6EAF2] dark:border-white/10 rounded text-[9px] md:text-[10px] text-slate-500 dark:text-slate-400 flex items-center gap-0.5">
                          <Hash size={8} /> {tag}
                        </span>
                      ))}
                    </div>
                  )}

                  {h.comment && (
                    <div className="mt-2 md:mt-3 pl-3 md:pl-4 border-l-2 border-[#E6EAF2] dark:border-white/10 py-0.5 md:py-1">
                      <p className="text-xs md:text-sm text-slate-600 dark:text-slate-400 italic">{h.comment}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {highlights.length === 0 && !isFormOpen && (
          <div className="text-center py-8 md:py-12 text-slate-400">
            <p className="text-xs md:text-base">No highlights or insights added yet.</p>
          </div>
        )}
      </div>

      <CameraOcrModal
        open={isCameraOpen}
        onClose={() => setIsCameraOpen(false)}
        onApply={handleApplyOcrText}
        onProcessingChange={setIsOcrProcessing}
        onErrorChange={setOcrError}
        onDraftChange={setOcrTextDraft}
      />
    </div>
  );
};
