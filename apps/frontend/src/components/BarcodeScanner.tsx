import React, { useEffect, useRef, useState, useCallback } from 'react';
import { X, Camera, Loader2 } from 'lucide-react';

interface BarcodeScannerProps {
    onDetected: (code: string) => void;
    onClose: () => void;
}

// Extend Window for BarcodeDetector (Shape Detection API)
interface BarcodeDetectorResult {
    rawValue: string;
    format: string;
}

interface BarcodeDetectorInstance {
    detect: (source: HTMLVideoElement) => Promise<BarcodeDetectorResult[]>;
}

interface BarcodeDetectorConstructor {
    new(options?: { formats?: string[] }): BarcodeDetectorInstance;
    getSupportedFormats: () => Promise<string[]>;
}

declare global {
    interface Window {
        BarcodeDetector?: BarcodeDetectorConstructor;
    }
}

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onDetected, onClose }) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isStarting, setIsStarting] = useState(true);
    const hasDetected = useRef(false);
    const rafId = useRef<number>(0);

    // Refs for callbacks to avoid stale closures
    const onDetectedRef = useRef(onDetected);
    onDetectedRef.current = onDetected;
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    const stopCamera = useCallback(() => {
        cancelAnimationFrame(rafId.current);
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
        }
    }, []);

    useEffect(() => {
        let mounted = true;

        const start = async () => {
            // 1) Check native BarcodeDetector support
            if (!window.BarcodeDetector) {
                if (mounted) {
                    setError('Barcode scanning is not supported in this browser. Please use Chrome or Safari.');
                    setIsStarting(false);
                }
                return;
            }

            // 2) Request camera
            let stream: MediaStream;
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: 'environment',
                        width: { ideal: 1280 },
                        height: { ideal: 720 },
                    },
                });
            } catch (err) {
                if (!mounted) return;
                const msg = err instanceof Error ? err.message : String(err);
                if (msg.includes('NotAllowed') || msg.includes('Permission')) {
                    setError('Camera permission denied. Please allow camera access and try again.');
                } else if (msg.includes('NotFound')) {
                    setError('No camera found on this device.');
                } else {
                    setError(`Camera error: ${msg}`);
                }
                setIsStarting(false);
                return;
            }

            if (!mounted) {
                stream.getTracks().forEach((t) => t.stop());
                return;
            }

            streamRef.current = stream;

            // 3) Attach stream to video element
            const video = videoRef.current;
            if (!video) return;
            video.srcObject = stream;
            try {
                await video.play();
            } catch {
                // autoplay might be blocked, ignore
            }

            if (mounted) setIsStarting(false);

            // 4) Create BarcodeDetector for book barcodes
            const detector = new window.BarcodeDetector({
                formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'],
            });

            // 5) Scan loop using requestAnimationFrame
            const scanFrame = async () => {
                if (!mounted || hasDetected.current || !video || video.readyState < 2) {
                    if (mounted && !hasDetected.current) {
                        rafId.current = requestAnimationFrame(scanFrame);
                    }
                    return;
                }

                try {
                    const results = await detector.detect(video);
                    if (results.length > 0 && !hasDetected.current) {
                        hasDetected.current = true;
                        const code = results[0].rawValue.replace(/[-\s]/g, '');
                        stopCamera();
                        onDetectedRef.current(code);
                        return;
                    }
                } catch {
                    // Frame detection error — skip frame
                }

                if (mounted && !hasDetected.current) {
                    rafId.current = requestAnimationFrame(scanFrame);
                }
            };

            rafId.current = requestAnimationFrame(scanFrame);
        };

        start();

        return () => {
            mounted = false;
            stopCamera();
        };
    }, [stopCamera]);

    const handleClose = useCallback(() => {
        stopCamera();
        onCloseRef.current();
    }, [stopCamera]);

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
                            muted
                            autoPlay
                            className="w-full rounded-lg"
                            style={{ transform: 'scaleX(1)' }}
                        />
                        {/* Scanning guide overlay */}
                        {!isStarting && !error && (
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <div className="w-[70%] h-16 border-2 border-white/70 rounded-lg shadow-[0_0_0_9999px_rgba(0,0,0,0.3)]" />
                            </div>
                        )}
                    </div>

                    {!isStarting && !error && (
                        <p className="text-center text-xs text-slate-400 dark:text-slate-500 mt-3">
                            Point camera at the barcode on the back of the book
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
};
