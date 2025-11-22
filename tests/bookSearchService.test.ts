// tests/bookSearchService.test.ts
import { describe, it, expect } from 'vitest';
import { searchBooks } from '../services/bookSearchService';

describe('searchBooks', () => {
    it('returns results and caches on second call', async () => {
        const result1 = await searchBooks('cocuk');
        expect(Array.isArray(result1.results)).toBe(true);
        const result2 = await searchBooks('cocuk');
        expect(result2.cached).toBe(true);
    });
});
