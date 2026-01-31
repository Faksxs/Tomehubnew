"""
Debug script to verify app.routes includes flow routes
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

# Import the app
from app import app

print(f"\n>>> Total routes in app: {len(app.routes)}")
print("\n>>> All registered routes:")
for route in app.routes:
    if hasattr(route, "path"):
        methods = getattr(route, "methods", set())
        print(f"  {route.path} [{', '.join(methods)}]")
    else:
        print(f"  {route}")

# Check for /api/flow specifically
flow_routes = [r for r in app.routes if hasattr(r, "path") and "/api/flow" in r.path]
print(f"\n>>> Flow routes found: {len(flow_routes)}")
for r in flow_routes:
    print(f"  {r.path}")
