import { createWorker } from 'tesseract.js';
import type { LoggerMessage } from 'tesseract.js';

export interface OcrResult {
  text: string;
  confidence: number;
}

type OcrProgressLogger = (msg: LoggerMessage) => void;

export class OnDeviceOcrSession {
  private worker: Awaited<ReturnType<typeof createWorker>> | null = null;
  private initialized = false;

  async init(logger?: OcrProgressLogger): Promise<void> {
    if (this.initialized && this.worker) return;
    this.worker = await createWorker('tur+eng', 1, {
      logger: (msg) => {
        logger?.(msg);
      },
    });
    this.initialized = true;
  }

  async recognize(image: string | Blob): Promise<OcrResult> {
    if (!this.worker || !this.initialized) {
      throw new Error('OCR session is not initialized');
    }
    const { data: { text, confidence } } = await this.worker.recognize(image);
    return { text, confidence };
  }

  async terminate(): Promise<void> {
    if (!this.worker) return;
    await this.worker.terminate();
    this.worker = null;
    this.initialized = false;
  }
}

export const extractTextFromImage = async (
  imageSrc: string | Blob,
  onProgress?: (progress: number) => void
): Promise<OcrResult> => {
  const worker = await createWorker('tur+eng', 1, {
    logger: m => {
      if (m.status === 'recognizing text' && onProgress) {
        onProgress(Math.round(m.progress * 100));
      }
    },
  });

  try {
    const { data: { text, confidence } } = await worker.recognize(imageSrc);
    return { text, confidence };
  } finally {
    await worker.terminate();
  }
};
