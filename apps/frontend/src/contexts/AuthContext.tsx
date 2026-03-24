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

const shouldPreferRedirectAuth = (): boolean => {
    if (typeof window === "undefined" || typeof navigator === "undefined") {
        return false;
    }

    const hostname = window.location.hostname.toLowerCase();
    if (popupSafeHosts.has(hostname)) {
        return false;
    }

    const userAgent = navigator.userAgent || "";
    const isMobileDevice = /android|iphone|ipad|ipod/i.test(userAgent);
    const isInAppBrowser = /FBAN|FBAV|Instagram|Line|Twitter|WebView/i.test(userAgent);

    return isMobileDevice || isInAppBrowser;
};

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
            if (shouldPreferRedirectAuth()) {
                await signInWithRedirect(auth, googleProvider);
                return;
            }

            await signInWithPopup(auth, googleProvider);
        } catch (error: any) {
            console.error("Login with Google failed:", error);
            if (
                error?.code === 'auth/popup-blocked' ||
                error?.code === 'auth/operation-not-supported-in-this-environment'
            ) {
                showToast({
                    title: "Yedek giris akisi kullaniliyor",
                    description: "Popup tamamlanamadi. Google girisi yonlendirme ile devam edecek.",
                    tone: "warning",
                });
                await signInWithRedirect(auth, googleProvider);
                return;
            }
            if (error.code === 'auth/popup-closed-by-user') {
                return;
            }
            if (error.code === 'auth/cancelled-popup-request') {
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
