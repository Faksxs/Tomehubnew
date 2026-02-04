
import time
import os
import sys
import io

# Handle encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOG_FILE = "backend_error.log" # Or server_final.log

def tail_logs():
    print(f"--- Tailing {LOG_FILE} ---")
    print("Waiting for new logs...")
    
    try:
        if not os.path.exists(LOG_FILE):
            print(f"File {LOG_FILE} not found yet.")
            return

        with open(LOG_FILE, "r", encoding="utf-8", errors='ignore') as f:
            # Go to the end
            f.seek(0, os.SEEK_END)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                print(line.strip())
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    tail_logs()
