import os
import json
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

async def test_gemini():
    # Load .env
    load_dotenv(dotenv_path=".env")
    api_key = os.getenv("GEMINI_API_KEY")
    
    print(f"Testing Gemini with key: {api_key[:10]}...")
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = "Hello, are you online? Respond with 'YES' if you are."
        print(f"Sending prompt: {prompt}")
        
        response = model.generate_content(prompt)
        print(f"Response: {response.text}")
        
        if "YES" in response.text.upper():
            print("SUCCESS: Gemini API is online and working.")
        else:
            print(f"WARNING: Unexpected response: {response.text}")
            
    except Exception as e:
        print(f"ERROR: Gemini test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
