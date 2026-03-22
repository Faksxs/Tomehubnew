import React, { useEffect, useState } from 'react';
import { getApiPreferences, updateApiPreferences } from '../services/backendApiService';
import { Database, Loader2, Server, Globe, Search, BrainCircuit, Library, CheckCircle2 } from 'lucide-react';

interface ApiIntegrationsProps {
    userId: string;
}

// Pre-defined available integrations with metadata
const AVAILABLE_PROVIDERS = [
    {
        id: 'ARXIV',
        name: 'Arxiv Preprints',
        description: 'Enables real-time searching of academic papers and preprints from Arxiv in Layer 3 Explorer.',
        icon: <Library className="w-5 h-5 text-red-500" />,
        domain: 'ACADEMIC'
    },
    {
        id: 'SEMANTIC_SCHOLAR',
        name: 'Semantic Scholar',
        description: 'Advanced academic graph for citations and cross-references.',
        icon: <Search className="w-5 h-5 text-blue-500" />,
        domain: 'ACADEMIC'
    },
    {
        id: 'OPENALEX',
        name: 'OpenAlex',
        description: 'Open catalog of the global research system.',
        icon: <Globe className="w-5 h-5 text-teal-500" />,
        domain: 'ACADEMIC'
    },
    {
        id: 'WIKIDATA',
        name: 'Wikidata & DBpedia',
        description: 'Knowledge graph enrichment for entities, places, and historic concepts.',
        icon: <Database className="w-5 h-5 text-gray-500" />,
        domain: 'GENERAL'
    },
    {
        id: 'EUROPEANA',
        name: 'Europeana',
        description: 'Digital cultural heritage platform for history and art.',
        icon: <Globe className="w-5 h-5 text-indigo-500" />,
        domain: 'CULTURE_HISTORY'
    },
    {
        id: 'GUTENDEX',
        name: 'Gutendex (Project Gutenberg)',
        description: 'Public domain literature and book metadata.',
        icon: <Library className="w-5 h-5 text-amber-500" />,
        domain: 'LITERARY'
    }
];

export const ApiIntegrations: React.FC<ApiIntegrationsProps> = ({ userId }) => {
    const [preferences, setPreferences] = useState<Record<string, boolean>>({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    useEffect(() => {
        if (!userId) return;
        
        const fetchPrefs = async () => {
            setLoading(true);
            try {
                const data = await getApiPreferences(userId);
                setPreferences(data);
                setError(null);
            } catch (err) {
                console.error('Failed to fetch API preferences:', err);
                setError('Failed to load API settings. Please try again.');
            } finally {
                setLoading(false);
            }
        };
        fetchPrefs();
    }, [userId]);

    const handleToggle = async (providerId: string, currentValue: boolean) => {
        const newValue = !currentValue;
        
        // Optimistically update local state
        const newPrefs = { ...preferences, [providerId]: newValue };
        setPreferences(newPrefs);
        
        try {
            setSaving(true);
            await updateApiPreferences(userId, newPrefs);
            setSuccessMessage('Settings updated successfully.');
            setTimeout(() => setSuccessMessage(null), 3000);
        } catch (err) {
            console.error('Failed to update API preferences:', err);
            // Revert on failure
            setPreferences(preferences);
            setError('Failed to save settings.');
            setTimeout(() => setError(null), 3000);
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-8 flex justify-center items-center">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                <span className="ml-3 text-slate-500 dark:text-slate-400">Loading Integrations...</span>
            </div>
        );
    }

    return (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden mb-8">
            <div className="p-6 md:p-8 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-xl">
                        <Server className="w-6 h-6" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-slate-900 dark:text-white">Data Sources & Integrations</h2>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                            Manage which external APIs are used during Layer 3 Explorer searches.
                        </p>
                    </div>
                </div>
            </div>

            <div className="p-6 md:p-8">
                {error && (
                    <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-100 dark:border-red-900/30">
                        {error}
                    </div>
                )}
                {successMessage && (
                    <div className="mb-6 p-4 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 flex items-center gap-2 text-sm border border-emerald-100 dark:border-emerald-900/30">
                        <CheckCircle2 className="w-4 h-4" />
                        {successMessage}
                    </div>
                )}

                <div className="grid gap-4 md:grid-cols-2">
                    {AVAILABLE_PROVIDERS.map((provider) => {
                        // Default is true if not explicitly set to false in the DB.
                        const isEnabled = preferences[provider.id] !== false;
                        
                        return (
                            <div 
                                key={provider.id} 
                                className={`p-5 rounded-xl border transition-all duration-200 flex flex-col justify-between ${
                                    isEnabled 
                                        ? 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm' 
                                        : 'border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 opacity-75'
                                }`}
                            >
                                <div className="flex items-start justify-between mb-4">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-slate-100 dark:bg-slate-900 rounded-lg">
                                            {provider.icon}
                                        </div>
                                        <div>
                                            <h3 className={`font-semibold ${isEnabled ? 'text-slate-900 dark:text-white' : 'text-slate-500 dark:text-slate-400'}`}>
                                                {provider.name}
                                            </h3>
                                            <span className="text-[10px] font-medium tracking-wider uppercase text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full inline-block mt-1">
                                                {provider.domain}
                                            </span>
                                        </div>
                                    </div>
                                    
                                    {/* Toggle Switch */}
                                    <button
                                        type="button"
                                        role="switch"
                                        aria-checked={isEnabled}
                                        onClick={() => handleToggle(provider.id, isEnabled)}
                                        disabled={saving}
                                        className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#262D40] focus:ring-offset-2 ${
                                            isEnabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700'
                                        } ${saving ? 'opacity-50 cursor-not-allowed' : ''}`}
                                    >
                                        <span
                                            aria-hidden="true"
                                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                                isEnabled ? 'translate-x-5' : 'translate-x-0'
                                            }`}
                                        />
                                    </button>
                                </div>
                                <p className={`text-sm ${isEnabled ? 'text-slate-600 dark:text-slate-300' : 'text-slate-400 dark:text-slate-500'}`}>
                                    {provider.description}
                                </p>
                            </div>
                        );
                    })}
                </div>
                
                <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-800 flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                    <BrainCircuit className="w-5 h-5" />
                    <p>These settings only apply to <strong>Layer 3 Explorer</strong> searches. Disabling an API may limit the depth and breadth of intelligent research across your library.</p>
                </div>
            </div>
        </div>
    );
};
