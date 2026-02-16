"""
Phase 3: Model Version Validation Tests
========================================

Tests for the version tracking and validation system that prevents cache
invalidation bugs by enforcing model version bumps on deployment.

Run with:
    pytest apps/backend/test_phase3_version_validation.py -v

Coverage:
    - Version format validation
    - Version comparison logic
    - Deployment version enforcement
    - .deployed file handling
    - Startup validation
"""

import pytest  # type: ignore
import os
import sys
import json
import tempfile
from pathlib import Path
from unittest import mock
from typing import Dict, Optional

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from config import Settings


class TestVersionFormatValidation:
    """Test version string format validation."""
    
    def test_valid_version_formats(self):
        """Test that valid version formats are accepted."""
        valid_formats = [
            "v1",
            "v2",
            "v10",
            "v1.0",
            "v1.0.0",
            "v2.3.4",
            "v10.20.30.40"
        ]
        
        for version in valid_formats:
            with mock.patch.dict(os.environ, {
                "DB_PASSWORD": "test",
                "GEMINI_API_KEY": "test",
                "LLM_MODEL_VERSION": version,
                "EMBEDDING_MODEL_VERSION": version
            }):
                # Should not raise
                settings = Settings()
                assert settings.LLM_MODEL_VERSION == version
                assert settings.EMBEDDING_MODEL_VERSION == version
    
    def test_invalid_version_formats(self):
        """Test that invalid version formats are rejected."""
        invalid_formats = [
            "1.0",           # Missing 'v' prefix
            "version1",      # Wrong prefix
            "v",             # No number
            "v1.0.0.0.0",    # Too many dots (OK actually per spec)
            "v1a",           # Contains letter
            "v-1",           # Negative number
            "V1",            # Uppercase V
            "",              # Empty
            "1",             # No prefix
        ]
        
        for version in invalid_formats:
            with mock.patch.dict(os.environ, {
                "DB_PASSWORD": "test",
                "GEMINI_API_KEY": "test",
                "LLM_MODEL_VERSION": version,
                "EMBEDDING_MODEL_VERSION": version
            }):
                with pytest.raises(ValueError, match="Invalid.*version.*format"):
                    Settings()


class TestVersionComparison:
    """Test version comparison logic."""
    
    def test_compare_major_versions(self):
        """Test comparison of major version numbers."""
        assert Settings._compare_versions("v2", "v1") > 0
        assert Settings._compare_versions("v1", "v2") < 0
        assert Settings._compare_versions("v1", "v1") == 0
        assert Settings._compare_versions("v10", "v2") > 0
    
    def test_compare_minor_versions(self):
        """Test comparison with minor version numbers."""
        assert Settings._compare_versions("v1.1", "v1.0") > 0
        assert Settings._compare_versions("v1.0", "v1.1") < 0
        assert Settings._compare_versions("v1.0", "v1.0") == 0
        assert Settings._compare_versions("v1.10", "v1.2") > 0
    
    def test_compare_patch_versions(self):
        """Test comparison with patch version numbers."""
        assert Settings._compare_versions("v1.0.1", "v1.0.0") > 0
        assert Settings._compare_versions("v1.0.0", "v1.0.1") < 0
        assert Settings._compare_versions("v1.0.0", "v1.0.0") == 0
    
    def test_compare_different_lengths(self):
        """Test comparison when versions have different number of parts."""
        assert Settings._compare_versions("v1.0", "v1") == 0
        assert Settings._compare_versions("v1.0.0", "v1") == 0
        assert Settings._compare_versions("v2.0.0", "v1.9.9") > 0
        assert Settings._compare_versions("v1.9.9", "v2.0.0") < 0


class TestVersionSuggestion:
    """Test next version number suggestion."""
    
    def test_suggest_next_major_version(self):
        """Test suggesting next major version."""
        assert Settings._next_version("v1") == "v2"
        assert Settings._next_version("v2") == "v3"
        assert Settings._next_version("v10") == "v11"
    
    def test_suggest_next_with_minor(self):
        """Test suggesting next version when minor version exists."""
        assert Settings._next_version("v1.0") == "v2.0"
        assert Settings._next_version("v1.5") == "v2.5"
    
    def test_suggest_next_with_patch(self):
        """Test suggesting next version when patch version exists."""
        assert Settings._next_version("v1.0.0") == "v2.0.0"
        assert Settings._next_version("v2.3.4") == "v3.3.4"
    
    def test_suggest_next_empty(self):
        """Test suggesting first version."""
        assert Settings._next_version("") == "v2"
        assert Settings._next_version(None) == "v2"


class TestDeployedVersionLoading:
    """Test loading and parsing of .deployed file."""
    
    def test_load_nonexistent_deployed_file(self):
        """Test that missing .deployed file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v2",
                    "EMBEDDING_MODEL_VERSION": "v3"
                }):
                    settings = Settings()
                    result = settings._load_last_deployed_versions()
                    assert result is None
    
    def test_load_deployed_file(self):
        """Test loading valid .deployed file."""
        deployed_content = {
            "llm": "v1",
            "embedding": "v2",
            "timestamp": "2026-02-02T12:00:00Z",
            "commit": "abc123"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .deployed file
            deployed_path = Path(tmpdir) / ".deployed"
            with open(deployed_path, "w") as f:
                json.dump(deployed_content, f)
            
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v2",
                    "EMBEDDING_MODEL_VERSION": "v3"
                }):
                    settings = Settings()
                    result = settings._load_last_deployed_versions()
                    assert result == deployed_content
    
    def test_load_malformed_deployed_file(self):
        """Test handling of malformed .deployed file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid JSON
            deployed_path = Path(tmpdir) / ".deployed"
            with open(deployed_path, "w") as f:
                f.write("{ invalid json")
            
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v2",
                    "EMBEDDING_MODEL_VERSION": "v3"
                }):
                    settings = Settings()
                    result = settings._load_last_deployed_versions()
                    assert result is None  # Should handle gracefully


