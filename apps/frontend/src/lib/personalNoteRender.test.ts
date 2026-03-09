import { describe, expect, it } from "vitest";

import { extractBookmarkPreviewData } from "./personalNoteRender";

describe("personalNoteRender", () => {
  it("extracts bookmark url, domain, and note from minimal template text", () => {
    const result = extractBookmarkPreviewData("<ul><li><p>URL: https://component.gallery/</p></li><li><p>Note: UI reference collection</p></li></ul>");

    expect(result.url).toBe("https://component.gallery/");
    expect(result.domain).toBe("component.gallery");
    expect(result.note).toBe("UI reference collection");
  });

  it("keeps note empty when bookmark note field is blank", () => {
    const result = extractBookmarkPreviewData("<ul><li><p>URL: https://example.com</p></li><li><p>Note: </p></li></ul>");

    expect(result.url).toBe("https://example.com");
    expect(result.note).toBe("");
  });
});
