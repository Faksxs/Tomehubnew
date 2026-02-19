export interface MobileOcrDetectionInput {
  viewportWidth: number;
  maxTouchPoints: number;
  hasCoarsePointer: boolean;
}

export interface NormalizeImageOptions {
  maxWidth?: number;
  quality?: number;
}

export const DEFAULT_OCR_MAX_WIDTH = 1600;
export const DEFAULT_OCR_QUALITY = 0.85;

export function shouldEnableMobileCameraOcr(input: MobileOcrDetectionInput): boolean {
  const isTouchDevice = input.maxTouchPoints > 0 || input.hasCoarsePointer;
  const isMobileViewport = input.viewportWidth <= 1024;
  return isTouchDevice && isMobileViewport;
}

export function appendRecognizedText(existingText: string, recognizedText: string): string {
  const base = (existingText || "").trim();
  const addition = (recognizedText || "").trim();
  if (!addition) return base;
  if (!base) return addition;
  return `${base}\n\n${addition}`;
}

export async function normalizeImageForOcr(
  input: Blob,
  options: NormalizeImageOptions = {}
): Promise<Blob> {
  const maxWidth = options.maxWidth ?? DEFAULT_OCR_MAX_WIDTH;
  const quality = options.quality ?? DEFAULT_OCR_QUALITY;

  const imageBitmap = await createImageBitmap(input);
  try {
    const width = imageBitmap.width;
    const height = imageBitmap.height;
    if (!width || !height) {
      throw new Error("Invalid image dimensions");
    }

    const scale = width > maxWidth ? maxWidth / width : 1;
    const targetWidth = Math.max(1, Math.round(width * scale));
    const targetHeight = Math.max(1, Math.round(height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = targetWidth;
    canvas.height = targetHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Canvas context is unavailable");
    }

    ctx.drawImage(imageBitmap, 0, 0, targetWidth, targetHeight);

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", quality);
    });

    return blob || input;
  } finally {
    imageBitmap.close();
  }
}

export function splitOcrLines(text: string): string[] {
  return (text || "")
    .split(/\r?\n/g)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}
