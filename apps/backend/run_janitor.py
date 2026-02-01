
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.data_health_service import DataHealthService

if __name__ == "__main__":
    service = DataHealthService()
    print("Executing Health Service Cleanup...")
    results = service.cleanup_database()
    print(f"Cleanup Results: {results}")
