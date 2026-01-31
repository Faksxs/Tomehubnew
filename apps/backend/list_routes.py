import sys
import os
sys.path.insert(0, 'c:\\Users\\aksoy\\Desktop\\yeni tomehub\\apps\\backend')

from app import app

print("=" * 80)
print("Route List:")
print("=" * 80)

for route in app.routes:
    # Use getattr to safely access attributes
    path = getattr(route, 'path', None)
    name = getattr(route, 'name', None)
    methods = getattr(route, 'methods', None)
    print(f"{path} | {methods} | {name}")
