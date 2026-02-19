import React, {
    createContext,
    useContext,
    useEffect,
    useState,
    ReactNode,
} from "react";
import {
    User,
    onAuthStateChanged,
    signInWithPopup,
    getRedirectResult,
    signOut,
} from "firebase/auth";
import { auth, googleProvider } from "../services/firebaseClient";

interface AuthContextValue {
    user: User | null;
    loading: boolean;
    loginWithGoogle: () => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({
    children,
}) => {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    // Kullanıcı oturum durumunu izle
    useEffect(() => {
        // Handle redirect results (important for mobile/restricted environments)
        // Some mobile browsers fallback to redirect even when signInWithPopup is called.
        getRedirectResult(auth)
            .then((result) => {
                if (result) {
                    console.log("Successfully signed in with redirect");
                }
            })
            .catch((error) => {
                console.error("Redirect login error:", error);
                // If it's a "missing initial state" error, it often means the session was lost
                // but we shouldn't block the app loading.
            });

        const unsub = onAuthStateChanged(auth, (firebaseUser) => {
            setUser(firebaseUser);
            setLoading(false);
        });
        return () => unsub();
    }, []);

    const loginWithGoogle = async () => {
        try {
            // Mobile users often have popups blocked, but signInWithPopup is generally
            // more reliable than redirect on modern browsers if triggered by a click.
            await signInWithPopup(auth, googleProvider);
        } catch (error: any) {
            console.error("Login with Google failed:", error);
            if (error.code === 'auth/popup-blocked') {
                alert("Giriş penceresi engellendi. Lütfen Safari veya Chrome gibi bir tarayıcıda açın veya pop-uplara izin verin.");
            } else if (error.code === 'auth/cancelled-popup-request') {
                // Ignore user cancellation
            } else {
                alert("Giriş hatası: " + (error.message || "Bilinmeyen bir hata oluştu."));
            }
        }
    };

    const logout = async () => {
        await signOut(auth);
    };

    const value: AuthContextValue = {
        user,
        loading,
        loginWithGoogle,
        logout,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
    const ctx = useContext(AuthContext);
    if (!ctx) {
        throw new Error("useAuth must be used within AuthProvider");
    }
    return ctx;
};
