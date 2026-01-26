import React, { useState, useRef } from 'react';
import { Upload, FileText, Loader2, CheckCircle, AlertCircle, User, X } from 'lucide-react';
import { ingestDocument, IngestResponse } from '../services/backendApiService';

interface DocumentIngestProps {
    userId: string;
    userEmail?: string | null;
}

export const DocumentIngest: React.FC<DocumentIngestProps> = ({ userId, userEmail }) => {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [title, setTitle] = useState('');
    const [author, setAuthor] = useState('');
    const [isIngesting, setIsIngesting] = useState(false);
    const [result, setResult] = useState<IngestResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleDrag = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            handleFileSelect(e.target.files[0]);
        }
    };

    const handleFileSelect = (file: File) => {
        if (file.type !== "application/pdf") {
            setError("Please select a PDF file");
            return;
        }
        setSelectedFile(file);
        setError(null);
        // Auto-fill title from filename if empty
        if (!title) {
            const name = file.name.replace('.pdf', '').replace(/_/g, ' ');
            setTitle(name);
        }
    };

    const handleIngest = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!selectedFile || !title.trim() || !author.trim()) {
            setError('All fields are required');
            return;
        }

        setIsIngesting(true);
        setError(null);
        setResult(null);

        try {
            const response = await ingestDocument(selectedFile, title, author, userId);
            setResult(response);
            // Clear form on success
            setSelectedFile(null);
            setTitle('');
            setAuthor('');
            if (fileInputRef.current) fileInputRef.current.value = '';
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Ingestion failed');
        } finally {
            setIsIngesting(false);
        }
    };

    return (
        <div className="max-w-2xl mx-auto p-6 space-y-6">
            {/* Header */}
            <div className="text-center space-y-2">
                <div className="flex items-center justify-center gap-2">
                    <Upload className="w-8 h-8 text-indigo-600" />
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
                        Ingest Document
                    </h1>
                </div>
                <p className="text-slate-600 dark:text-slate-400">
                    Upload a PDF to your searchable library
                </p>
                {userEmail && (
                    <div className="flex items-center justify-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                        <User className="w-4 h-4" />
                        <span>Adding to library for: {userEmail}</span>
                    </div>
                )}
            </div>

            {/* Form */}
            <form onSubmit={handleIngest} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 space-y-4">

                {/* File Drop Zone */}
                <div
                    className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer
                ${dragActive
                            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/10'
                            : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400 dark:hover:border-slate-500'
                        }
                ${selectedFile ? 'bg-indigo-50/50 dark:bg-slate-700/30' : ''}
            `}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        className="hidden"
                        accept=".pdf"
                        onChange={handleChange}
                    />

                    {selectedFile ? (
                        <div className="flex flex-col items-center gap-2 text-indigo-600 dark:text-indigo-400">
                            <FileText className="w-10 h-10" />
                            <span className="font-medium">{selectedFile.name}</span>
                            <span className="text-xs text-slate-500">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</span>
                            <button
                                type="button"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedFile(null);
                                }}
                                className="mt-2 text-xs text-red-500 hover:text-red-600 flex items-center gap-1"
                            >
                                <X className="w-3 h-3" /> Remove
                            </button>
                        </div>
                    ) : (
                        <div className="flex flex-col items-center gap-2 text-slate-500 dark:text-slate-400">
                            <Upload className="w-10 h-10 mb-2" />
                            <p className="font-medium">Click to upload or drag and drop</p>
                            <p className="text-xs">PDF files only</p>
                        </div>
                    )}
                </div>

                {/* Title */}
                <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Book Title
                    </label>
                    <input
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="Book Title"
                        className="w-full px-4 py-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        disabled={isIngesting}
                    />
                </div>

                {/* Author */}
                <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Author
                    </label>
                    <input
                        type="text"
                        value={author}
                        onChange={(e) => setAuthor(e.target.value)}
                        placeholder="Author Name"
                        className="w-full px-4 py-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        disabled={isIngesting}
                    />
                </div>

                {/* Submit Button */}
                <button
                    type="submit"
                    disabled={isIngesting || !selectedFile || !title.trim() || !author.trim()}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 dark:disabled:bg-slate-700 text-white font-medium py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                    {isIngesting ? (
                        <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            Ingesting... (This may take several minutes)
                        </>
                    ) : (
                        <>
                            <Upload className="w-5 h-5" />
                            Upload & Ingest Document
                        </>
                    )}
                </button>
            </form>

            {/* Success Message */}
            {result && (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-4 flex items-start gap-3">
                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                    <div>
                        <h3 className="font-medium text-green-900 dark:text-green-100">Success!</h3>
                        <p className="text-sm text-green-700 dark:text-green-300 mt-1">{result.message}</p>
                    </div>
                </div>
            )}

            {/* Error Message */}
            {error && (
                <div className={`rounded-xl p-4 flex items-start gap-3 border ${error === "ALREADY_EXISTS"
                        ? "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800"
                        : "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800"
                    }`}>
                    <AlertCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${error === "ALREADY_EXISTS" ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"
                        }`} />
                    <div>
                        <h3 className={`font-medium ${error === "ALREADY_EXISTS" ? "text-amber-900 dark:text-amber-100" : "text-red-900 dark:text-red-100"
                            }`}>
                            {error === "ALREADY_EXISTS" ? "Already in Library" : "Ingestion Failed"}
                        </h3>
                        <p className={`text-sm mt-1 ${error === "ALREADY_EXISTS" ? "text-amber-700 dark:text-amber-300" : "text-red-700 dark:text-red-300"
                            }`}>
                            {error === "ALREADY_EXISTS"
                                ? `The book "${title}" is already in your AI library. No need to re-upload.`
                                : error}
                        </p>
                    </div>
                </div>
            )}

            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
                <h3 className="font-medium text-blue-900 dark:text-blue-100 mb-2">How it works:</h3>
                <ul className="text-sm text-blue-700 dark:text-blue-300 space-y-1 list-disc list-inside">
                    <li>Upload a PDF file (max 50MB)</li>
                    <li>File is uploaded securely to the server</li>
                    <li>Content is extracted and vectorized</li>
                    <li>Document is added to your AI library</li>
                </ul>
            </div>
        </div>
    );
};
