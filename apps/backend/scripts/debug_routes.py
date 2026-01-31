
import sys
import os

# Create a path that includes the parent directory
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app import app

print("\n--- Registered Routes ---")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"{route.path} [{','.join(route.methods)}]")
    else:
        print(route)
print("-------------------------\n")
