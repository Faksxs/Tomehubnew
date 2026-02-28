import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode';
import { X, Camera, Loader2 } from 'lucide-react';

interface BarcodeScannerProps {
    onDetected: (code: string) => void;
    onClose: () => void;
}

const normalizeDetectedCode = (raw: string) => {
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

const scannerFormats = [
    Html5QrcodeSupportedFormats.EAN_13,
    Html5QrcodeSupportedFormats.EAN_8,
    Html5QrcodeSupportedFormats.UPC_A,
    Html5QrcodeSupportedFormats.UPC_E,
    Html5QrcodeSupportedFormats.CODE_128,
];

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({ onDetected, onClose }) => {
    const scannerRef = useRef<Html5Qrcode | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isStarting, setIsStarting] = useState(true);
    const [manualCode, setManualCode] = useState('');
    const hasDetected = useRef(false);

    const onDetectedRef = useRef(onDetected);
    onDetectedRef.current = onDetected;
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    const scannerElementId = useMemo(() => `isbn-scanner-${Math.random().toString(36).slice(2, 10)}`, []);

    const stopScanner = useCallback(async () => {
        const scanner = scannerRef.current;
        scannerRef.current = null;
        if (!scanner) return;

        try {
            await scanner.stop();
        } catch {
            // Already stopped or not started.
        }

        try {
            scanner.clear();
        } catch {
            // No-op if DOM is already cleaned.
        }
    }, []);

    useEffect(() => {
        let mounted = true;

        const startScanner = async () => {
            try {
                const scanner = new Html5Qrcode(scannerElementId, {
                    formatsToSupport: scannerFormats,
                    useBarCodeDetectorIfSupported: true,
                    verbose: false,
                });
                scannerRef.current = scanner;

                const onSuccess = async (decodedText: string) => {
                    if (!mounted || hasDetected.current) return;
                    hasDetected.current = true;
                    const normalizedCode = normalizeDetectedCode(decodedText);
                    await stopScanner();
                    if (mounted) onDetectedRef.current(normalizedCode);
                };

                const onError = () => {
                    // Per-frame decode errors are normal while scanning.
                };

                const scanConfig = {
                    fps: 12,
                    qrbox: { width: 280, height: 90 },
                    aspectRatio: 16 / 9,
                    disableFlip: false,
                    videoConstraints: {
                        facingMode: { ideal: 'environment' },
                        width: { ideal: 1920 },
                        height: { ideal: 1080 },
                    },
                };

                try {
                    await scanner.start({ facingMode: { ideal: 'environment' } }, scanConfig, onSuccess, onError);
                } catch {
                    await scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 260, height: 80 } }, onSuccess, onError);
                }

                if (mounted) setIsStarting(false);
            } catch (err) {
                if (!mounted) return;
                const msg = err instanceof Error ? err.message : String(err);

                if (msg.includes('NotAllowed') || msg.includes('Permission') || msg.includes('denied')) {
                    setError('Camera permission denied. Please allow camera access and try again.');
                } else if (msg.includes('NotFound') || msg.includes('camera') || msg.includes('Overconstrained')) {
                    setError('No suitable camera found on this device.');
                } else {
                    setError(`Camera error: ${msg}`);
                }

                setIsStarting(false);
            }
        };

        startScanner();

        return () => {
            mounted = false;
            void stopScanner();
        };
    }, [scannerElementId, stopScanner]);

    const handleClose = useCallback(() => {
        void (async () => {
            await stopScanner();
            onCloseRef.current();
        })();
    }, [stopScanner]);

    const handleManualSubmit = useCallback(() => {
        const normalizedCode = normalizeDetectedCode(manualCode);
        if (!normalizedCode) return;

        void (async () => {
            await stopScanner();
            onDetectedRef.current(normalizedCode);
        })();
    }, [manualCode, stopScanner]);

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
                                <div id={scannerElementId} className="w-full h-[320px]" />
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
