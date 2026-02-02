#!/usr/bin/env python3
"""
Record Deployment Versions Script
==================================

Records the current LLM_MODEL_VERSION and EMBEDDING_MODEL_VERSION to .deployed file
after successful deployment. This file is used by config.py to validate that versions
are bumped before the next deployment.

Usage (from CI/CD pipeline after successful deployment):
    python scripts/record_deployment_versions.py

Output:
    Creates apps/backend/.deployed with content like:
    {
      "llm": "v2",
      "embedding": "v3",
      "timestamp": "2026-02-02T14:30:45Z",
      "commit": "abc123def"
    }

This prevents the deployment bug where:
1. Developer changes LLM prompt
2. Forgets to bump LLM_MODEL_VERSION
3. Old cached results are reused with new prompts → stale decisions
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

def get_env_variable(key: str) -> Optional[str]:
    """Load environment variable from .env file."""
    env_path = Path(__file__).parent.parent / "apps" / "backend" / ".env"
    
    if not env_path.exists():
        print(f"⚠️  .env not found at {env_path}")
        return os.getenv(key)
    
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
    except Exception as e:
        print(f"⚠️  Error reading .env: {e}")
    
    return os.getenv(key)

def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

def record_deployment_versions() -> bool:
    """
    Record versions to .deployed file.
    
    Returns:
        True if successful, False otherwise
    """
    print("📝 Recording deployment versions...")
    
    # Get versions from environment
    llm_version = get_env_variable("LLM_MODEL_VERSION")
    embedding_version = get_env_variable("EMBEDDING_MODEL_VERSION")
    
    if not llm_version:
        llm_version = "v1"
        print(f"⚠️  LLM_MODEL_VERSION not set, using default: {llm_version}")
    
    if not embedding_version:
        embedding_version = "v2"
        print(f"⚠️  EMBEDDING_MODEL_VERSION not set, using default: {embedding_version}")
    
    # Prepare deployment record
    deployment_record = {
        "llm": llm_version,
        "embedding": embedding_version,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "commit": get_git_commit()
    }
    
    # Write to .deployed file
    deployed_file = Path(__file__).parent.parent / "apps" / "backend" / ".deployed"
    
    try:
        with open(deployed_file, "w") as f:
            json.dump(deployment_record, f, indent=2)
        
        print(f"✓ Deployment versions recorded:")
        print(f"  LLM: {llm_version}")
        print(f"  Embedding: {embedding_version}")
        print(f"  Timestamp: {deployment_record['timestamp']}")
        print(f"  Commit: {deployment_record['commit']}")
        print(f"  File: {deployed_file}")
        return True
    
    except Exception as e:
        print(f"❌ Failed to write .deployed file: {e}")
        return False

def validate_versions(deployed_data: Dict) -> bool:
    """
    Validate that recorded versions are valid format.
    
    Args:
        deployed_data: Dictionary from .deployed file
    
    Returns:
        True if valid, False otherwise
    """
    import re
    
    for key in ["llm", "embedding"]:
        version = deployed_data.get(key)
        if not version:
            print(f"❌ Missing {key} version")
            return False
        
        if not re.match(r'^v\d+(\.\d+)*$', version):
            print(f"❌ Invalid {key} version format: {version}")
            return False
    
    return True

def main():
    """Main entry point."""
    print("=" * 60)
    print("TomeHub Deployment Version Recorder")
    print("=" * 60)
    
    # Record versions
    success = record_deployment_versions()
    
    if not success:
        print("\n❌ Failed to record deployment versions")
        sys.exit(1)
    
    # Validate the recorded file
    deployed_file = Path(__file__).parent.parent / "apps" / "backend" / ".deployed"
    try:
        with open(deployed_file) as f:
            deployed_data = json.load(f)
        
        if not validate_versions(deployed_data):
            print("\n❌ Validation failed")
            sys.exit(1)
        
        print("\n✓ Deployment versions recorded and validated successfully")
        print("\nNext deployment must use newer versions:")
        print(f"  LLM: > {deployed_data['llm']}")
        print(f"  Embedding: > {deployed_data['embedding']}")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ Error validating deployment file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
