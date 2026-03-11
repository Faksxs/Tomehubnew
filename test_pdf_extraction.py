import sys
import os

# Add apps/backend to path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps', 'backend'))
sys.path.append(backend_path)

from services.pdf_service import extract_pdf_content

def main():
    pdf_path = "Ahmet Hamdi Tanpınar_Mahur Beste_Dergah Yayınları.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at {pdf_path}")
        return

    print(f"Testing extraction for: {pdf_path}")
    
    # We load env here if needed, but config.py handles defaults
    # For testing, ensure OPENDATALOADER_URL is correctly picked up
    try:
        from config import settings
        print(f"Using OPENDATALOADER_URL: {settings.OPENDATALOADER_URL}")
    except Exception:
        pass

    chunks = extract_pdf_content(pdf_path)

    if chunks:
        print(f"\n[SUCCESS] Extracted {len(chunks)} chunks.")
        print("\n--- First 3 chunks ---")
        for chunk in chunks[:3]:
            # Truncate text for display if it's too long
            text = chunk.get('text', '')
            chunk_copy = dict(chunk)
            chunk_copy['text'] = text[:100] + "..." if len(text) > 100 else text
            print(chunk_copy)
    # If the standard pdf_service failed, let's do a direct verbose call here to see what happened
    import requests
    from config import settings
    odl_url = getattr(settings, 'OPENDATALOADER_URL', 'http://158.101.213.120:5002').rstrip('/')
    api_endpoint = f"{odl_url}/v1/convert/file"
    print(f"\n--- VERBOSE DIAGNOSTIC ---")
    print(f"Direct POST to {api_endpoint}...")
    try:
        with open(pdf_path, 'rb') as f:
            resp = requests.post(api_endpoint, files={'files': (os.path.basename(pdf_path), f, 'application/pdf')}, timeout=10)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"JSON Keys: {list(data.keys())}")
            # If there's a nested docling structure, it might be in 'document'
            if 'document' in data and isinstance(data['document'], dict):
                print(f"Document Keys: {list(data['document'].keys())}")
    except Exception as e:
        print(f"Direct call failed (expected if timeout is short): {e}")

if __name__ == "__main__":
    main()