class TestVersionEnforcement:
    """Test that versions are enforced to be newer than deployed."""
    
    def test_success_when_no_deployed_file(self):
        """Version validation succeeds when no .deployed file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v1",
                    "EMBEDDING_MODEL_VERSION": "v1"
                }):
                    # Should not raise
                    settings = Settings()
                    assert settings.LLM_MODEL_VERSION == "v1"
    
    def test_success_when_versions_newer(self):
        """Version validation succeeds when current > deployed."""
        deployed_content = {
            "llm": "v1",
            "embedding": "v2"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .deployed file
            deployed_path = Path(tmpdir) / ".deployed"
            with open(deployed_path, "w") as f:
                json.dump(deployed_content, f)
            
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v2",  # Newer than v1
                    "EMBEDDING_MODEL_VERSION": "v3"  # Newer than v2
                }):
                    # Should not raise
                    settings = Settings()
                    assert settings.LLM_MODEL_VERSION == "v2"
                    assert settings.EMBEDDING_MODEL_VERSION == "v3"
    
    def test_failure_when_llm_not_bumped(self):
        """Version validation fails when LLM not bumped."""
        deployed_content = {
            "llm": "v2",
            "embedding": "v1"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .deployed file
            deployed_path = Path(tmpdir) / ".deployed"
            with open(deployed_path, "w") as f:
                json.dump(deployed_content, f)
            
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v2",  # NOT newer than v2
                    "EMBEDDING_MODEL_VERSION": "v2"
                }):
                    with pytest.raises(ValueError, match="LLM_MODEL_VERSION must be newer"):
                        Settings()
    
    def test_failure_when_embedding_not_bumped(self):
        """Version validation fails when EMBEDDING not bumped."""
        deployed_content = {
            "llm": "v1",
            "embedding": "v3"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .deployed file
            deployed_path = Path(tmpdir) / ".deployed"
            with open(deployed_path, "w") as f:
                json.dump(deployed_content, f)
            
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v2",
                    "EMBEDDING_MODEL_VERSION": "v3"  # NOT newer than v3
                }):
                    with pytest.raises(ValueError, match="EMBEDDING_MODEL_VERSION must be newer"):
                        Settings()
    
    def test_error_suggests_next_version(self):
        """Error message suggests what the next version should be."""
        deployed_content = {
            "llm": "v1",
            "embedding": "v2"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .deployed file
            deployed_path = Path(tmpdir) / ".deployed"
            with open(deployed_path, "w") as f:
                json.dump(deployed_content, f)
            
            with mock.patch('config.os.path.dirname', return_value=tmpdir):
                with mock.patch.dict(os.environ, {
                    "DB_PASSWORD": "test",
                    "GEMINI_API_KEY": "test",
                    "LLM_MODEL_VERSION": "v1",  # NOT bumped
                    "EMBEDDING_MODEL_VERSION": "v3"
                }):
                    with pytest.raises(ValueError) as exc_info:
                        Settings()
                    
                    # Should suggest v2
                    assert "v2" in str(exc_info.value)


class TestManualValidation:
    """
    Manual validation checklist.
    
    Run these manually to verify Phase 3 behavior:
    """
    
    def test_version_format_help_text(self):
        """
        ✓ Valid formats: v1, v2, v1.0.1, v2.0.0, etc.
        ✓ Invalid formats: 1, v, version1, etc.
        """
        pass
    
    def test_deployed_file_format(self):
        """
        Create apps/backend/.deployed with:
        {
          "llm": "v1",
          "embedding": "v2",
          "timestamp": "2026-02-02T12:00:00Z",
          "commit": "abc123"
        }
        
        ✓ Should be readable by Settings._load_last_deployed_versions()
        """
        pass
    
    def test_startup_validation_success(self):
        """
        Run: python apps/backend/app.py
        
        Check logs for:
        ✓ "Model versions validated successfully"
        
        Or if .deployed exists:
        ✓ "Model versions validated (newer than last deployment)"
        """
        pass
    
    def test_startup_validation_failure(self):
        """
        Create .deployed with {"llm": "v2", "embedding": "v1"}
        Set env: LLM_MODEL_VERSION=v2 (not bumped)
        
        Run: python apps/backend/app.py
        
        Check for error:
        ❌ "Configuration Error: LLM_MODEL_VERSION must be newer than last deployed"
        ✓ Server should not start
        """
        pass
    
    def test_deployment_recording(self):
        """
        Run: python scripts/record_deployment_versions.py
        
        Check output:
        ✓ "✓ Deployment versions recorded and validated successfully"
        ✓ apps/backend/.deployed is created/updated with current versions
        """
        pass
    
    def test_version_bump_workflow(self):
        """
        Workflow test:
        1. Edit .env to change model/prompt: LLM_MODEL_VERSION=v2
        2. Deploy application
        3. Run: python scripts/record_deployment_versions.py
        4. Later, try to deploy again without bumping version
        5. Should fail at startup with clear error message
        """
        pass
