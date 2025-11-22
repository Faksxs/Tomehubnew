/**
 * arXiv API Proxy Server
 * 
 * This Express server acts as a proxy to handle CORS issues when accessing
 * the arXiv API from browser-based React applications.
 * 
 * Features:
 * - CORS handling for cross-origin requests
 * - Response caching to reduce API load
 * - Rate limiting to prevent abuse
 * - Security headers via Helmet
 * - Error handling and logging
 */

const express = require('express');
const cors = require('cors');
const NodeCache = require('node-cache');
const rateLimit = require('express-rate-limit');
const helmet = require('helmet');
require('dotenv').config();

const app = express();
const PORT = process.env.PROXY_PORT || 3001;

// ============================================================================
// CACHING CONFIGURATION
// ============================================================================
// Cache arXiv responses for 1 hour (3600 seconds)
// This reduces load on arXiv servers and improves response times
const cache = new NodeCache({
    stdTTL: 3600,           // Cache for 1 hour
    checkperiod: 600,       // Check for expired entries every 10 minutes
    useClones: false        // Don't clone objects (better performance)
});

// ============================================================================
// SECURITY MIDDLEWARE
// ============================================================================
// Helmet adds various HTTP headers for security
app.use(helmet());

// CORS configuration - allow requests from your React app
const corsOptions = {
    origin: process.env.FRONTEND_URL || 'http://localhost:3000',
    methods: ['GET'],
    allowedHeaders: ['Content-Type'],
    credentials: false,
    maxAge: 86400 // Cache preflight requests for 24 hours
};
app.use(cors(corsOptions));

// ============================================================================
// RATE LIMITING
// ============================================================================
// Limit each IP to 100 requests per 15 minutes
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 100, // Limit each IP to 100 requests per windowMs
    message: 'Too many requests from this IP, please try again later.',
    standardHeaders: true, // Return rate limit info in the `RateLimit-*` headers
    legacyHeaders: false, // Disable the `X-RateLimit-*` headers
});

// Apply rate limiting to all routes
app.use(limiter);

// Parse JSON bodies
app.use(express.json());

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Generate a cache key from the request query parameters
 */
function generateCacheKey(query) {
    return `arxiv:${query.search_query}:${query.start || 0}:${query.max_results || 10}`;
}

/**
 * Fetch data from arXiv API
 */
async function fetchFromArxiv(queryParams) {
    const baseUrl = 'https://export.arxiv.org/api/query';
    const params = new URLSearchParams(queryParams);
    const url = `${baseUrl}?${params.toString()}`;

    console.log(`[arXiv] Fetching: ${url}`);

    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`arXiv API error: ${response.status} ${response.statusText}`);
    }

    const xmlText = await response.text();
    return xmlText;
}

// ============================================================================
// ROUTES
// ============================================================================

/**
 * Health check endpoint
 */
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        timestamp: new Date().toISOString(),
        cache: {
            keys: cache.keys().length,
            stats: cache.getStats()
        }
    });
});

/**
 * arXiv API Proxy Endpoint
 * 
 * GET /api/arxiv?search_query=all:quantum&start=0&max_results=10
 * 
 * Query Parameters:
 * - search_query: Search query (required)
 * - start: Starting index (default: 0)
 * - max_results: Number of results (default: 10, max: 100)
 */
app.get('/api/arxiv', async (req, res) => {
    try {
        const { search_query, start = '0', max_results = '10' } = req.query;

        // Validate required parameters
        if (!search_query) {
            return res.status(400).json({
                error: 'Missing required parameter: search_query'
            });
        }

        // Validate max_results
        const maxResults = parseInt(max_results, 10);
        if (maxResults > 100) {
            return res.status(400).json({
                error: 'max_results cannot exceed 100'
            });
        }

        // Check cache first
        const cacheKey = generateCacheKey(req.query);
        const cachedData = cache.get(cacheKey);

        if (cachedData) {
            console.log(`[Cache HIT] ${cacheKey}`);
            return res
                .set('Content-Type', 'application/xml')
                .set('X-Cache', 'HIT')
                .send(cachedData);
        }

        console.log(`[Cache MISS] ${cacheKey}`);

        // Fetch from arXiv
        const xmlData = await fetchFromArxiv(req.query);

        // Store in cache
        cache.set(cacheKey, xmlData);

        // Return response
        res
            .set('Content-Type', 'application/xml')
            .set('X-Cache', 'MISS')
            .send(xmlData);

    } catch (error) {
        console.error('[Error]', error.message);

        // Return appropriate error response
        if (error.message.includes('arXiv API error')) {
            res.status(502).json({
                error: 'Failed to fetch from arXiv API',
                details: error.message
            });
        } else {
            res.status(500).json({
                error: 'Internal server error',
                details: process.env.NODE_ENV === 'development' ? error.message : undefined
            });
        }
    }
});

/**
 * Cache management endpoint (optional, for debugging)
 */
app.get('/api/cache/stats', (req, res) => {
    res.json({
        keys: cache.keys().length,
        stats: cache.getStats()
    });
});

app.delete('/api/cache/clear', (req, res) => {
    cache.flushAll();
    res.json({ message: 'Cache cleared successfully' });
});

// ============================================================================
// ERROR HANDLING
// ============================================================================

// 404 handler
app.use((req, res) => {
    res.status(404).json({ error: 'Endpoint not found' });
});

// Global error handler
app.use((err, req, res, next) => {
    console.error('[Global Error]', err);
    res.status(500).json({
        error: 'Internal server error',
        details: process.env.NODE_ENV === 'development' ? err.message : undefined
    });
});

// ============================================================================
// START SERVER
// ============================================================================

app.listen(PORT, () => {
    console.log(`
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🚀 arXiv Proxy Server Running                          ║
║                                                           ║
║   Port:        ${PORT}                                        ║
║   Environment: ${process.env.NODE_ENV || 'development'}                              ║
║   Frontend:    ${process.env.FRONTEND_URL || 'http://localhost:3000'}              ║
║                                                           ║
║   Endpoints:                                              ║
║   - GET  /health                                          ║
║   - GET  /api/arxiv?search_query=...                      ║
║   - GET  /api/cache/stats                                 ║
║   - DEL  /api/cache/clear                                 ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
  `);
});

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('SIGTERM received, closing server...');
    cache.flushAll();
    process.exit(0);
});

process.on('SIGINT', () => {
    console.log('SIGINT received, closing server...');
    cache.flushAll();
    process.exit(0);
});
