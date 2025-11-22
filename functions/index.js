const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const { GoogleGenerativeAI } = require("@google/generative-ai");

// Gemini API key secret
const geminiApiKey = defineSecret("GEMINI_API_KEY");

// Allowed origins for CORS
const ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://faksxs.github.io",
];

// HTTP endpoint: bookEnrichmentHttp
exports.bookEnrichmentHttp = onRequest(
    {
        region: "us-central1",
        secrets: [geminiApiKey],
    },
    async (req, res) => {
        const origin = req.headers.origin;

        // Eğer istek gelen origin listede varsa CORS header ekle
        if (ALLOWED_ORIGINS.includes(origin)) {
            res.set("Access-Control-Allow-Origin", origin);
            res.set("Vary", "Origin");
        }

        // Preflight (OPTIONS) isteğini yönet
        if (req.method === "OPTIONS") {
            res.set("Access-Control-Allow-Methods", "POST, OPTIONS");
            res.set("Access-Control-Allow-Headers", "Content-Type");
            return res.status(204).send("");
        }

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
