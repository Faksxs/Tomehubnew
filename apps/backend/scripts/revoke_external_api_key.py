import argparse
import json
import os
import sys


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager
from services.external_api_key_service import revoke_external_api_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Revoke a TomeHub external API key.")
    parser.add_argument("--key-id", type=int, default=None, help="Numeric key id")
    parser.add_argument("--key-prefix", default=None, help="Stored key prefix")
    args = parser.parse_args()

    try:
        DatabaseManager.init_pool()
        success = revoke_external_api_key(key_id=args.key_id, key_prefix=args.key_prefix)
        print(json.dumps({"success": success}, ensure_ascii=False, indent=2))
        return 0 if success else 1
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
