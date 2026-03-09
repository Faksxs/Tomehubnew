import { describe, expect, it } from "vitest";

import { extractBookmarkPreviewData, toPersonalNoteCardPreviewHtml } from "./personalNoteRender";

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

  it("builds structured card preview from checklist markdown", () => {
    const result = toPersonalNoteCardPreviewHtml("## Priority\n- [ ] Buy apples\n- [x] Buy milk\nNote: check the bakery");

    expect(result).toContain("Priority");
    expect(result).toContain("&#9744;");
    expect(result).toContain("&#9745;");
    expect(result).toContain("check the bakery");
  });

  it("falls back to meaningful text when html preview is parsed without dom", () => {
    const result = toPersonalNoteCardPreviewHtml("<table><tr><td>Priority</td></tr><tr><td>Groceries</td></tr><tr><td></td></tr></table>");

    expect(result).toContain("Priority");
    expect(result).toContain("Groceries");
  });
});
