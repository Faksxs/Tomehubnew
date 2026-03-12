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
    signInWithRedirect,
    getRedirectResult,
    signOut,
} from "firebase/auth";
import { auth, googleProvider } from "../services/firebaseClient";
import { useUiFeedback } from "../shared/ui/feedback/useUiFeedback";

interface AuthContextValue {
    user: User | null;
    loading: boolean;
    loginWithGoogle: () => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const popupSafeHosts = new Set(["localhost", "127.0.0.1", "::1"]);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({
    children,
}) => {
    const { showToast } = useUiFeedback();
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
            const useRedirect =
                typeof window !== "undefined" &&
                !popupSafeHosts.has(window.location.hostname.toLowerCase());

            if (useRedirect) {
                await signInWithRedirect(auth, googleProvider);
                return;
            }

            await signInWithPopup(auth, googleProvider);
        } catch (error: any) {
            console.error("Login with Google failed:", error);
            if (error.code === 'auth/popup-blocked') {
                showToast({
                    title: "Giris penceresi engellendi",
                    description: "Lutfen Safari veya Chrome gibi bir tarayicida acin ya da pop-up izni verin.",
                    tone: "warning",
                });
            } else if (error.code === 'auth/cancelled-popup-request') {
                // Ignore user cancellation
            } else {
                showToast({
                    title: "Giris hatasi",
                    description: error.message || "Bilinmeyen bir hata olustu.",
                    tone: "error",
                });
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
