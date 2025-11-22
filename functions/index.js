const { onCall } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const { GoogleGenerativeAI } = require("@google/generative-ai");

// Define the secret for Gemini API Key
const geminiApiKey = defineSecret("GEMINI_API_KEY");

// Cloud Function: bookEnrichment
exports.bookEnrichment = onCall(
    {
        secrets: [geminiApiKey],
        region: "us-central1",
    },
    async (request) => {
        try {
            // Validate input
            const userPrompt = request.data?.prompt;

            if (!userPrompt) {
                return { success: false, error: "Prompt is required." };
            }

            // Initialize Gemini AI
            const genAI = new GoogleGenerativeAI(geminiApiKey.value());
            const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });

            // Generate content
            const result = await model.generateContent(userPrompt);
            const response = await result.response;
            const text = response.text();

            // Return success response
            return { success: true, message: text };
        } catch (error) {
            console.error("Cloud Function Error:", error);

            return {
                success: false,
                error: error.message || "An error occurred in the AI service.",
            };
        }
    }
);
