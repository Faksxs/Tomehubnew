import React, { useState } from 'react';
import { Database, Play, Loader2, CheckCircle, AlertCircle, BarChart } from 'lucide-react';
import { LibraryItem } from '../types';
import { addTextItem, migrateBulkItems, syncHighlights } from '../services/backendApiService';

interface MigrateToAIProps {
    books: LibraryItem[];
    userId: string;
}

export const MigrateToAI: React.FC<MigrateToAIProps> = ({ books, userId }) => {
    const [isMigrating, setIsMigrating] = useState(false);
    const [progress, setProgress] = useState(0);
    const [stats, setStats] = useState({ success: 0, failed: 0, total: 0 });
    const [currentTitle, setCurrentTitle] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [finished, setFinished] = useState(false);

    const handleMigrate = async () => {
        if (!userId) return;

        setIsMigrating(true);
        setError(null);
        setFinished(false);

        let successCount = 0;
        let failCount = 0;

        setStats({ success: 0, failed: 0, total: books.length });

        // Prepare all items first
        const allItems = books.map(item => {
            let textContent = '';
            if (item.type === 'PERSONAL_NOTE') {
                textContent = item.generalNotes || item.title;
                if (item.highlights && item.highlights.length > 0) {
                    textContent += '\n\n' + item.highlights.map(h => h.text).join('\n\n');
                }
            } else {
                textContent = `Title: ${item.title}\nAuthor: ${item.author}\n`;
                if (item.generalNotes) textContent += `\nSummary/Notes: ${item.generalNotes}`;
                if (item.tags && item.tags.length > 0) textContent += `\nTags: ${item.tags.join(', ')}`;
            }
            return {
                text: textContent,
                title: item.title,
                author: item.author,
                type: item.type,
                book_id: item.id,
                tags: item.tags
            };
        }).filter(item => item.text.length > 20); // Filter out empty/short items

        const totalItemsToProcess = allItems.length;

        // Chunk items into batches of 20
        const BATCH_SIZE = 20;
        const batches = [];
        for (let i = 0; i < allItems.length; i += BATCH_SIZE) {
            batches.push(allItems.slice(i, i + BATCH_SIZE));
        }

        let processedCount = 0;

        for (let i = 0; i < batches.length; i++) {
            const batch = batches[i];

            setCurrentTitle(`Batch ${i + 1}/${batches.length} (${batch.length} items)`);

            try {
                const result = await migrateBulkItems(batch, userId);

                if (result.success && result.results) {
                    successCount += result.results.success;
                    failCount += result.results.failed;
                }

            } catch (err) {
                console.error(`Batch ${i + 1} failed:`, err);
                failCount += batch.length; // Assume all failed if batch failed
            }

            processedCount += batch.length;
            setProgress(Math.round((processedCount / totalItemsToProcess) * 100));
            setStats(prev => ({
                ...prev,
                success: successCount,
                failed: failCount + (books.length - totalItemsToProcess)
            }));
        }

        // After bulk migration, sync highlights/insights for books with highlights
        const highlightSources = books.filter(b => b.highlights && b.highlights.length > 0);
        if (highlightSources.length > 0) {
            setCurrentTitle('Syncing highlights...');
            for (const item of highlightSources) {
                try {
                    await syncHighlights(userId, item.id, item.title, item.author, item.highlights || []);
                } catch (err) {
                    console.error(`Highlight sync failed for ${item.title}:`, err);
                }
            }
        }

        setIsMigrating(false);
        setFinished(true);
        setCurrentTitle('');
    };

    return (
        <div className="bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 rounded-xl border border-emerald-100 dark:border-emerald-800 shadow-sm overflow-hidden mb-8">
            <div className="p-6 md:p-8">
                <div className="flex items-start gap-4 mb-6">
                    <div className="p-3 bg-white dark:bg-slate-900 rounded-lg shadow-sm text-emerald-600 dark:text-emerald-400">
                        <Database size={24} />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-slate-900 dark:text-white">Migrate to AI Library</h2>
                        <p className="text-slate-600 dark:text-slate-300 mt-1">
                            Sync your existing books and notes to the new AI backend to make them searchable.
                        </p>
                    </div>
                </div>

                <div className="bg-white/60 dark:bg-slate-900/60 rounded-xl p-6 border border-emerald-100/50 dark:border-emerald-800/50">
                    <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                        <div>
                            <h3 className="font-medium text-slate-900 dark:text-white mb-1">
                                {isMigrating ? 'Migration in Progress...' : 'Ready to Sync'}
                            </h3>
                            <p className="text-slate-500 dark:text-slate-400 text-sm">
                                {finished ? (
                                    <span className="text-emerald-600 font-medium">Migration Complete! {stats.success} items synced.</span>
                                ) : isMigrating ? (
                                    <span>Syncing: <span className="font-medium text-emerald-600 dark:text-emerald-400">{currentTitle}</span></span>
                                ) : (
                                    <span>Sync {books.length} items to Oracle AI Vector Database.</span>
                                )}
                            </p>
                        </div>

                        {!isMigrating && !finished && (
                            <button
                                onClick={handleMigrate}
                                className="flex items-center gap-2 px-6 py-3 bg-emerald-600 text-white hover:bg-emerald-700 rounded-lg font-medium transition-colors shadow-md shadow-emerald-200 dark:shadow-none"
                            >
                                <Play size={18} fill="currentColor" />
                                Start Migration
                            </button>
                        )}

                        {isMigrating && (
                            <div className="flex items-center gap-2 px-6 py-3 bg-white dark:bg-slate-800 text-slate-500 rounded-lg border border-slate-200 dark:border-slate-700">
                                <Loader2 size={18} className="animate-spin" />
                                Processing...
                            </div>
                        )}
                    </div>

                    {/* Progress Bar */}
                    {(isMigrating || finished) && (
                        <div className="mt-6">
                            <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-2">
                                <span>Progress</span>
                                <span>{progress}%</span>
                            </div>
                            <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-emerald-500 transition-all duration-300 ease-out"
                                    style={{ width: `${progress}%` }}
                                />
                            </div>
                            <div className="flex justify-between text-xs text-slate-400 dark:text-slate-500 mt-2">
                                <span>{stats.success + stats.failed}/{stats.total} items</span>
                                <span>Success: {stats.success} • Failed: {stats.failed}</span>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
