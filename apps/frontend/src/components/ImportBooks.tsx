import React, { useState, useRef } from 'react';
import { Upload, Check, AlertCircle, FileJson } from 'lucide-react';
import { saveItemForUser } from '../services/firestoreService';
import { LibraryItem } from '../types';
import { useAuth } from '../contexts/AuthContext';

export const ImportBooks: React.FC = () => {
    const { user } = useAuth();
    const [importing, setImporting] = useState(false);
    const [progress, setProgress] = useState(0);
    const [total, setTotal] = useState(0);
    const [completed, setCompleted] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        // Basic validation
        if (!file.name.toLowerCase().endsWith('.json')) {
            setError("Please upload a valid JSON file.");
            return;
        }

        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const content = e.target?.result as string;
                const booksToImport = JSON.parse(content);

                if (!Array.isArray(booksToImport)) {
                    throw new Error("JSON must be an array of books.");
                }

                await processImport(booksToImport);
            } catch (err) {
                console.error("File parsing error:", err);
                setError("Failed to parse JSON file. Make sure it's a valid list of books.");
            }
        };
        reader.onerror = () => {
            setError("Error reading file.");
        };
        reader.readAsText(file);
    };

    const processImport = async (booksToImport: any[]) => {
        if (!user) return;

        setImporting(true);
        setError(null);
        setCompleted(false);
        setTotal(booksToImport.length);
        setProgress(0);

        let count = 0;

        try {
            for (const rawBook of booksToImport) {
                // Map JSON data to LibraryItem
                const newItem: LibraryItem = {
                    id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
                    type: 'BOOK',
                    title: rawBook.title || 'Untitled',
                    author: rawBook.author || 'Unknown Author',
                    status: 'On Shelf', // Default status
                    readingStatus: 'To Read', // Default reading status
                    tags: [],
                    highlights: [],
                    addedAt: Date.now(),
                    coverUrl: rawBook.coverUrl || undefined,
                    // Add other fields if available in JSON or leave defaults
                };

                await saveItemForUser(user.uid, newItem);

                count++;
                setProgress(count);

                // Small delay to prevent overwhelming Firestore
                await new Promise(resolve => setTimeout(resolve, 50));
            }
            setCompleted(true);
            // Reset file input so the same file can be selected again if needed
            if (fileInputRef.current) fileInputRef.current.value = '';
        } catch (err) {
            console.error("Import failed:", err);
            setError("Failed to import books. Please try again.");
        } finally {
            setImporting(false);
        }
    };

    const triggerFileInput = () => {
        fileInputRef.current?.click();
    };

    return (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 md:p-8 mt-6">
            <div className="flex items-start justify-between mb-4">
                <div>
                    <h2 className="text-xl font-bold text-slate-900">Import Books</h2>
                    <p className="text-slate-500 mt-1">
                        Upload a JSON file to add books to your library.
                    </p>
                </div>
                <div className="p-3 bg-[#262D40]/5 text-[#262D40] rounded-lg">
                    <FileJson size={24} />
                </div>
            </div>

            {error && (
                <div className="mb-4 p-4 bg-red-50 text-red-700 rounded-lg flex items-center gap-2">
                    <AlertCircle size={20} />
                    {error}
                </div>
            )}

            {completed ? (
                <div className="mb-4 p-4 bg-green-50 text-green-700 rounded-lg flex items-center gap-2">
                    <Check size={20} />
                    Successfully imported {total} books!
                </div>
            ) : null}

            {importing ? (
                <div className="space-y-2">
                    <div className="flex justify-between text-sm text-slate-600">
                        <span>Importing...</span>
                        <span>{Math.round((progress / total) * 100)}%</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                        <div
                            className="bg-[#262D40]/40 h-2.5 rounded-full transition-all duration-300"
                            style={{ width: `${(progress / total) * 100}%` }}
                        ></div>
                    </div>
                    <p className="text-xs text-slate-400 text-center mt-2">
                        {progress} / {total} books processed
                    </p>
                </div>
            ) : (
                <>
                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleFileChange}
                        accept=".json"
                        className="hidden"
                    />
                    <button
                        onClick={triggerFileInput}
                        disabled={importing}
                        className="w-full py-3 px-4 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors bg-[#262D40]/40 hover:bg-[#262D40]/55 text-white shadow-md hover:shadow-lg"
                    >
                        <Upload size={20} />
                        Select JSON File
                    </button>
                </>
            )}
        </div>
    );
};
