import { useState, useCallback, useRef } from 'react';
import { LibraryItem } from '../types';
import {
    enrichBooksBatch,
    libraryItemToDraft,
    mergeEnrichedDraftIntoItem
} from '../services/geminiService';
import { saveItemForUser } from '../services/oracleLibraryService';

interface BatchEnrichmentStats {
    total: number;
    processed: number;
    success: number;
    failed: number;
    currentBookTitle?: string;
}

export const useBatchEnrichment = (
    userId: string,
    onUpdateBook: (book: LibraryItem) => void
) => {
    const [isEnriching, setIsEnriching] = useState(false);
    const [stats, setStats] = useState<BatchEnrichmentStats>({
        total: 0,
        processed: 0,
        success: 0,
        failed: 0
    });

    const stopRef = useRef(false);

    const startEnrichment = useCallback(async (books: LibraryItem[]) => {
        // 1. Filter books that need enrichment
        // Criteria: No general notes AND (no tags OR empty tags)
        const candidates = books.filter(b =>
            b.type === 'BOOK' &&
            (!b.generalNotes || b.generalNotes.length < 10) &&
            (!b.tags || b.tags.length === 0)
        );

        if (candidates.length === 0) {
            alert("No books found that need enrichment!");
            return;
        }

        setIsEnriching(true);
        stopRef.current = false;
        setStats({
            total: candidates.length,
            processed: 0,
            success: 0,
            failed: 0,
            currentBookTitle: ''
        });

        // 2. Process queue in BATCHES of 5
        const BATCH_SIZE = 5;

        for (let i = 0; i < candidates.length; i += BATCH_SIZE) {
            if (stopRef.current) break;

            const batch = candidates.slice(i, i + BATCH_SIZE);
            const batchTitles = batch.map(b => b.title).join(', ');

            setStats(prev => ({
                ...prev,
                currentBookTitle: `Batch: ${batchTitles.substring(0, 30)}...`
            }));

            try {
                // Artificial delay to be nice to the API rate limits
                if (i > 0) await new Promise(r => setTimeout(r, 2000));

                // Prepare drafts
                const drafts = batch.map(b => libraryItemToDraft(b));

                // Call Batch API
                const enrichedDrafts = await enrichBooksBatch(drafts);

                // Process results
                for (let j = 0; j < batch.length; j++) {
                    const originalBook = batch[j];
                    // Try to find by title, or fallback to index if order preserved
                    const enrichedDraft = enrichedDrafts.find(d => d.title === originalBook.title) || enrichedDrafts[j];

                    if (enrichedDraft) {
                        const enrichedItem = mergeEnrichedDraftIntoItem(originalBook, enrichedDraft);

                        // Save to Firestore
                        await saveItemForUser(userId, enrichedItem);

                        // Update Local State
                        onUpdateBook(enrichedItem);

                        setStats(prev => ({
                            ...prev,
                            processed: prev.processed + 1,
                            success: prev.success + 1
                        }));
                    } else {
                        // Fallback: Failed to enrich this specific item in batch
                        setStats(prev => ({
                            ...prev,
                            processed: prev.processed + 1,
                            failed: prev.failed + 1
                        }));
                    }
                }

            } catch (error) {
                console.error(`Failed to enrich batch starting at ${i}:`, error);
                // Mark whole batch as failed
                setStats(prev => ({
                    ...prev,
                    processed: prev.processed + batch.length,
                    failed: prev.failed + batch.length
                }));
            }
        }

        setIsEnriching(false);
        setStats(prev => ({ ...prev, currentBookTitle: undefined }));

    }, [userId, onUpdateBook]);

    const stopEnrichment = useCallback(() => {
        stopRef.current = true;
    }, []);

    return {
        isEnriching,
        stats,
        startEnrichment,
        stopEnrichment
    };
};
