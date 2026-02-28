import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BrowserMultiFormatReader, DecodeHintType, BarcodeFormat, NotFoundException } from '@zxing/library';
import { X, Camera, Loader2 } from 'lucide-react';

interface BarcodeScannerProps {
    onDetected: (code: string) => void;
    onClose: () => void;
}

const SCAN_FORMATS = [
    BarcodeFormat.EAN_13,
    BarcodeFormat.EAN_8,
    BarcodeFormat.UPC_A,
    BarcodeFormat.UPC_E,
    BarcodeFormat.CODE_128,
];

const NATIVE_DETECTOR_FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'];

type DetectedBarcodeLike = {
    rawValue?: string;
};

type BarcodeDetectorLike = {
    detect: (source: ImageBitmapSource) => Promise<DetectedBarcodeLike[]>;
};

type BarcodeDetectorConstructorLike = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

const normalizeDetectedCode = (raw: string): string => {
    const compact = String(raw || '').replace(/[\s-]/g, '').trim();
    const isbnCharsOnly = compact.replace(/[^0-9Xx]/g, '').toUpperCase();

    if (isbnCharsOnly.length === 13 || isbnCharsOnly.length === 10) {
        return isbnCharsOnly;
    }

    const ean13 = isbnCharsOnly.match(/97[89]\d{10}/)?.[0];
    if (ean13) return ean13;

    const isbn10 = isbnCharsOnly.match(/\d{9}[0-9X]/)?.[0];
    if (isbn10) return isbn10;

    return compact;
};

const extractIsbnFromText = (rawText: string): string | null => {
    if (!rawText) return null;
    const compact = rawText.toUpperCase().replace(/[^0-9X]/g, '');
    const ean13 = compact.match(/97[89]\d{10}/)?.[0];
    if (ean13) return ean13;
    const isbn10 = compact.match(/\d{9}[0-9X]/)?.[0];
    if (isbn10) return isbn10;
    return null;
};

const createReader = () => {
    const hints = new Map<DecodeHintType, unknown>();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, SCAN_FORMATS);
    hints.set(DecodeHintType.TRY_HARDER, true);
    return new BrowserMultiFormatReader(hints, 160);
};

const loadImage = (src: string): Promise<HTMLImageElement> =>
    new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('Image could not be loaded'));
        img.src = src;
    });

const drawRotatedToCanvas = (
    image: HTMLImageElement,
    rotation: 0 | 90 | 180 | 270,
    filter: string
): HTMLCanvasElement => {
    const canvas = document.createElement('canvas');
    const sideways = rotation === 90 || rotation === 270;
    canvas.width = sideways ? image.naturalHeight : image.naturalWidth;
    canvas.height = sideways ? image.naturalWidth : image.naturalHeight;

    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) return canvas;

    ctx.save();
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.filter = filter;
    ctx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
    ctx.restore();

    return canvas;
};

