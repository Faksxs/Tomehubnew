import React, { useEffect, useRef, useState, useCallback } from 'react';
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

const normalizeDetectedCode = (raw: string): string => {
    const compact = raw.replace(/[\s-]/g, '').trim();
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

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onDetected, onClose }) => {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const readerRef = useRef<BrowserMultiFormatReader | null>(null);
    const hasDetected = useRef(false);

    const [error, setError] = useState<string | null>(null);
    const [isStarting, setIsStarting] = useState(true);
    const [manualCode, setManualCode] = useState('');

    const onDetectedRef = useRef(onDetected);
    onDetectedRef.current = onDetected;
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    const cleanup = useCallback(() => {
        if (readerRef.current) {
            try {
                readerRef.current.reset();
            } catch {
                // Already reset
            }
            readerRef.current = null;
        }

        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }

        if (videoRef.current) {
            videoRef.current.srcObject = null;
        }
    }, []);

    useEffect(() => {
        let mounted = true;

        const startScanning = async () => {
            try {
                // Step 1: Get camera stream directly — most reliable on iOS Safari
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: { ideal: 'environment' },
                        width: { ideal: 1920, min: 640 },
                        height: { ideal: 1080, min: 480 },
                    },
                    audio: false,
                });

                if (!mounted) {
                    stream.getTracks().forEach(t => t.stop());
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

                // Step 2: Create ZXing reader with barcode-specific hints
                const hints = new Map<DecodeHintType, unknown>();
                hints.set(DecodeHintType.POSSIBLE_FORMATS, SCAN_FORMATS);
                hints.set(DecodeHintType.TRY_HARDER, true);

                const reader = new BrowserMultiFormatReader(hints, 500);
                readerRef.current = reader;

                // Step 3: Use continuous decode — ZXing will poll the video element
                // and call our callback on each result (or error)
                reader.decodeFromVideoElementContinuously(video, (result, err) => {
                    if (!mounted || hasDetected.current) return;

                    if (result) {
                        const raw = result.getText();
                        const normalized = normalizeDetectedCode(raw);

                        if (normalized) {
                            hasDetected.current = true;
                            cleanup();
                            onDetectedRef.current(normalized);
                        }
                        return;
                    }

                    // NotFoundException is expected on frames without a barcode — ignore it
                    if (err && !(err instanceof NotFoundException)) {
                        // ChecksumException, FormatException etc. — just retry
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

        startScanning();

        return () => {
            mounted = false;
            cleanup();
        };
    }, [cleanup]);

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
                    {error ? (
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
                    ) : (
                        <>
                            <div className="relative rounded-lg overflow-hidden bg-black min-h-[320px]">
                                <video
                                    ref={videoRef}
                                    className="w-full h-[320px] object-cover"
                                    playsInline
                                    autoPlay
                                    muted
                                />

                                {/* Scan frame overlay */}
                                <div className="absolute inset-0 pointer-events-none">
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <div className="w-[280px] h-[90px] relative">
                                            {/* Corner markers */}
                                            <div className="absolute top-0 left-0 w-8 h-8 border-l-3 border-t-3 border-white" />
                                            <div className="absolute top-0 right-0 w-8 h-8 border-r-3 border-t-3 border-white" />
                                            <div className="absolute bottom-0 left-0 w-8 h-8 border-l-3 border-b-3 border-white" />
                                            <div className="absolute bottom-0 right-0 w-8 h-8 border-r-3 border-b-3 border-white" />
                                            {/* Scanning line animation */}
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
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};
