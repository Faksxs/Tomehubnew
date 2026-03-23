import React, { useEffect, useState } from 'react';
import {
    BrainCircuit,
    CheckCircle2,
    Database,
    Film,
    Globe,
    Library,
    Loader2,
    ScrollText,
    Search,
    Server,
} from 'lucide-react';
import { getApiPreferences, updateApiPreferences } from '../services/backendApiService';

interface ApiIntegrationsProps {
    userId: string;
}

const AVAILABLE_PROVIDERS = [
    { id: 'ARXIV', name: 'Arxiv Preprints', description: 'Recent preprints for Academic discovery cards.', category: 'Academic', icon: <Library className="w-5 h-5 text-red-500" /> },
    { id: 'CROSSREF', name: 'Crossref', description: 'Bibliographic reinforcement for Bridge and Deepen cards.', category: 'Academic', icon: <Search className="w-5 h-5 text-sky-500" /> },
    { id: 'SEMANTIC_SCHOLAR', name: 'Semantic Scholar', description: 'Academic graph support for bridge-style research cards.', category: 'Academic', icon: <Search className="w-5 h-5 text-blue-500" /> },
    { id: 'OPENALEX', name: 'OpenAlex', description: 'Primary graph source for research discovery cards.', category: 'Academic', icon: <Globe className="w-5 h-5 text-teal-500" /> },
    { id: 'SHARE', name: 'SHARE / OSF', description: 'Open scholarship context for deeper academic cards.', category: 'Academic', icon: <Database className="w-5 h-5 text-cyan-500" /> },
    { id: 'ORKG', name: 'ORKG', description: 'Structured research-knowledge views for Deepen cards.', category: 'Academic', icon: <Database className="w-5 h-5 text-indigo-500" /> },
    { id: 'QURANENC', name: 'QuranEnc', description: 'Verse-first reference source for Religious discovery.', category: 'Religious', icon: <ScrollText className="w-5 h-5 text-emerald-500" /> },
    { id: 'HADEETHENC', name: 'HadeethEnc', description: 'Hadith support for ayet and hadis bridge cards.', category: 'Religious', icon: <ScrollText className="w-5 h-5 text-lime-500" /> },
    { id: 'ISLAMHOUSE', name: 'IslamHouse', description: 'Supplemental source for grounded interpretive context.', category: 'Religious', icon: <ScrollText className="w-5 h-5 text-green-600" /> },
    { id: 'GOOGLE_BOOKS', name: 'Google Books', description: 'Primary metadata source for Literary continuation cards.', category: 'Literary', icon: <Library className="w-5 h-5 text-blue-500" /> },
    { id: 'OPEN_LIBRARY', name: 'Open Library', description: 'Secondary book metadata and open catalog support.', category: 'Literary', icon: <Library className="w-5 h-5 text-amber-600" /> },
    { id: 'GUTENDEX', name: 'Gutendex', description: 'Public-domain classics and parallel literary work discovery.', category: 'Literary', icon: <Library className="w-5 h-5 text-amber-500" /> },
    { id: 'TMDB', name: 'TMDb', description: 'Selective film and series mapping for Literary discovery.', category: 'Literary', icon: <Film className="w-5 h-5 text-rose-500" /> },
    { id: 'WIKIDATA', name: 'Wikidata', description: 'Knowledge graph enrichment for lineage and historic relations.', category: 'Culture', icon: <Database className="w-5 h-5 text-gray-500" /> },
    { id: 'DBPEDIA', name: 'DBpedia', description: 'Secondary entity graph support for Culture cards.', category: 'Culture', icon: <Database className="w-5 h-5 text-slate-500" /> },
    { id: 'EUROPEANA', name: 'Europeana', description: 'Digital cultural heritage platform for archive artifacts.', category: 'Culture', icon: <Globe className="w-5 h-5 text-indigo-500" /> },
    { id: 'INTERNET_ARCHIVE', name: 'Internet Archive', description: 'Archive scans and historical object context.', category: 'Culture', icon: <Database className="w-5 h-5 text-stone-500" /> },
    { id: 'ART_SEARCH_API', name: 'Art Search API', description: 'Museum artwork context for Culture cards.', category: 'Culture', icon: <Globe className="w-5 h-5 text-fuchsia-500" /> },
    { id: 'POETRYDB', name: 'PoetryDB', description: 'Low-frequency Wild Card support when a cultural surprise is useful.', category: 'Culture', icon: <Library className="w-5 h-5 text-violet-500" /> },
];

const CATEGORY_ORDER = ['Academic', 'Religious', 'Literary', 'Culture'] as const;

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
        const newPrefs = { ...preferences, [providerId]: newValue };
        setPreferences(newPrefs);

        try {
            setSaving(true);
            await updateApiPreferences(userId, newPrefs);
            setSuccessMessage('Settings updated successfully.');
            setTimeout(() => setSuccessMessage(null), 3000);
        } catch (err) {
            console.error('Failed to update API preferences:', err);
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
                            Manage which external APIs are used by Layer 3 Explorer and the Discovery board.
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

                <div className="space-y-8">
                    {CATEGORY_ORDER.map((category) => {
                        const providers = AVAILABLE_PROVIDERS.filter((provider) => provider.category === category);
                        if (providers.length === 0) return null;

                        return (
                            <section key={category}>
                                <div className="mb-4">
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                                        Layer 3 Category
                                    </p>
                                    <h3 className="mt-1 text-lg font-bold text-slate-900 dark:text-white">{category}</h3>
                                </div>
                                <div className="grid gap-4 md:grid-cols-2">
                                    {providers.map((provider) => {
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
                                                            <h4 className={`font-semibold ${isEnabled ? 'text-slate-900 dark:text-white' : 'text-slate-500 dark:text-slate-400'}`}>
                                                                {provider.name}
                                                            </h4>
                                                            <span className="text-[10px] font-medium tracking-wider uppercase text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full inline-block mt-1">
                                                                {provider.category}
                                                            </span>
                                                        </div>
                                                    </div>

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
                            </section>
                        );
                    })}
                </div>

                <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-800 flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                    <BrainCircuit className="w-5 h-5" />
                    <p>Disabling a provider can suppress entire discovery card families inside its Layer 3 category.</p>
                </div>
            </div>
        </div>
    );
};
