import React from 'react';
import { LogOut, User, ArrowLeft } from 'lucide-react';

interface ProfileViewProps {
    email: string | null | undefined;
    onLogout: () => void;
    onBack: () => void;
}

export const ProfileView: React.FC<ProfileViewProps> = ({ email, onLogout, onBack }) => {
    return (
        <div className="p-6 md:p-10 max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4">
            {/* Back Button */}
            <button
                onClick={onBack}
                className="flex items-center gap-2 text-slate-600 hover:text-slate-900 mb-6 transition-colors group"
            >
                <ArrowLeft size={20} className="group-hover:-translate-x-1 transition-transform" />
                <span className="font-medium">Back</span>
            </button>

            <div className="mb-8">
                <h1 className="text-3xl font-bold text-slate-900">Profile</h1>
                <p className="text-slate-500 mt-2">Manage your account settings</p>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-6 md:p-8 border-b border-slate-100 flex flex-col md:flex-row items-start md:items-center gap-6">
                    <div className="w-20 h-20 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-600">
                        <User size={40} />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-slate-900">Account Information</h2>
                        <p className="text-slate-500 mt-1">Signed in as</p>
                        <p className="text-lg font-medium text-slate-900 mt-1">{email || 'No email available'}</p>
                    </div>
                </div>

                <div className="p-6 md:p-8 bg-slate-50/50">
                    <button
                        onClick={onLogout}
                        className="flex items-center gap-2 px-6 py-3 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg font-medium transition-colors border border-red-100"
                    >
                        <LogOut size={20} />
                        Log Out
                    </button>
                </div>
            </div>
        </div>
    );
};
