const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const admin = require("firebase-admin");

// Initialize Firebase Admin SDK
admin.initializeApp();

// Gemini API key secret
const geminiApiKey = defineSecret("GEMINI_API_KEY");

// Allowed origins for CORS
const ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://faksxs.github.io",
];

// Rate limiting configuration
const RATE_LIMIT = 10; // requests per window
const WINDOW_MS = 60000; // 1 minute

// HTTP endpoint: bookEnrichmentHttp
exports.bookEnrichmentHttp = onRequest(
    {
        region: "us-central1",
        secrets: [geminiApiKey],
    },
    async (req, res) => {
        const origin = req.headers.origin;

        // CORS headers
        if (ALLOWED_ORIGINS.includes(origin)) {
            res.set("Access-Control-Allow-Origin", origin);
            res.set("Vary", "Origin");
        }

        // Preflight (OPTIONS) request
        if (req.method === "OPTIONS") {
            res.set("Access-Control-Allow-Methods", "POST, OPTIONS");
            res.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
            return res.status(204).send("");
        }

        // ===== AUTHENTICATION CHECK =====
        const authHeader = req.headers.authorization;
        if (!authHeader || !authHeader.startsWith("Bearer ")) {
            return res.status(401).json({
                success: false,
                error: "Unauthorized: Missing or invalid authorization header",
            });
        }

        const idToken = authHeader.split("Bearer ")[1];
        let decodedToken;

        try {
            decodedToken = await admin.auth().verifyIdToken(idToken);
        } catch (error) {
            console.error("Token verification failed:", error);
            return res.status(401).json({
                success: false,
                error: "Unauthorized: Invalid token",
            });
        }

        const userId = decodedToken.uid;

        // ===== RATE LIMITING =====
        try {
            const rateLimitRef = admin.firestore()
                .collection("rateLimits")
                .doc(userId);

            const rateLimitDoc = await rateLimitRef.get();
            const now = Date.now();

            if (rateLimitDoc.exists) {
                const data = rateLimitDoc.data();
                const windowStart = data.windowStart;

                // Check if we're still in the same time window
                if (now - windowStart < WINDOW_MS) {
                    if (data.count >= RATE_LIMIT) {
                        return res.status(429).json({
                            success: false,
                            error: "Rate limit exceeded. Please try again in a minute.",
                        });
                    }

                    // Increment count
                    await rateLimitRef.update({
                        count: admin.firestore.FieldValue.increment(1),
                    });
                } else {
                    // New window, reset
                    await rateLimitRef.set({
                        count: 1,
                        windowStart: now,
                    });
                }
            } else {
                // First request
                await rateLimitRef.set({
                    count: 1,
                    windowStart: now,
                });
            }
        } catch (error) {
            console.error("Rate limiting error:", error);
            // Continue execution even if rate limiting fails
        }

        // ===== PROCESS REQUEST =====
        try {
            const userPrompt = req.body?.prompt;

            if (!userPrompt) {
                return res.status(400).json({
                    success: false,
                    error: "Prompt is required.",
                });
            }

            const genAI = new GoogleGenerativeAI(geminiApiKey.value());
            const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });

            const result = await model.generateContent(userPrompt);
            const response = await result.response;
            const text = response.text();

            return res.status(200).json({
                success: true,
                message: text,
            });
        } catch (error) {
            console.error("Cloud Function Error (HTTP):", error);

            return res.status(500).json({
                success: false,
                error: error.message || "An error occurred in the AI service.",
            });
        }
    }
);
