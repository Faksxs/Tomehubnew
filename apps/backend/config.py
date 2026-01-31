
import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
# This ensures credentials are available regardless of import order
load_dotenv()

class Settings:
    def __init__(self):
        # Database
        self.DB_USER = os.getenv("DB_USER", "ADMIN")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD")
        self.DB_DSN = os.getenv("DB_DSN", "tomehubdb_high")
        
        # Security / Firebase
        # If GOOGLE_APPLICATION_CREDENTIALS is set, Firebase Admin uses it automatically.
        self.FIREBASE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") 
        
        # AI
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        
        # Validation
        if not self.DB_PASSWORD:
            raise ValueError("CRITICAL: DB_PASSWORD is missing from environment variables.")
        if not self.GEMINI_API_KEY:
            raise ValueError("CRITICAL: GEMINI_API_KEY is missing from environment variables.")

        # CORS
        # Default to localhost if not set, but allow overriding via env var
        # Format: "http://localhost:5173,http://localhost:3000,https://myapp.com"
        allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
        self.ALLOWED_ORIGINS: List[str] = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]
        
        # Cache Configuration
        self.REDIS_URL = os.getenv("REDIS_URL", None)  # e.g., "redis://localhost:6379/0"
        self.CACHE_L1_MAXSIZE = int(os.getenv("CACHE_L1_MAXSIZE", "1000"))
        self.CACHE_L1_TTL = int(os.getenv("CACHE_L1_TTL", "600"))  # 10 minutes
        self.CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        
        # Model Versions (for cache invalidation)
        self.EMBEDDING_MODEL_VERSION = os.getenv("EMBEDDING_MODEL_VERSION", "v2")
        self.LLM_MODEL_VERSION = os.getenv("LLM_MODEL_VERSION", "v1")

        # Observability
        self.SENTRY_DSN = os.getenv("SENTRY_DSN")

settings = Settings()
