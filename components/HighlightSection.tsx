import React, { useState } from 'react';
import { Highlight } from '../types';
import { Plus, Trash2, Quote, MapPin, FileText, Edit2, Save, X, StickyNote, Calendar, Sparkles, Loader2, Hash } from 'lucide-react';
import { generateTagsForNote } from '../services/geminiService';

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
  const [entryType, setEntryType] = useState<'highlight' | 'note'>('highlight');

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

  const handleAddNew = () => {
    setEditingId(null);
    setFormData({});
    setEntryType('highlight');
    // Default to today
    setDateInput(new Date().toISOString().split('T')[0]);
    setTagsInput('');
    setIsFormOpen(true);
  };

  const handleEdit = (h: Highlight) => {
    setEditingId(h.id);
    setFormData({ ...h });
    setEntryType(h.type || 'highlight');
    // Initialize date and tags
    setDateInput(new Date(h.createdAt).toISOString().split('T')[0]);
    setTagsInput(h.tags ? h.tags.join(', ') : '');
    setIsFormOpen(true);
  };

  const handleCancel = () => {
    setIsFormOpen(false);
    setEditingId(null);
    setFormData({});
    setTagsInput('');
    setDateInput('');
  };

  const handleGenerateTags = async () => {
    if (!formData.text) return;
    setIsGeneratingTags(true);

    // Combine text and note for context
    const contentToAnalyze = `"${formData.text}"\n${formData.note ? `Context: ${formData.note}` : ''}`;

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
      note: formData.note,
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
          className="w-full py-3 md:py-4 border-2 border-dashed border-slate-300 rounded-xl text-slate-500 hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50/30 transition-all flex flex-col items-center gap-1 md:gap-2"
        >
          <Plus size={20} className="md:w-6 md:h-6" />
          <span className="text-sm md:text-base font-medium">Add Highlight or Note</span>
        </button>
      )}

      {/* Form (Add or Edit) */}
      {isFormOpen && (
        <div className="bg-white p-4 md:p-6 rounded-xl shadow-lg border border-indigo-100 animate-in fade-in zoom-in-95 duration-200 relative ring-1 ring-indigo-50">
          <div className="flex items-center justify-between mb-3 md:mb-4">
            <h4 className="font-semibold text-slate-800 flex items-center gap-2 text-sm md:text-base">
              {editingId ? <Edit2 size={16} className="md:w-[18px] md:h-[18px] text-indigo-600" /> : <Plus size={16} className="md:w-[18px] md:h-[18px] text-indigo-600" />}
              {editingId ? (entryType === 'highlight' ? 'Edit Highlight' : 'Edit Note') : 'New Entry'}
            </h4>
            <button onClick={handleCancel} className="text-slate-400 hover:text-slate-600">
              <X size={18} className="md:w-5 md:h-5" />
            </button>
          </div>

          {/* Type Toggle */}
          <div className="flex bg-slate-100 p-1 rounded-lg mb-4 md:mb-5">
            <button
              type="button"
              onClick={() => setEntryType('highlight')}
              className={`flex-1 flex items-center justify-center gap-2 py-1.5 md:py-2 text-xs md:text-sm font-medium rounded-md transition-all ${entryType === 'highlight'
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
                }`}
            >
              <Quote size={14} className="md:w-4 md:h-4" />
              Highlight / Quote
            </button>
            <button
              type="button"
              onClick={() => setEntryType('note')}
              className={`flex-1 flex items-center justify-center gap-2 py-1.5 md:py-2 text-xs md:text-sm font-medium rounded-md transition-all ${entryType === 'note'
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
                }`}
            >
              <StickyNote size={14} className="md:w-4 md:h-4" />
              Personal Note
            </button>
          </div>

          <div className="space-y-3 md:space-y-4">
            <div>
              <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase">
                {entryType === 'highlight' ? 'Quote Text *' : 'Note Content *'}
              </label>
              <textarea
                autoFocus
                rows={8}
                className={`w-full border rounded-lg p-2 md:p-3 text-sm md:text-base text-slate-800 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 font-lora ${entryType === 'highlight' ? 'bg-yellow-50/50 border-yellow-200' : 'bg-slate-50 border-slate-200'
                  }`}
                placeholder={entryType === 'highlight' ? "Type the quote exactly as it appears..." : "Write your thoughts, summary, or key takeaway..."}
                value={formData.text || ''}
                onChange={e => setFormData(prev => ({ ...prev, text: e.target.value }))}
              ></textarea>
            </div>

            {/* Note input only for Highlights */}
            {entryType === 'highlight' && (
              <div>
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase">Personal Comment</label>
                <input
                  type="text"
                  className="w-full border border-slate-200 rounded-lg p-2 text-xs md:text-sm"
                  placeholder="Why is this quote important?"
                  value={formData.note || ''}
                  onChange={e => setFormData(prev => ({ ...prev, note: e.target.value }))}
                />
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
              <div>
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase">Page #</label>
                <input
                  type="number"
                  className="w-full border border-slate-200 rounded-lg p-2 text-xs md:text-sm"
                  value={formData.pageNumber || ''}
                  onChange={e => setFormData(prev => ({ ...prev, pageNumber: parseInt(e.target.value) || undefined }))}
                />
              </div>
              <div>
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase">Paragraph #</label>
                <input
                  type="number"
                  className="w-full border border-slate-200 rounded-lg p-2 text-xs md:text-sm"
                  value={formData.paragraphNumber || ''}
                  onChange={e => setFormData(prev => ({ ...prev, paragraphNumber: parseInt(e.target.value) || undefined }))}
                />
              </div>
              <div className="col-span-2 md:col-span-1">
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase">Chapter</label>
                <input
                  type="text"
                  className="w-full border border-slate-200 rounded-lg p-2 text-xs md:text-sm"
                  placeholder="Title or No."
                  value={formData.chapterTitle || ''}
                  onChange={e => setFormData(prev => ({ ...prev, chapterTitle: e.target.value }))}
                />
              </div>
            </div>

            {/* Date & Tags Section */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4 pt-2 border-t border-slate-50">
              <div className="md:col-span-1">
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase flex items-center gap-1">
                  <Calendar size={10} className="md:w-3 md:h-3" /> Date
                </label>
                <input
                  type="date"
                  value={dateInput}
                  onChange={(e) => setDateInput(e.target.value)}
                  className="w-full border border-slate-200 rounded-lg p-2 text-xs md:text-sm focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-[10px] md:text-xs font-medium text-slate-500 mb-1 uppercase flex items-center justify-between">
                  <span>Tags</span>
                  <button
                    type="button"
                    onClick={handleGenerateTags}
                    disabled={isGeneratingTags || !formData.text}
                    className="text-indigo-600 hover:text-indigo-800 flex items-center gap-1 disabled:opacity-50 text-[10px] font-bold tracking-wide"
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
                  className="w-full border border-slate-200 rounded-lg p-2 text-xs md:text-sm focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2 mt-2">
              <button
                onClick={handleCancel}
                className="px-3 md:px-4 py-2 text-xs md:text-sm text-slate-600 hover:bg-slate-100 rounded-lg flex items-center gap-2"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!formData.text}
                className="px-3 md:px-4 py-2 text-xs md:text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 shadow-sm flex items-center gap-2"
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
          const isNote = h.type === 'note';
          return (
            <div
              key={h.id}
              className={`p-3 md:p-6 rounded-xl border transition-all relative group ${isNote
                ? 'bg-slate-50 border-slate-200 hover:border-indigo-200 hover:shadow-md'
                : 'bg-yellow-50/50 border-yellow-100 hover:border-yellow-300 hover:shadow-md'
                }`}
            >
              {/* Action Buttons */}
              <div className="absolute top-2 right-2 md:top-4 md:right-4 flex gap-1 md:gap-2 bg-white/80 backdrop-blur-sm p-1 rounded-lg shadow-sm border border-slate-100 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity z-10">
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleEdit(h); }}
                  className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                  title="Edit"
                >
                  <Edit2 size={14} className="md:w-4 md:h-4" />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleDelete(h.id); }}
                  className="p-1.5 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                  title="Delete"
                >
                  <Trash2 size={14} className="md:w-4 md:h-4" />
                </button>
              </div>

              {/* Content */}
              <div className="flex gap-3 md:gap-4">
                <div className="flex-shrink-0 mt-0.5 md:mt-1">
                  {isNote ? (
                    <StickyNote size={16} className="text-indigo-400 fill-indigo-50 md:w-5 md:h-5" />
                  ) : (
                    <Quote size={16} className="text-yellow-400 fill-yellow-200 md:w-5 md:h-5" />
                  )}
                </div>
                <div className="flex-1">
                  <p className={`text-sm md:text-lg leading-relaxed mb-2 md:mb-3 pr-14 md:pr-16 whitespace-pre-wrap font-lora ${isNote ? 'text-slate-700' : 'text-slate-900'}`}>
                    {h.text}
                  </p>

                  <div className="flex flex-wrap items-center gap-2 md:gap-3 text-[10px] md:text-xs text-slate-500 mb-2">
                    {(h.pageNumber || h.paragraphNumber) && (
                      <div className={`flex items-center gap-1 px-1.5 py-0.5 md:px-2 md:py-1 rounded border ${isNote ? 'bg-white border-slate-200 text-slate-500' : 'bg-yellow-100/50 border-yellow-100 text-yellow-800'}`}>
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
                        <span key={i} className="px-1.5 py-0.5 bg-white/50 border border-slate-200 rounded text-[9px] md:text-[10px] text-slate-500 flex items-center gap-0.5">
                          <Hash size={8} /> {tag}
                        </span>
                      ))}
                    </div>
                  )}

                  {h.note && (
                    <div className={`mt-2 md:mt-3 pl-3 md:pl-4 border-l-2 py-0.5 md:py-1 ${isNote ? 'border-indigo-200' : 'border-yellow-300'}`}>
                      <p className="text-xs md:text-sm text-slate-600 italic">{h.note}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {highlights.length === 0 && !isFormOpen && (
          <div className="text-center py-8 md:py-12 text-slate-400">
            <p className="text-xs md:text-base">No highlights or notes added yet.</p>
          </div>
        )}
      </div>
    </div>
  );
};