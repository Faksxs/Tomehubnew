import React, { useEffect, useRef, useState } from 'react';
import { X, Camera, Loader2, Check, RotateCcw, ScanLine } from 'lucide-react';
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

type SelectionRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const MIN_SELECTION_SIZE = 0.02;

export const CameraOcrModal: React.FC<CameraOcrModalProps> = ({
  open,
  onClose,
  onApply,
  onProcessingChange,
  onErrorChange,
  onDraftChange,
}) => {
  const [image, setImage] = useState<string | null>(null);
  const [sourceImageBlob, setSourceImageBlob] = useState<Blob | null>(null);
  const [selection, setSelection] = useState<SelectionRect | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [resultText, setResultText] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageOverlayRef = useRef<HTMLDivElement>(null);
  const selectionStartRef = useRef<{ x: number; y: number } | null>(null);
  const selectionRef = useRef<SelectionRect | null>(null);

  const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

  useEffect(() => {
    if (!open) return;

    setImage(null);
    setSourceImageBlob(null);
    setSelection(null);
    setResultText('');
    setProgress(0);
    setIsProcessing(false);
    setIsSelecting(false);

    onProcessingChange(false);
    onErrorChange(null);
    onDraftChange('');

    setTimeout(() => {
      fileInputRef.current?.click();
    }, 100);
  }, [open, onDraftChange, onErrorChange, onProcessingChange]);

  useEffect(() => {
    selectionRef.current = selection;
  }, [selection]);

  if (!open) return null;

  const handleCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSourceImageBlob(file);
    setSelection(null);
    setResultText('');
    onDraftChange('');
    onErrorChange(null);

    const reader = new FileReader();
    reader.onload = (event) => {
      setImage(event.target?.result as string);
    };
    reader.readAsDataURL(file);
  };

  const getNormalizedPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!imageOverlayRef.current) return null;

    const rect = imageOverlayRef.current.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;

    return {
      x: clamp((event.clientX - rect.left) / rect.width, 0, 1),
      y: clamp((event.clientY - rect.top) / rect.height, 0, 1),
    };
  };

  const handleSelectionStart = (event: React.PointerEvent<HTMLDivElement>) => {
    if (isProcessing) return;

    const point = getNormalizedPointer(event);
    if (!point) return;

    event.currentTarget.setPointerCapture(event.pointerId);
    selectionStartRef.current = point;
    setSelection({ x: point.x, y: point.y, width: 0, height: 0 });
    setIsSelecting(true);
  };

  const handleSelectionMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isSelecting || !selectionStartRef.current) return;

    const point = getNormalizedPointer(event);
    if (!point) return;

    const start = selectionStartRef.current;
    const x = Math.min(start.x, point.x);
    const y = Math.min(start.y, point.y);
    const width = Math.abs(point.x - start.x);
    const height = Math.abs(point.y - start.y);

    setSelection({ x, y, width, height });
  };

  const handleSelectionEnd = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isSelecting) return;

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    setIsSelecting(false);
    const current = selectionRef.current;
    if (!current || current.width < MIN_SELECTION_SIZE || current.height < MIN_SELECTION_SIZE) {
      setSelection(null);
    }
  };

  const cropImageBySelection = async (input: Blob, rect: SelectionRect): Promise<Blob> => {
    const imageBitmap = await createImageBitmap(input);

    try {
      const sx = clamp(Math.round(rect.x * imageBitmap.width), 0, imageBitmap.width - 1);
      const sy = clamp(Math.round(rect.y * imageBitmap.height), 0, imageBitmap.height - 1);
      const sw = Math.max(1, Math.round(rect.width * imageBitmap.width));
      const sh = Math.max(1, Math.round(rect.height * imageBitmap.height));
      const safeWidth = Math.min(sw, imageBitmap.width - sx);
      const safeHeight = Math.min(sh, imageBitmap.height - sy);

      const canvas = document.createElement('canvas');
      canvas.width = safeWidth;
      canvas.height = safeHeight;

      const ctx = canvas.getContext('2d');
      if (!ctx) {
        throw new Error('Canvas context is unavailable');
      }

      ctx.drawImage(imageBitmap, sx, sy, safeWidth, safeHeight, 0, 0, safeWidth, safeHeight);

      const blob = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob(resolve, 'image/jpeg', 0.92);
      });

      return blob || input;
    } finally {
      imageBitmap.close();
    }
  };

  const processImage = async (selectedOnly: boolean) => {
    if (!sourceImageBlob) return;

    setIsProcessing(true);
    onProcessingChange(true);
    onErrorChange(null);
    setProgress(0);

    try {
      const cropSource = selectedOnly && selection ? await cropImageBySelection(sourceImageBlob, selection) : sourceImageBlob;
      const normalizedBlob = await normalizeImageForOcr(cropSource);
      const result = await extractTextFromImage(normalizedBlob, (p) => setProgress(p));

      const text = (result.text || '').trim();
      setResultText(text);
      onDraftChange(text);

      if (!text) {
        onErrorChange('Secilen alanda okunabilir metin bulunamadi. Alani degistirip tekrar deneyin.');
      }
    } catch (error) {
      console.error('OCR Error:', error);
      const msg = 'Metin okunamadi. Isigi ve aciyi duzeltip tekrar deneyin.';
      onErrorChange(msg);
      alert(msg);
    } finally {
      setIsProcessing(false);
      onProcessingChange(false);
    }
  };

  const handleRetry = () => {
    setImage(null);
    setSourceImageBlob(null);
    setSelection(null);
    setResultText('');
    setProgress(0);
    setIsSelecting(false);
    onDraftChange('');
    onErrorChange(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  };

  const handleConfirm = () => {
    onApply(resultText);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-slate-900 w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between p-4 border-b border-slate-100 dark:border-white/10">
          <h3 className="font-bold text-slate-800 dark:text-white flex items-center gap-2">
            <Camera size={20} className="text-primary dark:text-orange-500" />
            Metin Tara (OCR)
          </h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-white/5 rounded-full transition-colors" aria-label="Kapat">
            <X size={20} className="text-slate-500" />
          </button>
        </div>

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
                <p className="font-semibold text-slate-700 dark:text-slate-200">Kamerayi Ac</p>
                <p className="text-sm text-slate-500">Sayfayi cekin, sonra metin alanini secin</p>
              </div>
            </div>
          )}

          {image && (
            <div className="space-y-4">
              <div className="relative bg-black rounded-lg border border-slate-200 dark:border-white/10 shadow-inner p-2">
                <div className="relative mx-auto w-fit max-w-full touch-none">
                  <img src={image} alt="Captured" className="block max-h-[58vh] w-auto max-w-full rounded-md" />

                  {!isProcessing && (
                    <div
                      ref={imageOverlayRef}
                      className="absolute inset-0 cursor-crosshair"
                      onPointerDown={handleSelectionStart}
                      onPointerMove={handleSelectionMove}
                      onPointerUp={handleSelectionEnd}
                      onPointerCancel={handleSelectionEnd}
                    >
                      {selection && (
                        <div
                          className="absolute border-2 border-emerald-400 bg-emerald-400/12"
                          style={{
                            left: `${selection.x * 100}%`,
                            top: `${selection.y * 100}%`,
                            width: `${selection.width * 100}%`,
                            height: `${selection.height * 100}%`,
                          }}
                        />
                      )}
                    </div>
                  )}
                </div>

                {isProcessing && (
                  <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center text-white p-6 text-center backdrop-blur-[2px]">
                    <Loader2 size={48} className="animate-spin mb-4 text-primary dark:text-orange-500" />
                    <p className="font-bold text-lg mb-2">Metin Isleniyor...</p>
                    <div className="w-full max-w-xs bg-white/20 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-primary dark:bg-orange-500 h-full transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <p className="mt-2 text-sm font-medium">%{progress}</p>
                    <p className="mt-4 text-[10px] text-white/60">Bu islem cihaz hizina gore 5-10 saniye surebilir.</p>
                  </div>
                )}
              </div>

              {!isProcessing && (
                <div className="space-y-2">
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Metin bolgesini secmek icin gorsel uzerinde surukleyin.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => processImage(true)}
                      disabled={!selection}
                      className="py-2 px-3 rounded-lg bg-emerald-600 text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2"
                    >
                      <ScanLine size={16} />
                      Secili Alani Tara
                    </button>

                    <button
                      type="button"
                      onClick={() => processImage(false)}
                      className="py-2 px-3 rounded-lg border border-slate-200 dark:border-white/10 text-sm font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center justify-center gap-2 hover:bg-slate-50 dark:hover:bg-white/5"
                    >
                      Tum Sayfayi Tara
                    </button>

                    <button
                      type="button"
                      onClick={handleRetry}
                      className="py-2 px-3 rounded-lg border border-slate-200 dark:border-white/10 text-sm font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center justify-center gap-2 hover:bg-slate-50 dark:hover:bg-white/5"
                    >
                      <RotateCcw size={16} />
                      Tekrar Cek
                    </button>
                  </div>
                </div>
              )}

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
                  <p className="text-[10px] text-slate-400 italic text-right">* Hatalari buradan duzeltebilirsiniz.</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-100 dark:border-white/10 flex gap-3">
          {image && !isProcessing && (
            <>
              <button
                onClick={onClose}
                className="flex-1 py-3 px-4 border border-slate-200 dark:border-white/10 rounded-xl text-slate-600 dark:text-slate-300 font-semibold hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
              >
                Kapat
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
              Vazgec
            </button>
          )}
        </div>
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
  );
};
