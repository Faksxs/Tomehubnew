
import os
import logging
import re
from typing import List, Optional, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
# This ensures credentials are available regardless of import order
load_dotenv()

logger = logging.getLogger(__name__)

class Settings:
    def __init__(self):
        # Environment mode
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
        
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
        
        # AI
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.ANSWER_MODEL_NAME = os.getenv("ANSWER_MODEL_NAME", "gemini-flash-latest")
        
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
        
        # Model Versions (for cache invalidation)
        self.EMBEDDING_MODEL_VERSION = os.getenv("EMBEDDING_MODEL_VERSION", "v2")
        self.LLM_MODEL_VERSION = os.getenv("LLM_MODEL_VERSION", "v1")
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
