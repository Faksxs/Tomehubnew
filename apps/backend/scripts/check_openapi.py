"""
Runtime route diagnostics - calls the running server to list routes
"""
import requests

BASE = "http://localhost:5000"

# Try OpenAPI
response = requests.get(f"{BASE}/openapi.json")
if response.ok:
    data = response.json()
    paths = data.get("paths", {})
    print(f"Found {len(paths)} paths in OpenAPI:")
    for path in sorted(paths.keys()):
        methods = list(paths[path].keys())
        print(f"  {path} [{', '.join(methods)}]")
else:
    print(f"OpenAPI fetch failed: {response.status_code}")
