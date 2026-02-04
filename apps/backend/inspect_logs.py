
import os
import sys
import io

# Handle encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def read_last_lines(filename, n=100):
    print(f"\n--- Last {n} lines of {filename} ---")
    if not os.path.exists(filename):
        print("File not found.")
        return

    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            print(f"--- Scanning logs for Startup ---")
            found = False
            for line in lines[-200:]:
                if "Startup" in line or "Uvicorn running" in line:
                     print(line.strip())
                     found = True
            if not found:
                print("No startup logs found in last 200 lines.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    read_last_lines(os.path.join(base, "server_final.log"), 100)
    read_last_lines(os.path.join(base, "backend_error.log"), 100)
