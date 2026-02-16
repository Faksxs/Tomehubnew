
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
        
        # Security / Firebase
        self.FIREBASE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.FIREBASE_READY = False
        self._init_firebase()
        self.DEV_UNSAFE_AUTH_BYPASS = (
            os.getenv("DEV_UNSAFE_AUTH_BYPASS", "false").strip().lower() == "true"
        )
        
        # AI
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.LLM_MODEL_LITE = os.getenv("LLM_MODEL_LITE", "gemini-2.5-flash-lite")
        self.LLM_MODEL_FLASH = os.getenv("LLM_MODEL_FLASH", "gemini-2.5-flash")
        self.LLM_MODEL_PRO = os.getenv("LLM_MODEL_PRO", "gemini-2.5-pro")
        self.EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "gemini-embedding-001")
        self.LLM_PRO_FALLBACK_ENABLED = os.getenv("LLM_PRO_FALLBACK_ENABLED", "true").strip().lower() == "true"
        self.LLM_PRO_FALLBACK_MAX_PER_REQUEST = int(os.getenv("LLM_PRO_FALLBACK_MAX_PER_REQUEST", "1"))
        if self.LLM_PRO_FALLBACK_MAX_PER_REQUEST < 0:
            self.LLM_PRO_FALLBACK_MAX_PER_REQUEST = 0
        self.NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
        self.NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com").strip().rstrip("/")
        self.LLM_EXPLORER_QWEN_PILOT_ENABLED = (
            os.getenv("LLM_EXPLORER_QWEN_PILOT_ENABLED", "true").strip().lower() == "true"
        )
        self.LLM_EXPLORER_PRIMARY_PROVIDER = (
            os.getenv("LLM_EXPLORER_PRIMARY_PROVIDER", "qwen").strip().lower() or "qwen"
        )
        self.LLM_EXPLORER_PRIMARY_MODEL = (
            os.getenv("LLM_EXPLORER_PRIMARY_MODEL", "qwen/qwen3-next-80b-a3b-instruct").strip()
            or "qwen/qwen3-next-80b-a3b-instruct"
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
        
        # Retrieval Fusion Mode (Phase-1)
        # - concat: strict bucket concatenation (exact > lemma > semantic)
        # - rrf: reciprocal rank fusion over bucket rankings
        self.RETRIEVAL_FUSION_MODE = os.getenv("RETRIEVAL_FUSION_MODE", "concat").strip().lower()
        if self.RETRIEVAL_FUSION_MODE not in {"concat", "rrf"}:
            logger.warning(
                f"Invalid RETRIEVAL_FUSION_MODE='{self.RETRIEVAL_FUSION_MODE}', falling back to 'concat'"
            )
            self.RETRIEVAL_FUSION_MODE = "concat"

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
        self.EMBEDDING_MODEL_VERSION = os.getenv("EMBEDDING_MODEL_VERSION", "v3")
        self.LLM_MODEL_VERSION = os.getenv("LLM_MODEL_VERSION", "v2")
        self._validate_model_versions()

        # Observability
        self.SENTRY_DSN = os.getenv("SENTRY_DSN")
        self.MEMORY_WARNING_THRESHOLD = float(os.getenv("MEMORY_WARNING_THRESHOLD", "75.0"))
        self.MEMORY_CRITICAL_THRESHOLD = float(os.getenv("MEMORY_CRITICAL_THRESHOLD", "85.0"))

        # Rate Limiting (Task A3)
        self.RATE_LIMIT_GLOBAL = os.getenv("RATE_LIMIT_GLOBAL", "1000/minute")
        self.RATE_LIMIT_SEARCH = os.getenv("RATE_LIMIT_SEARCH", "100/minute")
        self.RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "50/minute")
        self.RATE_LIMIT_INGEST = os.getenv("RATE_LIMIT_INGEST", "10/minute")
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
            if self.FIREBASE_CREDENTIALS_PATH and os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
                try:
                    cred = credentials.Certificate(self.FIREBASE_CREDENTIALS_PATH)
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
