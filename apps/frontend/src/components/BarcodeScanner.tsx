import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Html5Qrcode, Html5QrcodeScannerState } from 'html5-qrcode';
import { X, Camera, Loader2 } from 'lucide-react';

interface BarcodeScannerProps {
    onDetected: (code: string) => void;
    onClose: () => void;
}

const SCANNER_REGION_ID = 'barcode-scanner-region';

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onDetected, onClose }) => {
    const scannerRef = useRef<Html5Qrcode | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isStarting, setIsStarting] = useState(true);
    const hasDetected = useRef(false);

    // Use ref for the callback to avoid stale closures and useEffect re-runs
    const onDetectedRef = useRef(onDetected);
    onDetectedRef.current = onDetected;

    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    useEffect(() => {
        let mounted = true;
        const scanner = new Html5Qrcode(SCANNER_REGION_ID);
        scannerRef.current = scanner;

        const startScanner = async () => {
            try {
                await scanner.start(
                    { facingMode: 'environment' },
                    {
                        fps: 15,
                        qrbox: { width: 220, height: 80 },
                        aspectRatio: 1.5,
                    },
                    (decodedText) => {
                        if (hasDetected.current || !mounted) return;
                        hasDetected.current = true;

                        // Clean ISBN: strip hyphens, spaces, and any prefix text
                        const cleaned = decodedText.replace(/[-\s]/g, '');

                        // Stop scanner immediately after detection
                        scanner.stop().then(() => {
                            onDetectedRef.current(cleaned);
                        }).catch(() => {
                            onDetectedRef.current(cleaned);
                        });
                    },
                    () => {
                        // Ignore per-frame scan failures (no barcode in frame)
                    }
                );
                if (mounted) setIsStarting(false);
            } catch (err) {
                if (!mounted) return;
                const message = err instanceof Error ? err.message : String(err);
                if (message.includes('NotAllowedError') || message.includes('Permission')) {
                    setError('Camera permission denied. Please allow camera access and try again.');
                } else if (message.includes('NotFoundError') || message.includes('no camera')) {
                    setError('No camera found on this device.');
                } else {
                    setError(`Camera error: ${message}`);
                }
                setIsStarting(false);
            }
        };

        startScanner();

        return () => {
            mounted = false;
            if (scannerRef.current) {
                try {
                    const state = scannerRef.current.getState();
                    if (state === Html5QrcodeScannerState.SCANNING || state === Html5QrcodeScannerState.PAUSED) {
                        scannerRef.current.stop().catch(() => { });
                    }
                } catch {
                    // Ignore errors during cleanup
                }
            }
        };
    }, []); // Empty deps — scanner starts once

    const handleClose = useCallback(async () => {
        if (scannerRef.current) {
            try {
                const state = scannerRef.current.getState();
                if (state === Html5QrcodeScannerState.SCANNING || state === Html5QrcodeScannerState.PAUSED) {
                    await scannerRef.current.stop();
                }
            } catch {
                // Ignore stop errors
            }
        }
        onCloseRef.current();
    }, []);

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

                    <div
                        id={SCANNER_REGION_ID}
                        className={`rounded-lg overflow-hidden ${isStarting || error ? 'h-0' : ''}`}
                    />

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
