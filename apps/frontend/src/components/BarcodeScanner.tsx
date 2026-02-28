import React, { useEffect, useRef, useState, useCallback } from 'react';
import { BrowserMultiFormatReader, DecodeHintType, BarcodeFormat, NotFoundException } from '@zxing/library';
import { X, Camera, Loader2 } from 'lucide-react';

interface BarcodeScannerProps {
    onDetected: (code: string) => void;
    onClose: () => void;
}

interface DetectedBarcodeValue {
    rawValue?: string;
}

interface BarcodeDetectorInstance {
    detect: (source: ImageBitmapSource) => Promise<DetectedBarcodeValue[]>;
}

type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorInstance;

type WindowWithOptionalBarcodeDetector = Window & {
    BarcodeDetector?: BarcodeDetectorCtor;
};

const buildDecodeHints = () => {
    const hints = new Map<DecodeHintType, unknown>();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [
        BarcodeFormat.EAN_13,
        BarcodeFormat.EAN_8,
        BarcodeFormat.UPC_A,
        BarcodeFormat.UPC_E,
        BarcodeFormat.CODE_128,
    ]);
    hints.set(DecodeHintType.TRY_HARDER, true);
    hints.set(DecodeHintType.ALSO_INVERTED, true);
    return hints;
};

const normalizeDetectedCode = (raw: string) => {
    const compact = raw.replace(/[\s-]/g, '').trim();
    const isbnCharsOnly = compact.replace(/[^0-9Xx]/g, '').toUpperCase();

    if (isbnCharsOnly.length === 13 || isbnCharsOnly.length === 10) {
        return isbnCharsOnly;
    }

    const ean13 = isbnCharsOnly.match(/97[89]\d{10}/)?.[0];
    if (ean13) {
        return ean13;
    }

    const isbn10 = isbnCharsOnly.match(/\d{9}[0-9X]/)?.[0];
    if (isbn10) {
        return isbn10;
    }

    return compact;
};

const stopStreamTracks = (stream: MediaStream | null) => {
    if (!stream) return;
    stream.getTracks().forEach((track) => track.stop());
};

