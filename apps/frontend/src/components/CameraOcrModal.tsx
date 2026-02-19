import React, { useState, useRef, useEffect } from 'react';
import { X, Camera, Loader2, Check, RotateCcw } from 'lucide-react';
import { extractTextFromImage } from '../services/ocrService';
import { normalizeImageForOcr } from '../lib/ocrHelpers';

interface CameraOcrModalProps {
  open: boolean;
  onClose: () => void;
  onApply: (text: string) => void;
  onProcessingChange: (processing: boolean) => void;
  onErrorChange: (error: string | null) => void;
  onDraftChange: (text: string) => void;
}

export const CameraOcrModal: React.FC<CameraOcrModalProps> = ({
  open,
  onClose,
  onApply,
  onProcessingChange,
  onErrorChange,
  onDraftChange
}) => {
  const [image, setImage] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [resultText, setResultText] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setImage(null);
      setResultText('');
      setProgress(0);
      setIsProcessing(false);
      onProcessingChange(false);
      onErrorChange(null);
      onDraftChange('');

      // Auto-open camera on mobile when modal opens
      setTimeout(() => {
        fileInputRef.current?.click();
      }, 100);
    }
  }, [open, onProcessingChange, onErrorChange, onDraftChange]);

  if (!open) return null;

  const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = async (event) => {
        setImage(event.target?.result as string);
        await processImage(file);
      };
      reader.readAsDataURL(file);
    }
  };

  const processImage = async (file: File) => {
    setIsProcessing(true);
    onProcessingChange(true);
    onErrorChange(null);
    setProgress(0);

    try {
      // Step 1: Normalize image (resize/compress)
      const normalizedBlob = await normalizeImageForOcr(file);

      // Step 2: OCR
      const result = await extractTextFromImage(normalizedBlob as File, (p) => setProgress(p));
      setResultText(result.text);
      onDraftChange(result.text);
    } catch (error) {
      console.error('OCR Error:', error);
      const msg = 'Metin okunamadı. Lütfen ışığı ve açıyı kontrol edip tekrar deneyin.';
      onErrorChange(msg);
      alert(msg);
    } finally {
      setIsProcessing(false);
      onProcessingChange(false);
    }
  };

  const handleConfirm = () => {
    onApply(resultText);
    onClose();
  };

  const handleRetry = () => {
    setImage(null);
    setResultText('');
    setProgress(0);
    onDraftChange('');
    if (fileInputRef.current) fileInputRef.current.value = '';
    fileInputRef.current?.click();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-slate-900 w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-100 dark:border-white/10">
          <h3 className="font-bold text-slate-800 dark:text-white flex items-center gap-2">
            <Camera size={20} className="text-primary dark:text-orange-500" />
            Metin Tara (OCR)
          </h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-white/5 rounded-full transition-colors">
            <X size={20} className="text-slate-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!image && (
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-12 flex flex-col items-center justify-center gap-4 cursor-pointer hover:border-primary/50 dark:hover:border-orange-500/50 transition-colors"
            >
              <div className="w-16 h-16 bg-primary/10 dark:bg-orange-500/10 rounded-full flex items-center justify-center text-primary dark:text-orange-500">
                <Camera size={32} />
              </div>
              <div className="text-center">
                <p className="font-semibold text-slate-700 dark:text-slate-200">Kamerayı Aç</p>
                <p className="text-sm text-slate-500">Kitap sayfasının fotoğrafını çekin</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={handleCapture}
              />
            </div>
          )}

          {image && (
            <div className="space-y-4">
              <div className="relative aspect-[3/4] bg-black rounded-lg overflow-hidden border border-slate-200 dark:border-white/10 shadow-inner">
                <img src={image} alt="Captured" className="w-full h-full object-contain" />

                {isProcessing && (
                  <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center text-white p-6 text-center backdrop-blur-[2px]">
                    <Loader2 size={48} className="animate-spin mb-4 text-primary dark:text-orange-500" />
                    <p className="font-bold text-lg mb-2">Metin İşleniyor...</p>
                    <div className="w-full max-w-xs bg-white/20 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-primary dark:bg-orange-500 h-full transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <p className="mt-2 text-sm font-medium">%{progress}</p>
                    <p className="mt-4 text-[10px] text-white/60">Bu işlem cihazınızın hızına bağlı olarak 5-10 saniye sürebilir.</p>
                  </div>
                )}
              </div>

              {!isProcessing && resultText && (
                <div className="space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
                  <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Okunan Metin</label>
                  <textarea
                    value={resultText}
                    onChange={(e) => {
                      setResultText(e.target.value);
                      onDraftChange(e.target.value);
                    }}
                    className="w-full h-40 border border-slate-200 dark:border-white/10 rounded-xl p-3 text-sm bg-slate-50 dark:bg-white/5 text-slate-800 dark:text-white focus:ring-2 focus:ring-primary/20 outline-none resize-none font-lora"
                  />
                  <p className="text-[10px] text-slate-400 italic text-right">* Hataları buradan düzeltebilirsiniz.</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 dark:border-white/10 flex gap-3">
          {image && !isProcessing && (
            <>
              <button
                onClick={handleRetry}
                className="flex-1 py-3 px-4 border border-slate-200 dark:border-white/10 rounded-xl text-slate-600 dark:text-slate-300 font-semibold hover:bg-slate-50 dark:hover:bg-white/5 transition-colors flex items-center justify-center gap-2"
              >
                <RotateCcw size={18} />
                Tekrar
              </button>
              <button
                onClick={handleConfirm}
                disabled={!resultText}
                className="flex-[1.5] py-3 px-4 bg-primary dark:bg-orange-600 text-white rounded-xl font-bold hover:opacity-90 transition-all shadow-lg shadow-primary/20 dark:shadow-orange-600/20 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Check size={18} />
                Highlight'a Ekle
              </button>
            </>
          )}
          {!image && (
            <button
              onClick={onClose}
              className="w-full py-3 text-slate-500 font-medium hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
            >
              Vazgeç
            </button>
          )}
        </div>
      </div>

      {/* Hidden input for retries */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleCapture}
      />
    </div>
  );
};
