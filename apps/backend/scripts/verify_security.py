
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Mocking modules BEFORE import
sys.modules['uvicorn'] = MagicMock()
sys.modules['firebase_admin'] = MagicMock()
sys.modules['firebase_admin.auth'] = MagicMock()
sys.modules['oracledb'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()
sys.modules['fastapi'] = MagicMock()
sys.modules['pydantic'] = MagicMock()
# We need to mock slowapi if it wasn't installed, but we installed it.
# However, if slowapi imports starlette/fastapi, it might fail?
# slowapi depends on limits.
# Let's hope slowapi doesn't explode if fastapi is mocked.

# Add backend to path

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestSecurityHardening(unittest.TestCase):
    
    def test_config_validation(self):
        print("\n[TEST] Verifying Config Secret Validation")
        from config import Settings
        
        # Test Missing DB_PASSWORD
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True):
            with self.assertRaises(ValueError) as cm:
                Settings()
            self.assertIn("DB_PASSWORD is missing", str(cm.exception))
            print("  - Correctly raised ValueError for missing DB_PASSWORD")

        # Test Missing GEMINI_API_KEY
        with patch.dict(os.environ, {"DB_PASSWORD": "test"}, clear=True):
            with self.assertRaises(ValueError) as cm:
                Settings()
            self.assertIn("GEMINI_API_KEY is missing", str(cm.exception))
            print("  - Correctly raised ValueError for missing GEMINI_API_KEY")
            
        # Test Valid
        with patch.dict(os.environ, {"DB_PASSWORD": "ok", "GEMINI_API_KEY": "ok"}, clear=True):
            try:
                Settings()
                print("  - Config initialized successfully when secrets present")
            except ValueError:
                self.fail("Config raised ValueError despite secrets being present")

    def test_app_rate_limiting_setup(self):
        print("\n[TEST] Verifying App Rate Limiting Setup")
        # Ensure we can import app and check limiter
        # We need to set env vars so app imports config without error
        with patch.dict(os.environ, {"DB_PASSWORD": "dummy", "GEMINI_API_KEY": "dummy"}):
            try:
                from app import app
                self.assertTrue(hasattr(app.state, 'limiter'), "app.state.limiter is missing")
                from slowapi import Limiter
                self.assertIsInstance(app.state.limiter, Limiter)
                print("  - Limiter is correctly attached to app.state")
            except ImportError as e:
                self.fail(f"Could not import app: {e}")
            except Exception as e:
                self.fail(f"App initialization failed: {e}")

if __name__ == '__main__':
    unittest.main()
