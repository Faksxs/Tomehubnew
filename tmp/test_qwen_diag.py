import os
import sys
import json
import urllib.request
import urllib.error

# Add backend dir to path
backend_dir = r"c:\Users\aksoy\Desktop\yeni tomehub\apps\backend"
sys.path.insert(0, backend_dir)

from config import settings

def test_qwen():
    print(f"Testing Qwen at {settings.NVIDIA_BASE_URL}...")
    if not settings.NVIDIA_API_KEY:
        print("Error: NVIDIA_API_KEY not set")
        return

def test_qwen():
    print(f"Testing Qwen at {settings.NVIDIA_BASE_URL}...")
    payload = {
        "model": "qwen/qwen3-next-80b-a3b-instruct",
        "messages": [{"role": "user", "content": "Hello, are you there? Response with YES."}],
        "stream": False,
        "max_tokens": 10
    }
    
    request_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{settings.NVIDIA_BASE_URL}/v1/chat/completions",
        data=request_data,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            print("Response success!")
            print(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP Error {e.code}: {body}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_qwen()
