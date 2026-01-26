import React, { useState } from 'react';
import { Download, Check, AlertCircle, FileJson } from 'lucide-react';
import { LibraryItem } from '../types';

interface ExportBooksProps {
    books: LibraryItem[];
}

export const ExportBooks: React.FC<ExportBooksProps> = ({ books }) => {
    const [exporting, setExporting] = useState(false);
    const [completed, setCompleted] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleExport = () => {
        try {
            setExporting(true);
            setError(null);
            setCompleted(false);

            // Prepare export data
            const exportData = books.map(book => ({
                ...book,
                // Ensure all fields are included
                id: book.id,
                type: book.type,
                title: book.title,
                author: book.author,
                status: book.status,
                readingStatus: book.readingStatus,
                tags: book.tags,
                highlights: book.highlights,
                addedAt: book.addedAt,
                generalNotes: book.generalNotes,
                coverUrl: book.coverUrl,
                isbn: book.isbn,
                publisher: book.publisher,
                publicationYear: book.publicationYear,
                translator: book.translator,
                code: book.code,
                url: book.url,
                lentTo: book.lentTo,
                lentDate: book.lentDate,
            }));

            // Convert to JSON with pretty formatting
            const jsonString = JSON.stringify(exportData, null, 2);

            // Create blob
            const blob = new Blob([jsonString], { type: 'application/json' });

            // Create download link
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;

            // Generate filename with current date
            const dateStr = new Date().toISOString().split('T')[0];
            link.download = `tomehub-export-${dateStr}.json`;

            // Trigger download
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);

            setCompleted(true);
            setExporting(false);

            // Reset success message after 3 seconds
            setTimeout(() => {
                setCompleted(false);
            }, 3000);
        } catch (err) {
            console.error('Export failed:', err);
            setError('Failed to export library. Please try again.');
            setExporting(false);
        }
    };

    return (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 md:p-8 mt-6">
            <div className="flex items-start justify-between mb-4">
                <div>
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white">Export Library</h2>
                    <p className="text-slate-500 dark:text-slate-400 mt-1">
                        Download your entire library as a JSON file.
                    </p>
                </div>
                <div className="p-3 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 rounded-lg">
                    <FileJson size={24} />
                </div>
            </div>

            {error && (
                <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-lg flex items-center gap-2 border border-red-100 dark:border-red-900/30">
                    <AlertCircle size={20} />
                    {error}
                </div>
            )}

            {completed && (
                <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-lg flex items-center gap-2 border border-green-100 dark:border-green-900/30">
                    <Check size={20} />
                    Successfully exported {books.length} items!
                </div>
            )}

            <button
                onClick={handleExport}
                disabled={exporting || books.length === 0}
                className="w-full py-3 px-4 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors bg-emerald-600 dark:bg-emerald-500 hover:bg-emerald-700 dark:hover:bg-emerald-600 text-white shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <Download size={20} />
                {books.length === 0 ? 'No Items to Export' : `Export ${books.length} Items`}
            </button>

            <p className="text-xs text-slate-400 dark:text-slate-500 text-center mt-3">
                Exports all books, articles, websites, and notes with highlights
            </p>
        </div>
    );
};
