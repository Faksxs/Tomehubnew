import React from "react";
import type { LoggerMessage } from "tesseract.js";
import { OnDeviceOcrSession, type OcrResult } from "../services/ocrService";

export function useOnDeviceOcr(enabled: boolean) {
  const sessionRef = React.useRef<OnDeviceOcrSession | null>(null);
  const [isInitializing, setIsInitializing] = React.useState(false);
  const [isProcessing, setIsProcessing] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [status, setStatus] = React.useState<string>("idle");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (enabled) return;
    setProgress(0);
    setStatus("idle");
    setError(null);
    setIsProcessing(false);
    setIsInitializing(false);
  }, [enabled]);

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const init = async () => {
      setIsInitializing(true);
      setError(null);
      setStatus("OCR motoru hazirlaniyor...");
      try {
        if (!sessionRef.current) {
          sessionRef.current = new OnDeviceOcrSession();
        }
        await sessionRef.current.init((msg: LoggerMessage) => {
          if (cancelled) return;
          if (typeof msg.progress === "number") {
            setProgress(Math.round(msg.progress * 100));
          }
          if (msg.status) {
            setStatus(msg.status);
          }
        });
        if (!cancelled) {
          setStatus("hazir");
          setProgress(0);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "OCR motoru baslatilamadi");
          setStatus("error");
        }
      } finally {
        if (!cancelled) {
          setIsInitializing(false);
        }
      }
    };

    init();

    return () => {
      cancelled = true;
      const session = sessionRef.current;
      sessionRef.current = null;
      if (session) {
        session.terminate().catch(() => undefined);
      }
    };
  }, [enabled]);

  const recognize = React.useCallback(async (image: Blob): Promise<OcrResult> => {
    if (!sessionRef.current) {
      throw new Error("OCR motoru henuz hazir degil");
    }
    setIsProcessing(true);
    setError(null);
    setProgress(0);
    setStatus("Metin okunuyor...");
    try {
      const result = await sessionRef.current.recognize(image);
      setStatus("Tamamlandi");
      setProgress(100);
      return result;
    } catch (e) {
      const message = e instanceof Error ? e.message : "OCR islemi basarisiz";
      setError(message);
      setStatus("error");
      throw e;
    } finally {
      setIsProcessing(false);
    }
  }, []);

  return {
    recognize,
    isInitializing,
    isProcessing,
    progress,
    status,
    error,
    isReady: !isInitializing && !error && enabled,
  };
}
