
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from routes.flow_routes import router
    print(f"Router Prefix: {router.prefix}")
    print(f"Router Tags: {router.tags}")
    print(f"Routes Count: {len(router.routes)}")
    for r in router.routes:
        print(f" - {r.path} {r.methods}")
except Exception as e:
    print(f"Import Failed: {e}")
    import traceback
    traceback.print_exc()
