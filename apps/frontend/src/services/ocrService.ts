import { createWorker } from 'tesseract.js';

export interface OcrResult {
  text: string;
  confidence: number;
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
