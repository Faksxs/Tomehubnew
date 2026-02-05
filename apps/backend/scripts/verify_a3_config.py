
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add backend to path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BACKEND_DIR)

os.chdir(BACKEND_DIR)

class TestRateLimitConfig(unittest.TestCase):
    def test_settings_overrides(self):
        """Test that environment variables correctly override default rate limits."""
        test_env = {
            "RATE_LIMIT_GLOBAL": "555/minute",
            "RATE_LIMIT_SEARCH": "222/minute",
            "RATE_LIMIT_INGEST": "11/minute",
            "DB_PASSWORD": "test", # Prevent config validation failure
            "GEMINI_API_KEY": "test"
        }
        
        with patch.dict(os.environ, test_env):
            # Re-import or re-initialize settings to pick up new env
            import config
            from importlib import reload
            reload(config)
            settings = config.Settings()
            
            print(f"Global Limit: {settings.RATE_LIMIT_GLOBAL}")
            self.assertEqual(settings.RATE_LIMIT_GLOBAL, "555/minute")
            self.assertEqual(settings.RATE_LIMIT_SEARCH, "222/minute")
            self.assertEqual(settings.RATE_LIMIT_INGEST, "11/minute")

    def test_app_limiter_setup(self):
        """Verify that the limiter in app.py uses the settings."""
        # We mock DB and other heavy dependencies to just check the limiter setup
        with patch('infrastructure.db_manager.DatabaseManager.init_pool'), \
             patch('services.cache_service.init_cache'), \
             patch('firebase_admin.initialize_app'), \
             patch('firebase_admin.get_app'):
            
            from app import limiter
            from config import settings
            
            # Check if default limits are set from settings
            # limiter._default_limits is normally a list of Limit objects
            self.assertTrue(any(settings.RATE_LIMIT_GLOBAL in str(l) for l in limiter._default_limits))
            print("✓ App limiter default limit verified")

if __name__ == "__main__":
    # Mock necessary environment for config validation
    os.environ["DB_PASSWORD"] = "dummy"
    os.environ["GEMINI_API_KEY"] = "dummy"
    unittest.main()
