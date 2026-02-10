export type CanonicalHighlightType = 'highlight' | 'insight';
export type StoredHighlightType = CanonicalHighlightType | 'note' | null | undefined;

export function normalizeHighlightType(type: StoredHighlightType): CanonicalHighlightType {
  const normalized = typeof type === 'string' ? type.trim().toLowerCase() : '';
  if (normalized === 'insight' || normalized === 'note') {
    return 'insight';
  }
  return 'highlight';
}

export function isInsightType(type: StoredHighlightType): boolean {
  return normalizeHighlightType(type) === 'insight';
}