const extractRawFromDetected = (detected: DetectedBarcodeLike[] | undefined | null): string | null => {
    if (!detected || detected.length === 0) return null;
    return detected.find((entry) => !!entry?.rawValue)?.rawValue || null;
};

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onDetected, onClose }) => {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const photoInputRef = useRef<HTMLInputElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const readerRef = useRef<BrowserMultiFormatReader | null>(null);
    const nativeLoopTimerRef = useRef<number | null>(null);
    const nativeDetectorRef = useRef<BarcodeDetectorLike | null>(null);
    const hasDetected = useRef(false);

    const [error, setError] = useState<string | null>(null);
    const [isStarting, setIsStarting] = useState(true);
    const [isDecodingPhoto, setIsDecodingPhoto] = useState(false);
    const [manualCode, setManualCode] = useState('');

    const onDetectedRef = useRef(onDetected);
    onDetectedRef.current = onDetected;

    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    const cleanup = useCallback(() => {
        if (nativeLoopTimerRef.current !== null) {
            window.clearTimeout(nativeLoopTimerRef.current);
            nativeLoopTimerRef.current = null;
        }
        nativeDetectorRef.current = null;

        if (readerRef.current) {
            try {
                readerRef.current.reset();
            } catch {
                // no-op
            }
            readerRef.current = null;
        }

        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }

        if (videoRef.current) {
            videoRef.current.srcObject = null;
        }
    }, []);

    const emitDetectedCode = useCallback((raw: string) => {
        const normalized = normalizeDetectedCode(raw);
        if (!normalized || hasDetected.current) return;

        hasDetected.current = true;
        cleanup();
        onDetectedRef.current(normalized);
    }, [cleanup]);

    const decodeWithZxingUrl = useCallback(async (url: string): Promise<string | null> => {
        const reader = createReader();
        try {
            const result = await reader.decodeFromImageUrl(url);
            return result?.getText?.() || null;
        } catch {
            return null;
        } finally {
            try {
                reader.reset();
            } catch {
                // no-op
            }
        }
    }, []);

    const decodeIsbnWithOcr = useCallback(async (image: Blob | File | string): Promise<string | null> => {
        try {
            const { createWorker } = await import('tesseract.js');
            const worker = await createWorker('eng');
            try {
                const result = await worker.recognize(image);
                const text = result?.data?.text || '';
                return extractIsbnFromText(text);
            } finally {
                await worker.terminate();
            }
        } catch {
            return null;
        }
    }, []);

    const decodeImageFile = useCallback(async (file: File): Promise<string | null> => {
        const detectorCtor = (window as unknown as { BarcodeDetector?: BarcodeDetectorConstructorLike }).BarcodeDetector;
        const detector = detectorCtor ? new detectorCtor({ formats: NATIVE_DETECTOR_FORMATS }) : null;

        // First pass: original file via native detector and ZXing.
        let bitmap: ImageBitmap | null = null;
        try {
            bitmap = await createImageBitmap(file);
            if (detector) {
                const nativeRaw = extractRawFromDetected(await detector.detect(bitmap));
                if (nativeRaw) return nativeRaw;
            }
        } catch {
            // Continue to ZXing/canvas variants.
        } finally {
            if (bitmap) bitmap.close();
        }

        const originalUrl = URL.createObjectURL(file);
        try {
            const directRaw = await decodeWithZxingUrl(originalUrl);
            if (directRaw) return directRaw;

            const image = await loadImage(originalUrl);
            const rotations: Array<0 | 90 | 180 | 270> = [0, 90, 180, 270];
            const filters = ['none', 'grayscale(1) contrast(1.9) brightness(1.1)'];

            for (const rotation of rotations) {
                for (const filter of filters) {
                    const canvas = drawRotatedToCanvas(image, rotation, filter);

                    if (detector) {
                        try {
                            const nativeRaw = extractRawFromDetected(await detector.detect(canvas));
                            if (nativeRaw) return nativeRaw;
                        } catch {
                            // ignore and continue
                        }
                    }

                    const variantUrl = canvas.toDataURL('image/jpeg', 0.95);
                    const zxingRaw = await decodeWithZxingUrl(variantUrl);
                    if (zxingRaw) return zxingRaw;
                }
            }

            // Final fallback: OCR ISBN text above/below barcode label.
            const ocrRaw = await decodeIsbnWithOcr(file);
            if (ocrRaw) return ocrRaw;

            return null;
        } finally {
            URL.revokeObjectURL(originalUrl);
        }
    }, [decodeIsbnWithOcr, decodeWithZxingUrl]);

    useEffect(() => {
        let mounted = true;

        const startScanning = async () => {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: { ideal: 'environment' },
                        width: { ideal: 1920, min: 640 },
                        height: { ideal: 1080, min: 480 },
                    },
                    audio: false,
                });

                if (!mounted) {
                    stream.getTracks().forEach((t) => t.stop());
                    return;
                }

                streamRef.current = stream;
                const video = videoRef.current;
                if (!video) return;

                video.srcObject = stream;
                video.setAttribute('playsinline', 'true');
                video.setAttribute('autoplay', 'true');
                video.muted = true;

                await video.play();
                if (!mounted) return;
                setIsStarting(false);

                const detectorCtor = (window as unknown as { BarcodeDetector?: BarcodeDetectorConstructorLike }).BarcodeDetector;
                if (detectorCtor) {
                    try {
                        nativeDetectorRef.current = new detectorCtor({ formats: NATIVE_DETECTOR_FORMATS });

                        const runNativeLoop = async () => {
                            if (!mounted || hasDetected.current) return;
                            const detector = nativeDetectorRef.current;
                            if (!detector) return;

                            try {
                                const detected = await detector.detect(video);
                                const firstRaw = extractRawFromDetected(detected);
                                if (firstRaw) {
                                    emitDetectedCode(firstRaw);
                                    return;
                                }
                            } catch {
                                // Ignore frame-level errors.
                            }

                            nativeLoopTimerRef.current = window.setTimeout(runNativeLoop, 120);
                        };

                        void runNativeLoop();
                    } catch {
                        nativeDetectorRef.current = null;
                    }
                }

                const reader = createReader();
                readerRef.current = reader;

                reader.decodeFromVideoElementContinuously(video, (result, err) => {
                    if (!mounted || hasDetected.current) return;

                    if (result) {
                        emitDetectedCode(result.getText());
                        return;
                    }

                    if (err && !(err instanceof NotFoundException)) {
                        // Ignore transient frame decode errors and continue.
                    }
                });
            } catch (err) {
                if (!mounted) return;
                const msg = err instanceof Error ? err.message : String(err);

                if (msg.includes('NotAllowed') || msg.includes('Permission') || msg.includes('denied')) {
                    setError('Camera permission denied. Please allow camera access and try again.');
                } else if (msg.includes('NotFound') || msg.includes('Overconstrained')) {
                    setError('No suitable camera found on this device.');
                } else {
                    setError(`Camera error: ${msg}`);
                }

                setIsStarting(false);
            }
        };

        void startScanning();

        return () => {
            mounted = false;
            cleanup();
        };
    }, [cleanup, emitDetectedCode]);

    const handleClose = useCallback(() => {
        cleanup();
        onCloseRef.current();
    }, [cleanup]);

    const handleManualSubmit = useCallback(() => {
        const normalized = normalizeDetectedCode(manualCode);
        if (!normalized) return;

        cleanup();
        onDetectedRef.current(normalized);
    }, [manualCode, cleanup]);

    const handlePhotoDecode = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setError(null);
        setIsDecodingPhoto(true);
        try {
            const decodedRaw = await decodeImageFile(file);
            if (!decodedRaw) {
                setError('Could not read barcode from photo. Try another angle, better light, or use manual ISBN.');
                return;
            }
            emitDetectedCode(decodedRaw);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setError(`Photo decode failed: ${msg}`);
        } finally {
            setIsDecodingPhoto(false);
            event.target.value = '';
        }
    }, [decodeImageFile, emitDetectedCode]);

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
            <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
                <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
                    <h3 className="text-lg font-bold text-slate-800 dark:text-white flex items-center gap-2">
                        <Camera className="text-[#CC561E]" size={20} />
                        Scan ISBN Barcode
                    </h3>
                    <button
                        onClick={handleClose}
                        className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                <div className="p-4">
                    <div className="relative rounded-lg overflow-hidden bg-black min-h-[320px]">
                        <video
                            ref={videoRef}
                            className="w-full h-[320px] object-cover"
                            playsInline
                            autoPlay
                            muted
                        />

                        <div className="absolute inset-0 pointer-events-none">
                            <div className="absolute inset-0 flex items-center justify-center">
                                <div className="w-[280px] h-[90px] relative">
                                    <div className="absolute top-0 left-0 w-8 h-8 border-l-2 border-t-2 border-white" />
                                    <div className="absolute top-0 right-0 w-8 h-8 border-r-2 border-t-2 border-white" />
                                    <div className="absolute bottom-0 left-0 w-8 h-8 border-l-2 border-b-2 border-white" />
                                    <div className="absolute bottom-0 right-0 w-8 h-8 border-r-2 border-b-2 border-white" />
                                    <div className="absolute top-1/2 left-2 right-2 h-0.5 bg-[#CC561E]/70 animate-pulse" />
                                </div>
                            </div>
                        </div>

                        {isStarting && (
                            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/50">
                                <Loader2 className="animate-spin text-[#CC561E]" size={32} />
                                <p className="text-sm text-slate-200">Starting camera...</p>
                            </div>
                        )}
                    </div>

                    <p className="text-center text-xs text-slate-400 dark:text-slate-500 mt-3">
                        Align the barcode in the frame and keep the phone steady.
                    </p>

                    {error && (
                        <p className="mt-2 text-center text-xs text-red-500 dark:text-red-400">
                            {error}
                        </p>
                    )}

                    <div className="mt-3">
                        <input
                            ref={photoInputRef}
                            type="file"
                            accept="image/*"
                            capture="environment"
                            onChange={handlePhotoDecode}
                            className="hidden"
                        />
                        <button
                            type="button"
                            onClick={() => photoInputRef.current?.click()}
                            disabled={isDecodingPhoto}
                            className="w-full px-3 py-2 rounded-lg text-sm font-medium border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:border-[#CC561E]/50 hover:text-[#CC561E] disabled:opacity-60 transition-colors"
                        >
                            {isDecodingPhoto ? 'Reading photo...' : 'Scan From Photo'}
                        </button>
                    </div>

                    <div className="mt-4 flex gap-2">
                        <input
                            value={manualCode}
                            onChange={(e) => setManualCode(e.target.value)}
                            placeholder="Type or paste ISBN"
                            className="flex-1 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm font-mono bg-white dark:bg-slate-950 text-slate-900 dark:text-white"
                        />
                        <button
                            type="button"
                            onClick={handleManualSubmit}
                            disabled={!manualCode.trim()}
                            className="px-3 py-2 rounded-lg text-sm font-medium bg-[#CC561E] text-white disabled:opacity-50"
                        >
                            Use ISBN
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