const applyMobileFocusHint = async (stream: MediaStream) => {
    const [videoTrack] = stream.getVideoTracks();
    if (!videoTrack) return;

    try {
        await videoTrack.applyConstraints({
            advanced: [{ focusMode: 'continuous' } as MediaTrackConstraintSet],
        } as MediaTrackConstraints);
    } catch {
        // Some browsers do not support focusMode.
    }
};

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onDetected, onClose }) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const readerRef = useRef<BrowserMultiFormatReader | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const detectTimerRef = useRef<number | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isStarting, setIsStarting] = useState(true);
    const hasDetected = useRef(false);

    const onDetectedRef = useRef(onDetected);
    onDetectedRef.current = onDetected;
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    const stopScanner = useCallback(() => {
        if (detectTimerRef.current !== null) {
            window.clearTimeout(detectTimerRef.current);
            detectTimerRef.current = null;
        }
        readerRef.current?.reset();
        stopStreamTracks(streamRef.current);
        streamRef.current = null;
    }, []);

    useEffect(() => {
        let mounted = true;

        const reader = new BrowserMultiFormatReader(buildDecodeHints(), { delayBetweenScanAttempts: 100 });
        readerRef.current = reader;

        const finishWithCode = (rawCode: string) => {
            if (!mounted || hasDetected.current) return;
            hasDetected.current = true;
            const normalized = normalizeDetectedCode(rawCode);
            stopScanner();
            onDetectedRef.current(normalized);
        };

        const startNativeBarcodeDetector = (videoEl: HTMLVideoElement) => {
            const barcodeDetectorCtor = (window as WindowWithOptionalBarcodeDetector).BarcodeDetector;
            if (!barcodeDetectorCtor) return;

            let detector: BarcodeDetectorInstance;
            try {
                detector = new barcodeDetectorCtor({
                    formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'],
                });
            } catch {
                try {
                    detector = new barcodeDetectorCtor();
                } catch {
                    return;
                }
            }

            const runDetectLoop = async () => {
                if (!mounted || hasDetected.current) return;

                try {
                    if (videoEl.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
                        const barcodes = await detector.detect(videoEl);
                        const rawValue = barcodes.find((item) => item.rawValue?.trim())?.rawValue;
                        if (rawValue) {
                            finishWithCode(rawValue);
                            return;
                        }
                    }
                } catch {
                    // Native detector can fail per frame.
                }

                detectTimerRef.current = window.setTimeout(runDetectLoop, 120);
            };

            runDetectLoop();
        };

        const startScanning = async () => {
            try {
                let stream: MediaStream;
                const preferredConstraints: MediaStreamConstraints = {
                    audio: false,
                    video: {
                        facingMode: { ideal: 'environment' },
                        width: { ideal: 1920 },
                        height: { ideal: 1080 },
                        aspectRatio: { ideal: 16 / 9 },
                    },
                };

                try {
                    stream = await navigator.mediaDevices.getUserMedia(preferredConstraints);
                } catch {
                    stream = await navigator.mediaDevices.getUserMedia({
                        audio: false,
                        video: { facingMode: { ideal: 'environment' } },
                    });
                }

                if (!mounted) {
                    stopStreamTracks(stream);
                    return;
                }

                streamRef.current = stream;
                await applyMobileFocusHint(stream);

                const videoEl = videoRef.current;
                if (!videoEl) {
                    throw new Error('Video element not available');
                }

                videoEl.srcObject = stream;
                videoEl.setAttribute('playsinline', 'true');
                videoEl.setAttribute('autoplay', 'true');
                await videoEl.play().catch(() => undefined);

                if (mounted) setIsStarting(false);

                // Run native detector and ZXing together for better mobile reliability.
                startNativeBarcodeDetector(videoEl);

                await reader.decodeFromStream(stream, videoEl, (result, err) => {
                    if (!mounted || hasDetected.current) return;

                    if (result) {
                        finishWithCode(result.getText());
                        return;
                    }

                    if (err && !(err instanceof NotFoundException)) {
                        console.error('ZXing scan error:', err);
                    }
                });
            } catch (err) {
                if (!mounted) return;
                const msg = err instanceof Error ? err.message : String(err);
                if (msg.includes('NotAllowed') || msg.includes('Permission')) {
                    setError('Camera permission denied. Please allow camera access and try again.');
                } else if (msg.includes('NotFound') || msg.includes('no camera') || msg.includes('Overconstrained')) {
                    setError('No suitable camera found on this device.');
                } else {
                    setError(`Camera error: ${msg}`);
                }
                setIsStarting(false);
            }
        };

        startScanning();

        return () => {
            mounted = false;
            stopScanner();
        };
    }, [stopScanner]);

    const handleClose = useCallback(() => {
        stopScanner();
        onCloseRef.current();
    }, [stopScanner]);

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
            <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
                {/* Header */}
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

                {/* Scanner Region */}
                <div className="p-4">
                    {isStarting && !error && (
                        <div className="flex flex-col items-center justify-center py-12 gap-3">
                            <Loader2 className="animate-spin text-[#CC561E]" size={32} />
                            <p className="text-sm text-slate-500 dark:text-slate-400">Starting camera...</p>
                        </div>
                    )}

                    {error && (
                        <div className="flex flex-col items-center justify-center py-12 gap-3 text-center">
                            <Camera className="text-red-400" size={32} />
                            <p className="text-sm text-red-500 dark:text-red-400 max-w-xs">{error}</p>
                            <button
                                onClick={handleClose}
                                className="mt-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium transition-colors"
                            >
                                Close
                            </button>
                        </div>
                    )}

                    {/* Live Camera Feed */}
                    <div className={`relative rounded-lg overflow-hidden ${isStarting || error ? 'h-0' : ''}`}>
                        <video
                            ref={videoRef}
                            playsInline
                            autoPlay
                            muted
                            className="w-full rounded-lg"
                        />
                        {!isStarting && !error && (
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <div className="w-[75%] h-14 border-2 border-white/80 rounded shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
                            </div>
                        )}
                    </div>

                    {!isStarting && !error && (
                        <p className="text-center text-xs text-slate-400 dark:text-slate-500 mt-3">
                            Align the barcode in the white frame and keep the phone steady.
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
};
