import argparse
import json
import os
import sys


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager
from services.external_api_key_service import create_external_api_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a TomeHub external API key.")
    parser.add_argument("--owner-uid", required=True, help="Firebase UID that owns the key")
    parser.add_argument("--label", required=True, help="Human-readable label for the key")
    parser.add_argument(
        "--scopes",
        default="search:read",
        help="Comma-separated scopes. Example: search:read,notes:read_private",
    )
    parser.add_argument(
        "--expires-at",
        default=None,
        help="Optional ISO timestamp, e.g. 2026-06-01T00:00:00+00:00",
    )
    args = parser.parse_args()

    scopes = [part.strip() for part in str(args.scopes or "").split(",") if part.strip()]

    try:
        DatabaseManager.init_pool()
        payload = create_external_api_key(
            owner_firebase_uid=args.owner_uid,
            label=args.label,
            scopes=scopes,
            expires_at_iso=args.expires_at,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
