import { describe, expect, it } from "vitest";
import { appendRecognizedText, shouldEnableMobileCameraOcr, splitOcrLines } from "./ocrHelpers";

describe("ocrHelpers", () => {
  it("enables camera OCR only on touch + mobile viewport", () => {
    expect(
      shouldEnableMobileCameraOcr({
        viewportWidth: 390,
        maxTouchPoints: 5,
        hasCoarsePointer: true,
      })
    ).toBe(true);

    expect(
      shouldEnableMobileCameraOcr({
        viewportWidth: 1366,
        maxTouchPoints: 5,
        hasCoarsePointer: true,
      })
    ).toBe(false);
  });

  it("appends OCR text with spacing", () => {
    expect(appendRecognizedText("", "Merhaba dunya")).toBe("Merhaba dunya");
    expect(appendRecognizedText("Ilk satir", "Ikinci satir")).toBe("Ilk satir\n\nIkinci satir");
  });

  it("splits OCR lines and removes empty lines", () => {
    expect(splitOcrLines(" satir 1 \n\nsatir 2\r\n  ")).toEqual(["satir 1", "satir 2"]);
  });
});
