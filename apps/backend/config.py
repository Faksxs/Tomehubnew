
import os
import logging
import re
from typing import List, Optional, Dict
from dotenv import load_dotenv

# Load backend/.env deterministically regardless of process working directory.
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_CONFIG_DIR, ".env")
load_dotenv(dotenv_path=_ENV_PATH)

logger = logging.getLogger(__name__)


def _parse_csv_upper(raw: str) -> List[str]:
    return [part.strip().upper() for part in str(raw or "").split(",") if part.strip()]


def _parse_csv(raw: str) -> List[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


class Settings:
    def __init__(self):
        # Environment mode
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        self.DEBUG_VERBOSE_PIPELINE = (
            os.getenv("DEBUG_VERBOSE_PIPELINE", "false").strip().lower() == "true"
        )
        
        # Database
        self.DB_USER = os.getenv("DB_USER", "ADMIN")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD")
        self.DB_DSN = os.getenv("DB_DSN", "tomehubdb_high")
        
        # Database Connection Pool (Task A1 + C1)
        self.DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "5"))
        self.DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "40"))  # Increased from 20
        self.DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))  # seconds
        self.DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour
        
        # C1: Separate Pool Sizing
        # Default: 75% for reads (search, RAG), 25% for writes (ingestion, logs)
        self.DB_READ_POOL_MAX = int(os.getenv("DB_READ_POOL_MAX", str(int(self.DB_POOL_MAX * 0.75))))
        self.DB_WRITE_POOL_MAX = int(os.getenv("DB_WRITE_POOL_MAX", str(int(self.DB_POOL_MAX * 0.25))))

        # OCI PDF storage / parsing
        self.OCI_TENANCY_OCID = os.getenv("OCI_TENANCY_OCID", "").strip()
        self.OCI_COMPARTMENT_OCID = os.getenv("OCI_COMPARTMENT_OCID", "").strip() or self.OCI_TENANCY_OCID
        self.OCI_OBJECT_STORAGE_BUCKET = os.getenv("OCI_OBJECT_STORAGE_BUCKET", "").strip()
        self.OCI_OBJECT_STORAGE_NAMESPACE = os.getenv("OCI_OBJECT_STORAGE_NAMESPACE", "").strip()
        self.PDF_STORAGE_WARN_GB = float(os.getenv("PDF_STORAGE_WARN_GB", "15"))
        self.PDF_STORAGE_BLOCK_GB = float(os.getenv("PDF_STORAGE_BLOCK_GB", "19"))
        self.PDF_STORAGE_LIMIT_GB = float(os.getenv("PDF_STORAGE_LIMIT_GB", "20"))
        self.PDF_OCI_POLL_INTERVAL_SEC = int(os.getenv("PDF_OCI_POLL_INTERVAL_SEC", "15"))
        if self.PDF_OCI_POLL_INTERVAL_SEC < 3:
            self.PDF_OCI_POLL_INTERVAL_SEC = 15
        self.PDF_DELETE_RETRY_INTERVAL_SEC = int(os.getenv("PDF_DELETE_RETRY_INTERVAL_SEC", "300"))
        if self.PDF_DELETE_RETRY_INTERVAL_SEC < 30:
            self.PDF_DELETE_RETRY_INTERVAL_SEC = 300
        self.PDF_CANONICAL_RETENTION_DAYS = int(os.getenv("PDF_CANONICAL_RETENTION_DAYS", "15"))
        if self.PDF_CANONICAL_RETENTION_DAYS < 0:
            self.PDF_CANONICAL_RETENTION_DAYS = 15
        self.PDF_CANONICAL_CLEANUP_INTERVAL_SEC = int(os.getenv("PDF_CANONICAL_CLEANUP_INTERVAL_SEC", "21600"))
        if self.PDF_CANONICAL_CLEANUP_INTERVAL_SEC < 300:
            self.PDF_CANONICAL_CLEANUP_INTERVAL_SEC = 21600
        self.PDF_V2_ENABLED = os.getenv("PDF_V2_ENABLED", "true").strip().lower() == "true"
        self.PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE = int(os.getenv("PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE", "120"))
        self.PDF_TEXT_NATIVE_TEXT_PAGE_RATIO_MIN = float(os.getenv("PDF_TEXT_NATIVE_TEXT_PAGE_RATIO_MIN", "0.70"))
        self.PDF_TEXT_NATIVE_BLANK_PAGE_RATIO_MAX = float(os.getenv("PDF_TEXT_NATIVE_BLANK_PAGE_RATIO_MAX", "0.20"))
        self.PDF_TEXT_NATIVE_GARBLED_RATIO_MAX = float(os.getenv("PDF_TEXT_NATIVE_GARBLED_RATIO_MAX", "0.12"))
        self.PDF_TEXT_NATIVE_IMAGE_HEAVY_RATIO_MAX = float(os.getenv("PDF_TEXT_NATIVE_IMAGE_HEAVY_RATIO_MAX", "0.40"))
        self.PDF_CLASSIFIER_EARLY_OCR_ENABLED = (
            os.getenv("PDF_CLASSIFIER_EARLY_OCR_ENABLED", "true").strip().lower() == "true"
        )
        self.PDF_CLASSIFIER_SAMPLE_PAGES = int(os.getenv("PDF_CLASSIFIER_SAMPLE_PAGES", "5"))
        if self.PDF_CLASSIFIER_SAMPLE_PAGES < 3:
            self.PDF_CLASSIFIER_SAMPLE_PAGES = 3
        if self.PDF_CLASSIFIER_SAMPLE_PAGES > 9:
            self.PDF_CLASSIFIER_SAMPLE_PAGES = 9
        self.PDF_RETRY_AS_OCR_GARBLED_RATIO = float(os.getenv("PDF_RETRY_AS_OCR_GARBLED_RATIO", "0.18"))
        self.PDF_RETRY_AS_OCR_MIN_CHUNKS = int(os.getenv("PDF_RETRY_AS_OCR_MIN_CHUNKS", "8"))
        self.PDF_OCR_SHARD_TRIGGER_PAGES = int(os.getenv("PDF_OCR_SHARD_TRIGGER_PAGES", "300"))
        self.PDF_OCR_SHARD_SIZE = int(os.getenv("PDF_OCR_SHARD_SIZE", "100"))
        self.PDF_OCR_SHARD_TRIGGER_FILE_MB = int(os.getenv("PDF_OCR_SHARD_TRIGGER_FILE_MB", "25"))
        self.PDF_HEADER_FOOTER_SAMPLE_DEPTH = int(os.getenv("PDF_HEADER_FOOTER_SAMPLE_DEPTH", "2"))
        if self.PDF_HEADER_FOOTER_SAMPLE_DEPTH < 1:
            self.PDF_HEADER_FOOTER_SAMPLE_DEPTH = 2
        if self.PDF_HEADER_FOOTER_SAMPLE_DEPTH > 4:
            self.PDF_HEADER_FOOTER_SAMPLE_DEPTH = 4
        self.PDF_HEADER_FOOTER_MIN_OCCURRENCES = int(os.getenv("PDF_HEADER_FOOTER_MIN_OCCURRENCES", "3"))
        if self.PDF_HEADER_FOOTER_MIN_OCCURRENCES < 2:
            self.PDF_HEADER_FOOTER_MIN_OCCURRENCES = 3
        self.PDF_HEADER_FOOTER_REPEAT_RATIO_MIN = float(
            os.getenv("PDF_HEADER_FOOTER_REPEAT_RATIO_MIN", "0.20")
        )
        if self.PDF_HEADER_FOOTER_REPEAT_RATIO_MIN <= 0.0:
            self.PDF_HEADER_FOOTER_REPEAT_RATIO_MIN = 0.20
        if self.PDF_HEADER_FOOTER_REPEAT_RATIO_MIN > 0.80:
            self.PDF_HEADER_FOOTER_REPEAT_RATIO_MIN = 0.80
        self.PDF_PROCESSING_STALE_SEC = int(os.getenv("PDF_PROCESSING_STALE_SEC", "1800"))
        if self.PDF_PROCESSING_STALE_SEC < 300:
            self.PDF_PROCESSING_STALE_SEC = 1800
        self.PDF_PROCESSING_RECOVERY_LIMIT = int(os.getenv("PDF_PROCESSING_RECOVERY_LIMIT", "50"))
        if self.PDF_PROCESSING_RECOVERY_LIMIT < 1:
            self.PDF_PROCESSING_RECOVERY_LIMIT = 50
        if self.PDF_PROCESSING_RECOVERY_LIMIT > 500:
            self.PDF_PROCESSING_RECOVERY_LIMIT = 500
        self.PDF_OCR_LANGUAGES = os.getenv("PDF_OCR_LANGUAGES", "tr,en").strip() or "tr,en"
        self.PDF_CHUNK_SOFT_TOKEN_TARGET = int(os.getenv("PDF_CHUNK_SOFT_TOKEN_TARGET", "350"))
        self.PDF_CHUNK_HARD_TOKEN_CAP = int(os.getenv("PDF_CHUNK_HARD_TOKEN_CAP", "450"))
        self.PDF_SENTENCE_CHUNKING_ENABLED = (
            os.getenv("PDF_SENTENCE_CHUNKING_ENABLED", "true").strip().lower() == "true"
        )
        self.PDF_CHUNK_OVERLAP_TOKENS = int(os.getenv("PDF_CHUNK_OVERLAP_TOKENS", "20"))
        if self.PDF_CHUNK_OVERLAP_TOKENS < 0:
            self.PDF_CHUNK_OVERLAP_TOKENS = 0
        self.LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "").strip()
        self.LLAMA_PARSE_API_URL = os.getenv(
            "LLAMA_PARSE_API_URL",
            "https://api.cloud.llamaindex.ai/api/parsing/upload",
        ).strip()
        self.LLAMA_PARSE_RESULT_URL_TEMPLATE = os.getenv(
            "LLAMA_PARSE_RESULT_URL_TEMPLATE",
            "https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/json",
        ).strip()
        self.LLAMA_PARSE_TIMEOUT_SEC = int(os.getenv("LLAMA_PARSE_TIMEOUT_SEC", "900"))
        self.LLAMA_PARSE_POLL_INTERVAL_SEC = int(os.getenv("LLAMA_PARSE_POLL_INTERVAL_SEC", "8"))
        self.LLAMA_PARSE_TIER = os.getenv("LLAMA_PARSE_TIER", "agentic").strip() or "agentic"
        self.LLAMA_PARSE_VERSION = os.getenv("LLAMA_PARSE_VERSION", "latest").strip() or "latest"
        self.UNSTRUCTURED_API_URL = os.getenv("UNSTRUCTURED_API_URL", "").strip()
        self.UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY", "").strip()
        
        # Security / Firebase
        self.FIREBASE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.FIREBASE_READY = False
        self._init_firebase()
        # External read-only API (separate from Firebase JWT user auth)
        self.EXTERNAL_API_ENABLED = (
            os.getenv("EXTERNAL_API_ENABLED", "false").strip().lower() == "true"
        )
        self.EXTERNAL_API_KEY_PEPPER = os.getenv("EXTERNAL_API_KEY_PEPPER", "").strip()
        self.EXTERNAL_API_DEFAULT_SCOPES = _parse_csv(
            os.getenv("EXTERNAL_API_DEFAULT_SCOPES", "search:read")
        )
        admin_uid_allowlist_raw = (
            os.getenv("ADMIN_UID_ALLOWLIST", "").strip()
            or os.getenv("FIREBASE_ADMIN_UIDS", "").strip()
        )
        self.ADMIN_UID_ALLOWLIST = {
            uid.strip() for uid in admin_uid_allowlist_raw.split(",") if uid.strip()
        }
        self.EXTERNAL_API_KEY_CACHE_TTL_SEC = int(
            os.getenv("EXTERNAL_API_KEY_CACHE_TTL_SEC", "300")
        )
        if self.EXTERNAL_API_KEY_CACHE_TTL_SEC < 5:
            self.EXTERNAL_API_KEY_CACHE_TTL_SEC = 300
        if self.EXTERNAL_API_KEY_CACHE_TTL_SEC > 3600:
            self.EXTERNAL_API_KEY_CACHE_TTL_SEC = 3600
        self.EXTERNAL_API_KEY_CACHE_MAXSIZE = int(
            os.getenv("EXTERNAL_API_KEY_CACHE_MAXSIZE", "1024")
        )
        if self.EXTERNAL_API_KEY_CACHE_MAXSIZE < 32:
            self.EXTERNAL_API_KEY_CACHE_MAXSIZE = 1024
        if self.EXTERNAL_API_KEY_CACHE_MAXSIZE > 10000:
            self.EXTERNAL_API_KEY_CACHE_MAXSIZE = 10000
        self.EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC = int(
            os.getenv("EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC", "300")
        )
        if self.EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC < 5:
            self.EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC = 300
        if self.EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC > 3600:
            self.EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC = 3600
        self.EXTERNAL_API_MAX_LIMIT = int(os.getenv("EXTERNAL_API_MAX_LIMIT", "12"))
        if self.EXTERNAL_API_MAX_LIMIT < 1:
            self.EXTERNAL_API_MAX_LIMIT = 12
        if self.EXTERNAL_API_MAX_LIMIT > 50:
            self.EXTERNAL_API_MAX_LIMIT = 50
        self.EXTERNAL_API_MAX_SNIPPET_CHARS = int(
            os.getenv("EXTERNAL_API_MAX_SNIPPET_CHARS", "1200")
        )
        if self.EXTERNAL_API_MAX_SNIPPET_CHARS < 200:
            self.EXTERNAL_API_MAX_SNIPPET_CHARS = 1200
        if self.EXTERNAL_API_MAX_SNIPPET_CHARS > 4000:
            self.EXTERNAL_API_MAX_SNIPPET_CHARS = 4000
        self.EXTERNAL_API_MAX_TAGS_PER_RESULT = int(
            os.getenv("EXTERNAL_API_MAX_TAGS_PER_RESULT", "8")
        )
        if self.EXTERNAL_API_MAX_TAGS_PER_RESULT < 0:
            self.EXTERNAL_API_MAX_TAGS_PER_RESULT = 8
        if self.EXTERNAL_API_MAX_TAGS_PER_RESULT > 20:
            self.EXTERNAL_API_MAX_TAGS_PER_RESULT = 20
        
        # AI
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "").strip() or None
        self.BIG_BOOK_API_KEY = os.getenv("BIG_BOOK_API_KEY", "").strip() or None
        self.BIG_BOOK_API_DAILY_LIMIT = int(os.getenv("BIG_BOOK_API_DAILY_LIMIT", "50"))
        if self.BIG_BOOK_API_DAILY_LIMIT < 1:
            self.BIG_BOOK_API_DAILY_LIMIT = 50
        self.LLM_MODEL_LITE = os.getenv("LLM_MODEL_LITE", "gemini-2.5-flash-lite")
        # Economic policy: keep Gemini on a single cost-efficient model by default.
        self.LLM_MODEL_FLASH = os.getenv("LLM_MODEL_FLASH", "gemini-2.5-flash-lite")
        self.LLM_MODEL_PRO = os.getenv("LLM_MODEL_PRO", "gemini-2.5-flash-lite")
        self.EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "gemini-embedding-2-preview")
        self.LLM_PRO_FALLBACK_ENABLED = os.getenv("LLM_PRO_FALLBACK_ENABLED", "false").strip().lower() == "true"
        self.LLM_PRO_FALLBACK_MAX_PER_REQUEST = int(os.getenv("LLM_PRO_FALLBACK_MAX_PER_REQUEST", "1"))
        if self.LLM_PRO_FALLBACK_MAX_PER_REQUEST < 0:
            self.LLM_PRO_FALLBACK_MAX_PER_REQUEST = 0
        self.NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
        self.NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com").strip().rstrip("/")
        self.NVIDIA_DISABLE_TIMEOUT = (
            os.getenv("NVIDIA_DISABLE_TIMEOUT", "false").strip().lower() == "true"
        )
        self.LLM_EXPLORER_QWEN_PILOT_ENABLED = (
            os.getenv("LLM_EXPLORER_QWEN_PILOT_ENABLED", "true").strip().lower() == "true"
        )
        self.LLM_EXPLORER_PRIMARY_PROVIDER = (
            os.getenv("LLM_EXPLORER_PRIMARY_PROVIDER", "qwen").strip().lower() or "qwen"
        )
        self.LLM_EXPLORER_PRIMARY_MODEL = (
            os.getenv("LLM_EXPLORER_PRIMARY_MODEL", "qwen/qwen3.5-122b-a10b").strip()
            or "qwen/qwen3.5-122b-a10b"
        )
        self.LLM_TRANSLATION_PROVIDER = (
            os.getenv("LLM_TRANSLATION_PROVIDER", "nvidia").strip().lower() or "nvidia"
        )
        self.LLM_TRANSLATION_MODEL = (
            os.getenv("LLM_TRANSLATION_MODEL", "moonshotai/kimi-k2-instruct").strip()
            or "moonshotai/kimi-k2-instruct"
        )
        self.LLM_EXPLORER_PARALLEL_NVIDIA_ENABLED = (
            os.getenv("LLM_EXPLORER_PARALLEL_NVIDIA_ENABLED", "false").strip().lower() == "true"
        )
        self.LLM_EXPLORER_PARALLEL_NVIDIA_MODEL = (
            os.getenv("LLM_EXPLORER_PARALLEL_NVIDIA_MODEL", "kimi-k2-thinking").strip()
            or "kimi-k2-thinking"
        )
        self.LLM_EXPLORER_FALLBACK_PROVIDER = (
            os.getenv("LLM_EXPLORER_FALLBACK_PROVIDER", "gemini").strip().lower() or "gemini"
        )
        self.LLM_EXPLORER_RPM_CAP = int(os.getenv("LLM_EXPLORER_RPM_CAP", "35"))
        if self.LLM_EXPLORER_RPM_CAP < 1:
            self.LLM_EXPLORER_RPM_CAP = 35
        self.LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST = int(
            os.getenv("LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST", "1")
        )
        if self.LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST < 0:
            self.LLM_EXPLORER_SECONDARY_MAX_PER_REQUEST = 0

        # Ingestion data-cleaner guardrails (token spike prevention)
        self.INGESTION_DATA_CLEANER_AI_ENABLED = (
            os.getenv("INGESTION_DATA_CLEANER_AI_ENABLED", "true").strip().lower() == "true"
        )
        self.INGESTION_DATA_CLEANER_NOISE_THRESHOLD = int(
            os.getenv("INGESTION_DATA_CLEANER_NOISE_THRESHOLD", "4")
        )
        if self.INGESTION_DATA_CLEANER_NOISE_THRESHOLD < 0:
            self.INGESTION_DATA_CLEANER_NOISE_THRESHOLD = 0
        self.INGESTION_DATA_CLEANER_MAX_CALLS_PER_BOOK = int(
            os.getenv("INGESTION_DATA_CLEANER_MAX_CALLS_PER_BOOK", "40")
        )
        if self.INGESTION_DATA_CLEANER_MAX_CALLS_PER_BOOK < 0:
            self.INGESTION_DATA_CLEANER_MAX_CALLS_PER_BOOK = 0
        self.INGESTION_DATA_CLEANER_MIN_CHARS_FOR_AI = int(
            os.getenv("INGESTION_DATA_CLEANER_MIN_CHARS_FOR_AI", "180")
        )
        if self.INGESTION_DATA_CLEANER_MIN_CHARS_FOR_AI < 50:
            self.INGESTION_DATA_CLEANER_MIN_CHARS_FOR_AI = 50
        self.INGESTION_DATA_CLEANER_CACHE_SIZE = int(
            os.getenv("INGESTION_DATA_CLEANER_CACHE_SIZE", "256")
        )
        if self.INGESTION_DATA_CLEANER_CACHE_SIZE < 0:
            self.INGESTION_DATA_CLEANER_CACHE_SIZE = 0

        # Backward compatibility: ANSWER_MODEL_NAME still supported but deprecated.
        answer_model_env = os.getenv("ANSWER_MODEL_NAME")
        if answer_model_env:
            self.ANSWER_MODEL_NAME = answer_model_env.strip()
            logger.warning(
                "ANSWER_MODEL_NAME is deprecated. Prefer LLM_MODEL_FLASH/LLM_MODEL_LITE/LLM_MODEL_PRO."
            )
        else:
            self.ANSWER_MODEL_NAME = self.LLM_MODEL_FLASH
        
        # Validation
        if not self.DB_PASSWORD:
            raise ValueError("CRITICAL: DB_PASSWORD is missing from environment variables.")
        if not self.GEMINI_API_KEY:
            raise ValueError("CRITICAL: GEMINI_API_KEY is missing from environment variables.")
        if self.EXTERNAL_API_ENABLED and not self.EXTERNAL_API_KEY_PEPPER:
            raise ValueError(
                "CRITICAL: EXTERNAL_API_KEY_PEPPER is required when EXTERNAL_API_ENABLED=true."
            )

        # CORS
        # Default to localhost if not set, but allow overriding via env var
        # Format: "http://localhost:5173,http://localhost:3000,https://myapp.com"
        allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174,http://localhost:3000")
        self.ALLOWED_ORIGINS: List[str] = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]
        
        # Cache Configuration
        self.REDIS_URL = os.getenv("REDIS_URL", None)  # e.g., "redis://localhost:6379/0"
        self.CACHE_L1_MAXSIZE = int(os.getenv("CACHE_L1_MAXSIZE", "1000"))
        self.CACHE_L1_TTL = int(os.getenv("CACHE_L1_TTL", "600"))  # 10 minutes
        self.CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        
        # Retrieval Fusion Mode
        # - concat: strict bucket concatenation (exact > lemma > semantic)
        # - rrf: reciprocal rank fusion over bucket rankings
        self.RETRIEVAL_FUSION_MODE = os.getenv("RETRIEVAL_FUSION_MODE", "rrf").strip().lower()
        if self.RETRIEVAL_FUSION_MODE not in {"concat", "rrf"}:
            logger.warning(
                f"Invalid RETRIEVAL_FUSION_MODE='{self.RETRIEVAL_FUSION_MODE}', falling back to 'rrf'"
            )
            self.RETRIEVAL_FUSION_MODE = "rrf"
        self.SEARCH_DEFAULT_RESULT_MIX_POLICY = (
            os.getenv("SEARCH_DEFAULT_RESULT_MIX_POLICY", "auto").strip().lower()
        )
        if self.SEARCH_DEFAULT_RESULT_MIX_POLICY not in {"auto", "none", "lexical_then_semantic_tail"}:
            logger.warning(
                "Invalid SEARCH_DEFAULT_RESULT_MIX_POLICY='%s', falling back to 'auto'",
                self.SEARCH_DEFAULT_RESULT_MIX_POLICY,
            )
            self.SEARCH_DEFAULT_RESULT_MIX_POLICY = "auto"

        # Router mode for strategy selection
        # - static: run all enabled strategies
        # - rule_based: lightweight semantic router chooses strategy set per query
        self.SEARCH_ROUTER_MODE = os.getenv("SEARCH_ROUTER_MODE", "rule_based").strip().lower()
        if self.SEARCH_ROUTER_MODE not in {"static", "rule_based"}:
            logger.warning(
                f"Invalid SEARCH_ROUTER_MODE='{self.SEARCH_ROUTER_MODE}', falling back to 'rule_based'"
            )
            self.SEARCH_ROUTER_MODE = "rule_based"

        # Search mode routing and latency/noise controls
        self.SEARCH_MODE_ROUTING_ENABLED = os.getenv("SEARCH_MODE_ROUTING_ENABLED", "true").strip().lower() == "true"
        self.SEARCH_DEFAULT_MODE = os.getenv("SEARCH_DEFAULT_MODE", "balanced").strip().lower()
        if self.SEARCH_DEFAULT_MODE not in {"fast_exact", "balanced", "semantic_focus"}:
            logger.warning(
                f"Invalid SEARCH_DEFAULT_MODE='{self.SEARCH_DEFAULT_MODE}', falling back to 'balanced'"
            )
            self.SEARCH_DEFAULT_MODE = "balanced"
        self.SEARCH_GRAPH_TIMEOUT_MS = int(os.getenv("SEARCH_GRAPH_TIMEOUT_MS", "120"))
        if self.SEARCH_GRAPH_TIMEOUT_MS <= 0:
            self.SEARCH_GRAPH_TIMEOUT_MS = 120
        self.SEARCH_GRAPH_BRIDGE_TIMEOUT_MS = int(os.getenv("SEARCH_GRAPH_BRIDGE_TIMEOUT_MS", "650"))
        if self.SEARCH_GRAPH_BRIDGE_TIMEOUT_MS <= 0:
            self.SEARCH_GRAPH_BRIDGE_TIMEOUT_MS = 650
        self.SEARCH_GRAPH_BRIDGE_EXPLORER_ALWAYS_ATTEMPT = (
            os.getenv("SEARCH_GRAPH_BRIDGE_EXPLORER_ALWAYS_ATTEMPT", "false").strip().lower() == "true"
        )
        self.SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS = int(
            os.getenv("SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS", "950")
        )
        if self.SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS <= 0:
            self.SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS = 950
        self.SEARCH_GRAPH_DIRECT_SKIP = os.getenv("SEARCH_GRAPH_DIRECT_SKIP", "true").strip().lower() == "true"
        self.SEARCH_NOISE_GUARD_ENABLED = os.getenv("SEARCH_NOISE_GUARD_ENABLED", "true").strip().lower() == "true"
        self.SEARCH_SMART_SEMANTIC_TAIL_CAP = int(os.getenv("SEARCH_SMART_SEMANTIC_TAIL_CAP", "6"))
        if self.SEARCH_SMART_SEMANTIC_TAIL_CAP <= 0:
            self.SEARCH_SMART_SEMANTIC_TAIL_CAP = 6
        self.SEARCH_TYPO_RESCUE_ENABLED = os.getenv("SEARCH_TYPO_RESCUE_ENABLED", "true").strip().lower() == "true"
        self.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = os.getenv("SEARCH_LEMMA_SEED_FALLBACK_ENABLED", "true").strip().lower() == "true"
        self.SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED = (
            os.getenv("SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED", "true").strip().lower() == "true"
        )
        self.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = int(
            os.getenv("SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS", "2")
        )
        if self.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS < 0:
            self.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0

        # Phase-1 retrieval/rerank controls (fail-open, canary-safe).
        # Default-off to guarantee no latency regression on rollout.
        self.SEARCH_RERANK_ENABLED = (
            os.getenv("SEARCH_RERANK_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_RERANK_SHADOW_ENABLED = (
            os.getenv("SEARCH_RERANK_SHADOW_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_RERANK_PROVIDER = (
            os.getenv("SEARCH_RERANK_PROVIDER", "fast_heuristic_v1").strip().lower()
            or "fast_heuristic_v1"
        )
        self.SEARCH_RERANK_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("SEARCH_RERANK_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.SEARCH_RERANK_MIN_CANDIDATES = int(os.getenv("SEARCH_RERANK_MIN_CANDIDATES", "8"))
        if self.SEARCH_RERANK_MIN_CANDIDATES < 2:
            self.SEARCH_RERANK_MIN_CANDIDATES = 8
        self.SEARCH_RERANK_MAX_CANDIDATES = int(os.getenv("SEARCH_RERANK_MAX_CANDIDATES", "80"))
        if self.SEARCH_RERANK_MAX_CANDIDATES < self.SEARCH_RERANK_MIN_CANDIDATES:
            self.SEARCH_RERANK_MAX_CANDIDATES = max(24, self.SEARCH_RERANK_MIN_CANDIDATES)
        if self.SEARCH_RERANK_MAX_CANDIDATES > 300:
            self.SEARCH_RERANK_MAX_CANDIDATES = 300
        self.SEARCH_RERANK_TOP_N = int(os.getenv("SEARCH_RERANK_TOP_N", "24"))
        if self.SEARCH_RERANK_TOP_N < 4:
            self.SEARCH_RERANK_TOP_N = 24
        if self.SEARCH_RERANK_TOP_N > self.SEARCH_RERANK_MAX_CANDIDATES:
            self.SEARCH_RERANK_TOP_N = self.SEARCH_RERANK_MAX_CANDIDATES

        # Phase-2 lexical booster (BM25Plus): default-off and canary-safe.
        self.SEARCH_BM25PLUS_ENABLED = (
            os.getenv("SEARCH_BM25PLUS_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_BM25PLUS_SHADOW_ENABLED = (
            os.getenv("SEARCH_BM25PLUS_SHADOW_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_BM25PLUS_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("SEARCH_BM25PLUS_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.SEARCH_BM25PLUS_MIN_CANDIDATES = int(os.getenv("SEARCH_BM25PLUS_MIN_CANDIDATES", "8"))
        if self.SEARCH_BM25PLUS_MIN_CANDIDATES < 2:
            self.SEARCH_BM25PLUS_MIN_CANDIDATES = 8
        self.SEARCH_BM25PLUS_MAX_CANDIDATES = int(os.getenv("SEARCH_BM25PLUS_MAX_CANDIDATES", "120"))
        if self.SEARCH_BM25PLUS_MAX_CANDIDATES < self.SEARCH_BM25PLUS_MIN_CANDIDATES:
            self.SEARCH_BM25PLUS_MAX_CANDIDATES = max(24, self.SEARCH_BM25PLUS_MIN_CANDIDATES)
        if self.SEARCH_BM25PLUS_MAX_CANDIDATES > 300:
            self.SEARCH_BM25PLUS_MAX_CANDIDATES = 300
        self.SEARCH_BM25PLUS_BLEND_WEIGHT = float(os.getenv("SEARCH_BM25PLUS_BLEND_WEIGHT", "0.22"))
        if self.SEARCH_BM25PLUS_BLEND_WEIGHT < 0.0:
            self.SEARCH_BM25PLUS_BLEND_WEIGHT = 0.22
        if self.SEARCH_BM25PLUS_BLEND_WEIGHT > 1.0:
            self.SEARCH_BM25PLUS_BLEND_WEIGHT = 1.0

        # Phase-2 wide candidate pool controls (default-off, canary-safe).
        self.SEARCH_WIDE_POOL_ENABLED = (
            os.getenv("SEARCH_WIDE_POOL_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_WIDE_POOL_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("SEARCH_WIDE_POOL_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.SEARCH_WIDE_POOL_LIMIT_DIRECT = int(os.getenv("SEARCH_WIDE_POOL_LIMIT_DIRECT", "900"))
        if self.SEARCH_WIDE_POOL_LIMIT_DIRECT < 200:
            self.SEARCH_WIDE_POOL_LIMIT_DIRECT = 900
        if self.SEARCH_WIDE_POOL_LIMIT_DIRECT > 2500:
            self.SEARCH_WIDE_POOL_LIMIT_DIRECT = 2500
        self.SEARCH_WIDE_POOL_LIMIT_DEFAULT = int(os.getenv("SEARCH_WIDE_POOL_LIMIT_DEFAULT", "480"))
        if self.SEARCH_WIDE_POOL_LIMIT_DEFAULT < 150:
            self.SEARCH_WIDE_POOL_LIMIT_DEFAULT = 480
        if self.SEARCH_WIDE_POOL_LIMIT_DEFAULT > 2000:
            self.SEARCH_WIDE_POOL_LIMIT_DEFAULT = 2000
        self.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT = int(
            os.getenv("SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT", "72")
        )
        if self.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT < 20:
            self.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT = 72
        if self.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT > 180:
            self.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT = 180

        # Phase-3 MMR diversity policy (default-off, canary-safe).
        self.SEARCH_MMR_ENABLED = (
            os.getenv("SEARCH_MMR_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_MMR_SHADOW_ENABLED = (
            os.getenv("SEARCH_MMR_SHADOW_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_MMR_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("SEARCH_MMR_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.SEARCH_MMR_MIN_CANDIDATES = int(os.getenv("SEARCH_MMR_MIN_CANDIDATES", "8"))
        if self.SEARCH_MMR_MIN_CANDIDATES < 2:
            self.SEARCH_MMR_MIN_CANDIDATES = 8
        self.SEARCH_MMR_MAX_CANDIDATES = int(os.getenv("SEARCH_MMR_MAX_CANDIDATES", "100"))
        if self.SEARCH_MMR_MAX_CANDIDATES < self.SEARCH_MMR_MIN_CANDIDATES:
            self.SEARCH_MMR_MAX_CANDIDATES = max(24, self.SEARCH_MMR_MIN_CANDIDATES)
        if self.SEARCH_MMR_MAX_CANDIDATES > 300:
            self.SEARCH_MMR_MAX_CANDIDATES = 300
        self.SEARCH_MMR_TOP_N = int(os.getenv("SEARCH_MMR_TOP_N", "24"))
        if self.SEARCH_MMR_TOP_N < 4:
            self.SEARCH_MMR_TOP_N = 24
        if self.SEARCH_MMR_TOP_N > self.SEARCH_MMR_MAX_CANDIDATES:
            self.SEARCH_MMR_TOP_N = self.SEARCH_MMR_MAX_CANDIDATES
        self.SEARCH_MMR_LAMBDA = float(os.getenv("SEARCH_MMR_LAMBDA", "0.62"))
        if self.SEARCH_MMR_LAMBDA < 0.0:
            self.SEARCH_MMR_LAMBDA = 0.62
        if self.SEARCH_MMR_LAMBDA > 1.0:
            self.SEARCH_MMR_LAMBDA = 1.0

        # Chat scope policy (Phase: Chat-only rollout)
        scope_policy_default = "true" if self.ENVIRONMENT == "development" else "false"
        self.SEARCH_SCOPE_POLICY_ENABLED = (
            os.getenv("SEARCH_SCOPE_POLICY_ENABLED", scope_policy_default).strip().lower() == "true"
        )
        self.SEARCH_SCOPE_POLICY_CHAT_MODES = _parse_csv_upper(
            os.getenv("SEARCH_SCOPE_POLICY_CHAT_MODES", "STANDARD,EXPLORER")
        )
        if not self.SEARCH_SCOPE_POLICY_CHAT_MODES:
            self.SEARCH_SCOPE_POLICY_CHAT_MODES = ["STANDARD", "EXPLORER"]
        self.SEARCH_SCOPE_POLICY_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("SEARCH_SCOPE_POLICY_CANARY_UIDS", "").split(",") if uid.strip()
        }

        # Personal note wiki-link cleanup (temporary rollout toggle).
        self.PERSONAL_NOTE_WIKI_TOKEN_CLEANUP_ENABLED = (
            os.getenv("PERSONAL_NOTE_WIKI_TOKEN_CLEANUP_ENABLED", "false").strip().lower() == "true"
        )

        # Media library rollout controls (films & series).
        self.MEDIA_LIBRARY_ENABLED = (
            os.getenv("MEDIA_LIBRARY_ENABLED", "true").strip().lower() == "true"
        )
        self.MEDIA_TMDB_SYNC_ENABLED = (
            os.getenv("MEDIA_TMDB_SYNC_ENABLED", "true").strip().lower() == "true"
        )
        self.TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
        self.TMDB_BASE_URL = os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3").strip().rstrip("/")
        self.TMDB_TIMEOUT_SEC = float(os.getenv("TMDB_TIMEOUT_SEC", "8"))
        if self.TMDB_TIMEOUT_SEC <= 0:
            self.TMDB_TIMEOUT_SEC = 8.0

        # Compare policy rollout controls (non-breaking, canary-first).
        self.SEARCH_COMPARE_POLICY_ENABLED = (
            os.getenv("SEARCH_COMPARE_POLICY_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_COMPARE_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("SEARCH_COMPARE_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.SEARCH_COMPARE_TARGET_MAX = int(os.getenv("SEARCH_COMPARE_TARGET_MAX", "8"))
        if self.SEARCH_COMPARE_TARGET_MAX < 2:
            self.SEARCH_COMPARE_TARGET_MAX = 8
        self.SEARCH_COMPARE_PRIMARY_PER_BOOK = int(os.getenv("SEARCH_COMPARE_PRIMARY_PER_BOOK", "6"))
        if self.SEARCH_COMPARE_PRIMARY_PER_BOOK < 1:
            self.SEARCH_COMPARE_PRIMARY_PER_BOOK = 6
        self.SEARCH_COMPARE_SECONDARY_PER_BOOK = int(os.getenv("SEARCH_COMPARE_SECONDARY_PER_BOOK", "2"))
        if self.SEARCH_COMPARE_SECONDARY_PER_BOOK < 0:
            self.SEARCH_COMPARE_SECONDARY_PER_BOOK = 2
        self.SEARCH_COMPARE_GLOBAL_MAX = int(os.getenv("SEARCH_COMPARE_GLOBAL_MAX", "48"))
        if self.SEARCH_COMPARE_GLOBAL_MAX < 8:
            self.SEARCH_COMPARE_GLOBAL_MAX = 48
        self.SEARCH_COMPARE_TIMEOUT_MS = int(os.getenv("SEARCH_COMPARE_TIMEOUT_MS", "2500"))
        if self.SEARCH_COMPARE_TIMEOUT_MS < 100:
            self.SEARCH_COMPARE_TIMEOUT_MS = 2500
        self.SEARCH_COMPARE_SECONDARY_MAX_RATIO = float(
            os.getenv("SEARCH_COMPARE_SECONDARY_MAX_RATIO", "0.25")
        )
        if self.SEARCH_COMPARE_SECONDARY_MAX_RATIO <= 0.0:
            self.SEARCH_COMPARE_SECONDARY_MAX_RATIO = 0.25
        if self.SEARCH_COMPARE_SECONDARY_MAX_RATIO > 0.9:
            self.SEARCH_COMPARE_SECONDARY_MAX_RATIO = 0.9
        self.SEARCH_COMPARE_SECONDARY_WEIGHT = float(
            os.getenv("SEARCH_COMPARE_SECONDARY_WEIGHT", "0.45")
        )
        if self.SEARCH_COMPARE_SECONDARY_WEIGHT <= 0.0:
            self.SEARCH_COMPARE_SECONDARY_WEIGHT = 0.45
        if self.SEARCH_COMPARE_SECONDARY_WEIGHT > 1.0:
            self.SEARCH_COMPARE_SECONDARY_WEIGHT = 1.0

        # Highlight-first -> PDF augment controls
        self.SEARCH_HIGHLIGHT_AUGMENT_ENABLED = (
            os.getenv("SEARCH_HIGHLIGHT_AUGMENT_ENABLED", "true").strip().lower() == "true"
        )
        self.SEARCH_HIGHLIGHT_AUGMENT_MAX_BOOKS = int(
            os.getenv("SEARCH_HIGHLIGHT_AUGMENT_MAX_BOOKS", "2")
        )
        if self.SEARCH_HIGHLIGHT_AUGMENT_MAX_BOOKS < 1:
            self.SEARCH_HIGHLIGHT_AUGMENT_MAX_BOOKS = 2
        self.SEARCH_HIGHLIGHT_AUGMENT_CHUNKS_PER_BOOK = int(
            os.getenv("SEARCH_HIGHLIGHT_AUGMENT_CHUNKS_PER_BOOK", "1")
        )
        if self.SEARCH_HIGHLIGHT_AUGMENT_CHUNKS_PER_BOOK < 1:
            self.SEARCH_HIGHLIGHT_AUGMENT_CHUNKS_PER_BOOK = 1
        self.SEARCH_HIGHLIGHT_AUGMENT_TOTAL_MAX = int(
            os.getenv("SEARCH_HIGHLIGHT_AUGMENT_TOTAL_MAX", "2")
        )
        if self.SEARCH_HIGHLIGHT_AUGMENT_TOTAL_MAX < 1:
            self.SEARCH_HIGHLIGHT_AUGMENT_TOTAL_MAX = 2

        # Stage-2 controlled expansion controls
        self.SEARCH_STAGE2_ENABLED = os.getenv("SEARCH_STAGE2_ENABLED", "true").strip().lower() == "true"
        self.SEARCH_STAGE2_MAX_BOOKS = int(os.getenv("SEARCH_STAGE2_MAX_BOOKS", "4"))
        if self.SEARCH_STAGE2_MAX_BOOKS < 1:
            self.SEARCH_STAGE2_MAX_BOOKS = 4
        self.SEARCH_STAGE2_PER_BOOK_LIMIT = int(os.getenv("SEARCH_STAGE2_PER_BOOK_LIMIT", "2"))
        if self.SEARCH_STAGE2_PER_BOOK_LIMIT < 1:
            self.SEARCH_STAGE2_PER_BOOK_LIMIT = 2
        self.SEARCH_STAGE2_MIN_CHUNKS = int(os.getenv("SEARCH_STAGE2_MIN_CHUNKS", "8"))
        if self.SEARCH_STAGE2_MIN_CHUNKS < 1:
            self.SEARCH_STAGE2_MIN_CHUNKS = 8
        self.SEARCH_STAGE2_MIN_CONFIDENCE = float(os.getenv("SEARCH_STAGE2_MIN_CONFIDENCE", "2.8"))
        if self.SEARCH_STAGE2_MIN_CONFIDENCE < 0.0:
            self.SEARCH_STAGE2_MIN_CONFIDENCE = 2.8
        self.SEARCH_STAGE2_MIN_SOURCE_DIVERSITY = int(
            os.getenv("SEARCH_STAGE2_MIN_SOURCE_DIVERSITY", "2")
        )
        if self.SEARCH_STAGE2_MIN_SOURCE_DIVERSITY < 1:
            self.SEARCH_STAGE2_MIN_SOURCE_DIVERSITY = 2
        self.SEARCH_STAGE2_SCORE_DECAY = float(os.getenv("SEARCH_STAGE2_SCORE_DECAY", "0.85"))
        if self.SEARCH_STAGE2_SCORE_DECAY <= 0.0:
            self.SEARCH_STAGE2_SCORE_DECAY = 0.85

        # Source scoring policy controls
        self.SEARCH_SCOPE_HIGHLIGHT_PRIORITY_BONUS = float(
            os.getenv("SEARCH_SCOPE_HIGHLIGHT_PRIORITY_BONUS", "0.8")
        )
        self.SEARCH_SCOPE_INSIGHT_PRIORITY_BONUS = float(
            os.getenv("SEARCH_SCOPE_INSIGHT_PRIORITY_BONUS", "0.5")
        )
        self.SEARCH_SCOPE_NOTES_PRIORITY_BONUS = float(
            os.getenv("SEARCH_SCOPE_NOTES_PRIORITY_BONUS", "0.2")
        )

        # Layer-3 Performance Guards
        # Default OFF to preserve legacy Layer-3 answer quality.
        self.L3_PERF_CONTEXT_BUDGET_ENABLED = (
            os.getenv("L3_PERF_CONTEXT_BUDGET_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PERF_OUTPUT_BUDGET_ENABLED = (
            os.getenv("L3_PERF_OUTPUT_BUDGET_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PERF_REWRITE_GUARD_ENABLED = (
            os.getenv("L3_PERF_REWRITE_GUARD_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PERF_SUPPLEMENTARY_GATE_ENABLED = (
            os.getenv("L3_PERF_SUPPLEMENTARY_GATE_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PERF_EXPANSION_TAIL_FIX_ENABLED = (
            os.getenv("L3_PERF_EXPANSION_TAIL_FIX_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PERF_MAX_OUTPUT_TOKENS_STANDARD = int(
            os.getenv("L3_PERF_MAX_OUTPUT_TOKENS_STANDARD", "1600")
        )
        if self.L3_PERF_MAX_OUTPUT_TOKENS_STANDARD < 128:
            self.L3_PERF_MAX_OUTPUT_TOKENS_STANDARD = 1600
        self.L3_PERF_CONTEXT_TOPK_STANDARD = int(
            os.getenv("L3_PERF_CONTEXT_TOPK_STANDARD", "12")
        )
        if self.L3_PERF_CONTEXT_TOPK_STANDARD < 1:
            self.L3_PERF_CONTEXT_TOPK_STANDARD = 12
        self.L3_PERF_CONTEXT_CHARS_STANDARD = int(
            os.getenv("L3_PERF_CONTEXT_CHARS_STANDARD", "700")
        )
        if self.L3_PERF_CONTEXT_CHARS_STANDARD < 120:
            self.L3_PERF_CONTEXT_CHARS_STANDARD = 700
        # Layer-3 Phase-4 quality controls (default-off, canary-safe).
        self.L3_PHASE4_STEPBACK_ENABLED = (
            os.getenv("L3_PHASE4_STEPBACK_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PHASE4_STEPBACK_SHADOW_ENABLED = (
            os.getenv("L3_PHASE4_STEPBACK_SHADOW_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PHASE4_STEPBACK_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("L3_PHASE4_STEPBACK_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.L3_PHASE4_STEPBACK_LIMIT = int(os.getenv("L3_PHASE4_STEPBACK_LIMIT", "10"))
        if self.L3_PHASE4_STEPBACK_LIMIT < 2:
            self.L3_PHASE4_STEPBACK_LIMIT = 10
        if self.L3_PHASE4_STEPBACK_LIMIT > 40:
            self.L3_PHASE4_STEPBACK_LIMIT = 40
        self.L3_PHASE4_STEPBACK_TIMEOUT_MS = int(os.getenv("L3_PHASE4_STEPBACK_TIMEOUT_MS", "220"))
        if self.L3_PHASE4_STEPBACK_TIMEOUT_MS < 50:
            self.L3_PHASE4_STEPBACK_TIMEOUT_MS = 220
        self.L3_PHASE4_STEPBACK_MIN_QUERY_TOKENS = int(
            os.getenv("L3_PHASE4_STEPBACK_MIN_QUERY_TOKENS", "4")
        )
        if self.L3_PHASE4_STEPBACK_MIN_QUERY_TOKENS < 2:
            self.L3_PHASE4_STEPBACK_MIN_QUERY_TOKENS = 4

        self.L3_PHASE4_PARENT_CONTEXT_ENABLED = (
            os.getenv("L3_PHASE4_PARENT_CONTEXT_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PHASE4_PARENT_CONTEXT_SHADOW_ENABLED = (
            os.getenv("L3_PHASE4_PARENT_CONTEXT_SHADOW_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PHASE4_PARENT_CONTEXT_CANARY_UIDS = {
            uid.strip() for uid in os.getenv("L3_PHASE4_PARENT_CONTEXT_CANARY_UIDS", "").split(",") if uid.strip()
        }
        self.L3_PHASE4_PARENT_SEED_TOPK = int(os.getenv("L3_PHASE4_PARENT_SEED_TOPK", "3"))
        if self.L3_PHASE4_PARENT_SEED_TOPK < 1:
            self.L3_PHASE4_PARENT_SEED_TOPK = 3
        if self.L3_PHASE4_PARENT_SEED_TOPK > 8:
            self.L3_PHASE4_PARENT_SEED_TOPK = 8
        self.L3_PHASE4_PARENT_NEIGHBOR_WINDOW = int(
            os.getenv("L3_PHASE4_PARENT_NEIGHBOR_WINDOW", "1")
        )
        if self.L3_PHASE4_PARENT_NEIGHBOR_WINDOW < 1:
            self.L3_PHASE4_PARENT_NEIGHBOR_WINDOW = 1
        if self.L3_PHASE4_PARENT_NEIGHBOR_WINDOW > 3:
            self.L3_PHASE4_PARENT_NEIGHBOR_WINDOW = 3
        self.L3_PHASE4_PARENT_NEIGHBOR_LIMIT = int(
            os.getenv("L3_PHASE4_PARENT_NEIGHBOR_LIMIT", "2")
        )
        if self.L3_PHASE4_PARENT_NEIGHBOR_LIMIT < 1:
            self.L3_PHASE4_PARENT_NEIGHBOR_LIMIT = 2
        if self.L3_PHASE4_PARENT_NEIGHBOR_LIMIT > 8:
            self.L3_PHASE4_PARENT_NEIGHBOR_LIMIT = 8
        self.L3_PHASE4_PARENT_TIMEOUT_MS = int(os.getenv("L3_PHASE4_PARENT_TIMEOUT_MS", "260"))
        if self.L3_PHASE4_PARENT_TIMEOUT_MS < 50:
            self.L3_PHASE4_PARENT_TIMEOUT_MS = 260
        self.L3_PHASE4_PARENT_SCORE_DECAY = float(
            os.getenv("L3_PHASE4_PARENT_SCORE_DECAY", "0.88")
        )
        if self.L3_PHASE4_PARENT_SCORE_DECAY <= 0.0:
            self.L3_PHASE4_PARENT_SCORE_DECAY = 0.88
        if self.L3_PHASE4_PARENT_SCORE_DECAY > 1.0:
            self.L3_PHASE4_PARENT_SCORE_DECAY = 1.0

        self.L3_PHASE4_DUP_SUPPRESS_ENABLED = (
            os.getenv("L3_PHASE4_DUP_SUPPRESS_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_PHASE4_DUP_SUPPRESS_THRESHOLD = float(
            os.getenv("L3_PHASE4_DUP_SUPPRESS_THRESHOLD", "0.92")
        )
        if self.L3_PHASE4_DUP_SUPPRESS_THRESHOLD <= 0.0:
            self.L3_PHASE4_DUP_SUPPRESS_THRESHOLD = 0.92
        if self.L3_PHASE4_DUP_SUPPRESS_THRESHOLD > 1.0:
            self.L3_PHASE4_DUP_SUPPRESS_THRESHOLD = 1.0
        self.L3_PHASE4_DUP_SUPPRESS_COMPARE_WINDOW = int(
            os.getenv("L3_PHASE4_DUP_SUPPRESS_COMPARE_WINDOW", "8")
        )
        if self.L3_PHASE4_DUP_SUPPRESS_COMPARE_WINDOW < 1:
            self.L3_PHASE4_DUP_SUPPRESS_COMPARE_WINDOW = 8
        if self.L3_PHASE4_DUP_SUPPRESS_COMPARE_WINDOW > 20:
            self.L3_PHASE4_DUP_SUPPRESS_COMPARE_WINDOW = 20
        self.L3_PHASE4_LONG_CONTEXT_REORDER_ENABLED = (
            os.getenv("L3_PHASE4_LONG_CONTEXT_REORDER_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_QUOTE_DYNAMIC_COUNT_ENABLED = (
            os.getenv("L3_QUOTE_DYNAMIC_COUNT_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_QUOTE_DYNAMIC_MIN = int(os.getenv("L3_QUOTE_DYNAMIC_MIN", "2"))
        self.L3_QUOTE_DYNAMIC_MAX = int(os.getenv("L3_QUOTE_DYNAMIC_MAX", "5"))
        if self.L3_QUOTE_DYNAMIC_MIN < 1:
            self.L3_QUOTE_DYNAMIC_MIN = 2
        if self.L3_QUOTE_DYNAMIC_MAX < self.L3_QUOTE_DYNAMIC_MIN:
            self.L3_QUOTE_DYNAMIC_MAX = self.L3_QUOTE_DYNAMIC_MIN
        self.L3_JUDGE_DIVERSITY_AUDIT_ENABLED = (
            os.getenv("L3_JUDGE_DIVERSITY_AUDIT_ENABLED", "false").strip().lower() == "true"
        )
        self.L3_JUDGE_DIVERSITY_THRESHOLD = int(os.getenv("L3_JUDGE_DIVERSITY_THRESHOLD", "2"))
        if self.L3_JUDGE_DIVERSITY_THRESHOLD < 1:
            self.L3_JUDGE_DIVERSITY_THRESHOLD = 2
        self.SEARCH_LOG_DIAGNOSTICS_PERSIST_ENABLED = (
            os.getenv("SEARCH_LOG_DIAGNOSTICS_PERSIST_ENABLED", "false").strip().lower() == "true"
        )
        self.SEARCH_LOG_RETENTION_DAYS = int(os.getenv("SEARCH_LOG_RETENTION_DAYS", "90"))
        if self.SEARCH_LOG_RETENTION_DAYS < 1:
            self.SEARCH_LOG_RETENTION_DAYS = 90
        self.SEARCH_LOG_RETENTION_CLEANUP_ENABLED = (
            os.getenv("SEARCH_LOG_RETENTION_CLEANUP_ENABLED", "false").strip().lower() == "true"
        )
        
        # Model Versions (for cache invalidation)
        self.EMBEDDING_MODEL_VERSION = os.getenv("EMBEDDING_MODEL_VERSION", "v4")
        self.LLM_MODEL_VERSION = os.getenv("LLM_MODEL_VERSION", "v2")
        self._validate_model_versions()

        # Observability
        self.SENTRY_DSN = os.getenv("SENTRY_DSN")
        self.MEMORY_WARNING_THRESHOLD = float(os.getenv("MEMORY_WARNING_THRESHOLD", "75.0"))
        self.MEMORY_CRITICAL_THRESHOLD = float(os.getenv("MEMORY_CRITICAL_THRESHOLD", "85.0"))
        self.MEMORY_PROFILE_MIN_REFRESH_MINUTES = int(
            os.getenv("MEMORY_PROFILE_MIN_REFRESH_MINUTES", "30")
        )
        if self.MEMORY_PROFILE_MIN_REFRESH_MINUTES < 1:
            self.MEMORY_PROFILE_MIN_REFRESH_MINUTES = 30

        # Rate Limiting (Task A3)
        self.RATE_LIMIT_GLOBAL = os.getenv("RATE_LIMIT_GLOBAL", "1000/minute")
        self.RATE_LIMIT_SEARCH = os.getenv("RATE_LIMIT_SEARCH", "100/minute")
        self.RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "50/minute")
        self.RATE_LIMIT_INGEST = os.getenv("RATE_LIMIT_INGEST", "10/minute")
        self.RATE_LIMIT_EXTERNAL_SEARCH = os.getenv("RATE_LIMIT_EXTERNAL_SEARCH", "30/minute")
        self.RATE_LIMIT_AI_ENRICH = os.getenv("RATE_LIMIT_AI_ENRICH", "10/minute")
        self.RATE_LIMIT_AI_COVER = os.getenv("RATE_LIMIT_AI_COVER", "20/minute")
        self.RATE_LIMIT_AI_ANALYZE = os.getenv("RATE_LIMIT_AI_ANALYZE", "5/minute")

        # Chat / Memory Limits
        self.CHAT_CONTEXT_LIMIT = int(os.getenv("CHAT_CONTEXT_LIMIT", "5"))  # recent messages sent to AI
        self.CHAT_PROMPT_TURNS = int(os.getenv("CHAT_PROMPT_TURNS", "3"))    # turns injected into prompt
        self.CHAT_SUMMARY_LIMIT = int(os.getenv("CHAT_SUMMARY_LIMIT", "10")) # messages used for summary extraction
        self.CHAT_RETENTION_DAYS = int(os.getenv("CHAT_RETENTION_DAYS", "90"))
        self.CHAT_TITLE_MIN_MESSAGES = int(os.getenv("CHAT_TITLE_MIN_MESSAGES", "3"))
        self.CHAT_TITLE_MAX_LENGTH = int(os.getenv("CHAT_TITLE_MAX_LENGTH", "60"))

        # Graph Concept Strength
        self.CONCEPT_STRENGTH_MIN = float(os.getenv("CONCEPT_STRENGTH_MIN", "0.7"))
        self.GRAPH_ENRICH_ON_INGEST = os.getenv("GRAPH_ENRICH_ON_INGEST", "true").lower() == "true"
        self.GRAPH_ENRICH_MAX_ITEMS = int(os.getenv("GRAPH_ENRICH_MAX_ITEMS", "1"))
        self.GRAPH_ENRICH_TIMEOUT_SEC = int(os.getenv("GRAPH_ENRICH_TIMEOUT_SEC", "20"))

        # External KB (Wikidata + OpenAlex)
        default_academic_tags = (
            "sosyoloji,felsefe,psikoloji,ekonomi,tarih,hukuk,bilim,siyaset,politika,"
            "etik,metodoloji,teori,toplum,devlet,kamu,modernite"
        )
        academic_tag_raw = os.getenv("ACADEMIC_TAG_SET", default_academic_tags)
        self.ACADEMIC_TAG_SET = {
            tag.strip().lower()
            for tag in academic_tag_raw.split(",")
            if tag.strip()
        }
        self.EXTERNAL_KB_ENABLED = os.getenv("EXTERNAL_KB_ENABLED", "true").strip().lower() == "true"
        self.OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "").strip()
        self.OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "").strip()
        self.SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        self.EUROPEANA_API_KEY = os.getenv("EUROPEANA_API_KEY", "").strip()
        self.LINGUA_ROBOT_API_KEY = os.getenv("LINGUA_ROBOT_API_KEY", "").strip()
        self.WORDS_API_KEY = os.getenv("WORDS_API_KEY", "").strip()
        self.EXTERNAL_KB_OPENALEX_EXPLORER_ONLY = (
            os.getenv("EXTERNAL_KB_OPENALEX_EXPLORER_ONLY", "true").strip().lower() == "true"
        )
        self.EXTERNAL_KB_BACKFILL_BATCH_SIZE = int(os.getenv("EXTERNAL_KB_BACKFILL_BATCH_SIZE", "50"))
        if self.EXTERNAL_KB_BACKFILL_BATCH_SIZE < 1:
            self.EXTERNAL_KB_BACKFILL_BATCH_SIZE = 50
        self.EXTERNAL_KB_SYNC_TTL_HOURS = int(os.getenv("EXTERNAL_KB_SYNC_TTL_HOURS", "72"))
        if self.EXTERNAL_KB_SYNC_TTL_HOURS < 1:
            self.EXTERNAL_KB_SYNC_TTL_HOURS = 72
        self.EXTERNAL_KB_GRAPH_WEIGHT = float(os.getenv("EXTERNAL_KB_GRAPH_WEIGHT", "0.15"))
        self.EXTERNAL_KB_MAX_CANDIDATES = int(os.getenv("EXTERNAL_KB_MAX_CANDIDATES", "5"))
        self.EXTERNAL_KB_MIN_CONFIDENCE = float(os.getenv("EXTERNAL_KB_MIN_CONFIDENCE", "0.45"))
        self.EXTERNAL_KB_WIKIDATA_TIMEOUT_SEC = float(os.getenv("EXTERNAL_KB_WIKIDATA_TIMEOUT_SEC", "2.5"))
        self.EXTERNAL_KB_OPENALEX_TIMEOUT_SEC = float(os.getenv("EXTERNAL_KB_OPENALEX_TIMEOUT_SEC", "3.0"))
        self.EXTERNAL_KB_DBPEDIA_ENABLED = os.getenv("EXTERNAL_KB_DBPEDIA_ENABLED", "false").strip().lower() == "true"
        self.EXTERNAL_KB_ORKG_ENABLED = os.getenv("EXTERNAL_KB_ORKG_ENABLED", "false").strip().lower() == "true"
        self.EXTERNAL_KB_DBPEDIA_EXPLORER_ONLY = (
            os.getenv("EXTERNAL_KB_DBPEDIA_EXPLORER_ONLY", "true").strip().lower() == "true"
        )
        self.EXTERNAL_KB_ORKG_EXPLORER_ONLY = (
            os.getenv("EXTERNAL_KB_ORKG_EXPLORER_ONLY", "true").strip().lower() == "true"
        )
        self.EXTERNAL_KB_DBPEDIA_TIMEOUT_SEC = float(os.getenv("EXTERNAL_KB_DBPEDIA_TIMEOUT_SEC", "2.5"))
        self.EXTERNAL_KB_ORKG_TIMEOUT_SEC = float(os.getenv("EXTERNAL_KB_ORKG_TIMEOUT_SEC", "3.0"))
        self.EXTERNAL_KB_DBPEDIA_WEIGHT = float(os.getenv("EXTERNAL_KB_DBPEDIA_WEIGHT", "0.08"))
        self.EXTERNAL_KB_ORKG_WEIGHT = float(os.getenv("EXTERNAL_KB_ORKG_WEIGHT", "0.10"))
        self.EXTERNAL_KB_HTTP_MAX_RETRY = int(os.getenv("EXTERNAL_KB_HTTP_MAX_RETRY", "1"))

        # Explorer-only Islamic providers
        self.ISLAMIC_API_ENABLED = os.getenv("ISLAMIC_API_ENABLED", "false").strip().lower() == "true"
        self.ISLAMIC_API_EXPLORER_ONLY = (
            os.getenv("ISLAMIC_API_EXPLORER_ONLY", "true").strip().lower() == "true"
        )
        self.ISLAMIC_API_MAX_CANDIDATES = int(os.getenv("ISLAMIC_API_MAX_CANDIDATES", "4"))
        if self.ISLAMIC_API_MAX_CANDIDATES < 1:
            self.ISLAMIC_API_MAX_CANDIDATES = 4
        if self.ISLAMIC_API_MAX_CANDIDATES > 8:
            self.ISLAMIC_API_MAX_CANDIDATES = 8
        self.ISLAMIC_API_MIN_CONFIDENCE = float(os.getenv("ISLAMIC_API_MIN_CONFIDENCE", "0.45"))
        self.ISLAMIC_API_QURAN_WEIGHT = float(os.getenv("ISLAMIC_API_QURAN_WEIGHT", "0.22"))
        self.ISLAMIC_API_HADITH_WEIGHT = float(os.getenv("ISLAMIC_API_HADITH_WEIGHT", "0.18"))
        self.ISLAMIC_API_HTTP_TIMEOUT_SEC = float(os.getenv("ISLAMIC_API_HTTP_TIMEOUT_SEC", "6.0"))
        self.ISLAMIC_API_HTTP_MAX_RETRY = int(os.getenv("ISLAMIC_API_HTTP_MAX_RETRY", "1"))

        self.QURANENC_ENABLED = os.getenv("QURANENC_ENABLED", "true").strip().lower() == "true"
        self.QURANENC_API_BASE_URL = (
            os.getenv("QURANENC_API_BASE_URL", "https://quranenc.com/api/v1").strip().rstrip("/")
        )
        self.QURANENC_DEFAULT_LANGUAGE = (
            os.getenv("QURANENC_DEFAULT_LANGUAGE", "tr").strip().lower() or "tr"
        )
        self.QURANENC_DEFAULT_TRANSLATION_KEY = (
            os.getenv("QURANENC_DEFAULT_TRANSLATION_KEY", "").strip().lower()
        )
        self.QURANENC_TRANSLATION_CACHE_TTL_SEC = int(
            os.getenv("QURANENC_TRANSLATION_CACHE_TTL_SEC", "21600")
        )

        self.ISLAMHOUSE_ENABLED = os.getenv("ISLAMHOUSE_ENABLED", "true").strip().lower() == "true"
        self.ISLAMHOUSE_API_BASE_URL = (
            os.getenv("ISLAMHOUSE_API_BASE_URL", "https://api3.islamhouse.com/v3").strip().rstrip("/")
        )
        self.ISLAMHOUSE_API_KEY = os.getenv("ISLAMHOUSE_API_KEY", "paV29H2gm56kvLPy").strip()
        self.ISLAMHOUSE_DEFAULT_LANGUAGE = (
            os.getenv("ISLAMHOUSE_DEFAULT_LANGUAGE", "tr").strip().lower() or "tr"
        )
        self.ISLAMHOUSE_MAX_CATEGORIES = int(os.getenv("ISLAMHOUSE_MAX_CATEGORIES", "2"))
        self.ISLAMHOUSE_ITEMS_PER_TYPE = int(os.getenv("ISLAMHOUSE_ITEMS_PER_TYPE", "2"))
        self.ISLAMHOUSE_CATEGORY_CACHE_TTL_SEC = int(
            os.getenv("ISLAMHOUSE_CATEGORY_CACHE_TTL_SEC", "21600")
        )
        self.ISLAMHOUSE_WEIGHT = float(os.getenv("ISLAMHOUSE_WEIGHT", "0.11"))

        self.QURAN_FOUNDATION_ENABLED = os.getenv("QURAN_FOUNDATION_ENABLED", "false").strip().lower() == "true"
        self.QURAN_FOUNDATION_CLIENT_ID = os.getenv("QURAN_FOUNDATION_CLIENT_ID", "").strip()
        self.QURAN_FOUNDATION_CLIENT_SECRET = os.getenv("QURAN_FOUNDATION_CLIENT_SECRET", "").strip()
        self.QURAN_FOUNDATION_OAUTH_URL = (
            os.getenv("QURAN_FOUNDATION_OAUTH_URL", "https://oauth2.quran.foundation").strip().rstrip("/")
        )
        self.QURAN_FOUNDATION_CONTENT_SCOPE = (
            os.getenv("QURAN_FOUNDATION_CONTENT_SCOPE", "content").strip() or "content"
        )
        self.QURAN_FOUNDATION_API_BASE_URL = (
            os.getenv(
                "QURAN_FOUNDATION_API_BASE_URL",
                "https://apis.quran.foundation/content/api/v4",
            ).strip().rstrip("/")
        )
        self.QURAN_FOUNDATION_DEFAULT_TRANSLATION_IDS = _parse_csv(
            os.getenv("QURAN_FOUNDATION_DEFAULT_TRANSLATION_IDS", "77")
        )
        self.QURAN_FOUNDATION_DEFAULT_LANGUAGE = (
            os.getenv("QURAN_FOUNDATION_DEFAULT_LANGUAGE", "tr").strip().lower() or "tr"
        )
        self.QURAN_FOUNDATION_DEFAULT_TAFSIR_ID = int(
            os.getenv("QURAN_FOUNDATION_DEFAULT_TAFSIR_ID", "169")
        )
        self.QURAN_FOUNDATION_DEFAULT_TAFSIR_NAME = (
            os.getenv("QURAN_FOUNDATION_DEFAULT_TAFSIR_NAME", "Ibn Kathir (Abridged)").strip()
            or "Ibn Kathir (Abridged)"
        )

        self.DIYANET_QURAN_ENABLED = os.getenv("DIYANET_QURAN_ENABLED", "false").strip().lower() == "true"
        self.DIYANET_QURAN_API_KEY = os.getenv("DIYANET_QURAN_API_KEY", "").strip()
        self.DIYANET_QURAN_BASE_URL = (
            os.getenv(
                "DIYANET_QURAN_BASE_URL",
                "https://acikkaynakkuran-dev.diyanet.gov.tr",
            ).strip().rstrip("/")
        )

        self.HADEETHENC_ENABLED = os.getenv("HADEETHENC_ENABLED", "false").strip().lower() == "true"
        self.HADEETHENC_API_BASE_URL = (
            os.getenv("HADEETHENC_API_BASE_URL", "https://hadeethenc.com/api/v1").strip().rstrip("/")
        )
        self.HADEETHENC_LANGUAGE_PRIMARY = (
            os.getenv("HADEETHENC_LANGUAGE_PRIMARY", "tr").strip().lower() or "tr"
        )
        self.HADEETHENC_LANGUAGE_FALLBACK = (
            os.getenv("HADEETHENC_LANGUAGE_FALLBACK", "en").strip().lower() or "en"
        )
        self.HADEETHENC_CATEGORY_CACHE_TTL_SEC = int(
            os.getenv("HADEETHENC_CATEGORY_CACHE_TTL_SEC", "21600")
        )

        self.RELIGIOUS_DATASET_SEARCH_ENABLED = (
            os.getenv("RELIGIOUS_DATASET_SEARCH_ENABLED", "false").strip().lower() == "true"
        )
        self.RELIGIOUS_DATASET_TIMEOUT_SEC = float(
            os.getenv("RELIGIOUS_DATASET_TIMEOUT_SEC", "0.45")
        )
        self.RELIGIOUS_DATASET_TOPK = int(os.getenv("RELIGIOUS_DATASET_TOPK", "3"))
        if self.RELIGIOUS_DATASET_TOPK < 1:
            self.RELIGIOUS_DATASET_TOPK = 3
        if self.RELIGIOUS_DATASET_TOPK > 6:
            self.RELIGIOUS_DATASET_TOPK = 6
        self.RELIGIOUS_DATASET_TYPESENSE_URL = (
            os.getenv("RELIGIOUS_DATASET_TYPESENSE_URL", "http://typesense:8108").strip().rstrip("/")
        )
        self.RELIGIOUS_DATASET_TYPESENSE_API_KEY = (
            os.getenv("RELIGIOUS_DATASET_TYPESENSE_API_KEY", "").strip()
        )
        self.RELIGIOUS_DATASET_HADITH_COLLECTION = (
            os.getenv("RELIGIOUS_DATASET_HADITH_COLLECTION", "religious_hadith_current").strip()
            or "religious_hadith_current"
        )
        self.RELIGIOUS_DATASET_QURAN_COLLECTION = (
            os.getenv("RELIGIOUS_DATASET_QURAN_COLLECTION", "religious_quran_current").strip()
            or "religious_quran_current"
        )
        self.RELIGIOUS_DATASET_HADITH_WEIGHT = float(
            os.getenv("RELIGIOUS_DATASET_HADITH_WEIGHT", "0.13")
        )
        self.RELIGIOUS_DATASET_QURAN_WEIGHT = float(
            os.getenv("RELIGIOUS_DATASET_QURAN_WEIGHT", "0.14")
        )
        self.RELIGIOUS_DATASET_CB_FAILURE_THRESHOLD = int(
            os.getenv("RELIGIOUS_DATASET_CB_FAILURE_THRESHOLD", "3")
        )
        self.RELIGIOUS_DATASET_CB_RECOVERY_TIMEOUT_SEC = int(
            os.getenv("RELIGIOUS_DATASET_CB_RECOVERY_TIMEOUT_SEC", "30")
        )

        # Flow (Layer 4) text repair: deterministic display-time OCR/imla fix
        self.FLOW_TEXT_REPAIR_ENABLED = os.getenv("FLOW_TEXT_REPAIR_ENABLED", "true").strip().lower() == "true"
        source_types_raw = os.getenv(
            "FLOW_TEXT_REPAIR_SOURCE_TYPES",
            "PDF,EPUB,PDF_CHUNK,ARTICLE,WEBSITE"
        )
        self.FLOW_TEXT_REPAIR_SOURCE_TYPES = [
            st.strip().upper() for st in source_types_raw.split(",") if st.strip()
        ]
        if not self.FLOW_TEXT_REPAIR_SOURCE_TYPES:
            self.FLOW_TEXT_REPAIR_SOURCE_TYPES = ["PDF", "EPUB", "PDF_CHUNK", "ARTICLE", "WEBSITE"]
        self.FLOW_TEXT_REPAIR_MAX_DELTA_RATIO = float(
            os.getenv("FLOW_TEXT_REPAIR_MAX_DELTA_RATIO", "0.12")
        )
        self.FLOW_TEXT_REPAIR_MAX_INPUT_CHARS = int(
            os.getenv("FLOW_TEXT_REPAIR_MAX_INPUT_CHARS", "4000")
        )
        self.FLOW_TEXT_REPAIR_RULESET_VERSION = os.getenv(
            "FLOW_TEXT_REPAIR_RULESET_VERSION",
            "tr_flow_v1"
        ).strip() or "tr_flow_v1"
    
    def _init_firebase(self):
        """Initialize Firebase Admin SDK if credentials available."""
        try:
            import firebase_admin
            from firebase_admin import credentials
            
            if firebase_admin._apps:
                # Already initialized
                self.FIREBASE_READY = True
                return
            
            # Look for service account credentials
            cred_path = self.FIREBASE_CREDENTIALS_PATH
            if cred_path and not os.path.isabs(cred_path):
                rel = cred_path.lstrip("./\\")
                cred_path = os.path.join(_CONFIG_DIR, rel)

            if cred_path and os.path.exists(cred_path):
                try:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    self.FIREBASE_READY = True
                    logger.info("✓ Firebase Admin SDK initialized from credentials file")
                except Exception as e:
                    logger.error(f"Failed to initialize Firebase with credentials: {e}")
                    self.FIREBASE_READY = False
            else:
                if self.ENVIRONMENT == "production":
                    # STRICT ENFORCEMENT: Fail fast if credentials missing in Prod
                    raise ValueError(
                        "CRITICAL SECURITY: Firebase credentials missing in Production. "
                        "Set GOOGLE_APPLICATION_CREDENTIALS. "
                        "Dev workaround is disabled."
                    )
                logger.warning("Firebase credentials not configured (OK for development only)")
                self.FIREBASE_READY = False
        
        except ImportError:
            logger.error("firebase-admin not installed")
            self.FIREBASE_READY = False
        except Exception as e:
            logger.error(f"Unexpected error initializing Firebase: {e}")
            self.FIREBASE_READY = False
    
    def _validate_model_versions(self):
        """
        Validate model versions on startup.
        
        Ensures:
        1. Version format is correct (v1, v2, v1.0.1, etc.)
        2. If .deployed file exists, versions are newer than last deployment
        
        Prevents cache invalidation bugs by requiring explicit version bumps.
        """
        # Validate format for both versions
        for version_name, version_str in [
            ("LLM_MODEL_VERSION", self.LLM_MODEL_VERSION),
            ("EMBEDDING_MODEL_VERSION", self.EMBEDDING_MODEL_VERSION)
        ]:
            if not re.match(r'^v\d+(\.\d+)*$', version_str):
                raise ValueError(
                    f"Invalid {version_name} format: {version_str}. "
                    f"Use format: v1, v2, v1.0.1, etc."
                )
        
        # Load last deployed versions if .deployed file exists
        last_deployed = self._load_last_deployed_versions()
        
        if last_deployed:
            # Check LLM version is newer
            if last_deployed.get('llm'):
                comparison = self._compare_versions(
                    self.LLM_MODEL_VERSION,
                    last_deployed['llm']
                )
                if comparison <= 0:
                    suggestion = self._next_version(last_deployed['llm'])
                    raise ValueError(
                        f"❌ LLM_MODEL_VERSION must be newer than last deployed!\n"
                        f"   Last deployed: {last_deployed['llm']}\n"
                        f"   Current: {self.LLM_MODEL_VERSION}\n"
                        f"   Suggestion: Update to {suggestion} in .env"
                    )
            
            # Check EMBEDDING version is newer
            if last_deployed.get('embedding'):
                comparison = self._compare_versions(
                    self.EMBEDDING_MODEL_VERSION,
                    last_deployed['embedding']
                )
                if comparison <= 0:
                    suggestion = self._next_version(last_deployed['embedding'])
                    raise ValueError(
                        f"❌ EMBEDDING_MODEL_VERSION must be newer than last deployed!\n"
                        f"   Last deployed: {last_deployed['embedding']}\n"
                        f"   Current: {self.EMBEDDING_MODEL_VERSION}\n"
                        f"   Suggestion: Update to {suggestion} in .env"
                    )
            
            logger.info(
                f"✓ Model versions validated (newer than last deployment):\n"
                f"  LLM: {self.LLM_MODEL_VERSION} (was {last_deployed.get('llm', 'unknown')})\n"
                f"  Embedding: {self.EMBEDDING_MODEL_VERSION} (was {last_deployed.get('embedding', 'unknown')})"
            )
        else:
            logger.info(
                f"✓ Model versions validated (no previous deployment):\n"
                f"  LLM: {self.LLM_MODEL_VERSION}\n"
                f"  Embedding: {self.EMBEDDING_MODEL_VERSION}"
            )
    
    def _load_last_deployed_versions(self) -> Optional[Dict]:
        """Load versions from .deployed file (created on successful deploy)."""
        deployed_file = os.path.join(os.path.dirname(__file__), '.deployed')
        if os.path.exists(deployed_file):
            try:
                import json
                with open(deployed_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read .deployed file: {e}")
        return None
    
    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """Compare two version strings. Returns: >0 if v1 > v2, <0 if v1 < v2, 0 if equal."""
        def parse(v):
            return [int(x) for x in v.lstrip('v').split('.')]
        
        parts1 = parse(v1)
        parts2 = parse(v2)
        
        # Pad with zeros
        max_len = max(len(parts1), len(parts2))
        parts1 += [0] * (max_len - len(parts1))
        parts2 += [0] * (max_len - len(parts2))
        
        if parts1 > parts2:
            return 1
        elif parts1 < parts2:
            return -1
        else:
            return 0
    
    @staticmethod
    def _next_version(current: str) -> str:
        """Suggest next version number."""
        if not current:
            return "v2"
        
        parts = current.lstrip('v').split('.')
        parts[0] = str(int(parts[0]) + 1)
        return 'v' + '.'.join(parts)

settings = Settings()
