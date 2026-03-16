
import os
import json
import urllib.request
import urllib.parse
import time

# Zero-dependency .env parser
def load_env_manual(filepath):
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
    return env_vars

# Helper for simple GET/POST with urllib
def http_call(url, headers=None, data=None, method="GET", timeout=12):
    actual_headers = {
        "User-Agent": "Mozilla/5.0 (Tomehub Diagnostic)",
        "Accept": "*/*"
    }
    if headers: actual_headers.update(headers)
    req = urllib.request.Request(url, headers=actual_headers, method=method)
    if data:
        if isinstance(data, dict):
            req.data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        else:
            req.data = data
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try: body = e.read().decode("utf-8")
        except: body = str(e)
        return e.code, body
    except Exception as e:
        return 0, str(e)

def test_api(name, url, headers=None, data=None, method="GET"):
    print(f"Testing {name:<18}...", end=" ", flush=True)
    status, body = http_call(url, headers=headers, data=data, method=method)
    res = "OK" if 200 <= status < 300 else f"FAIL({status})"
    print(res)
    # Return detail if failed
    return res if res == "OK" else f"{res} - {body[:50]}"

def run_all():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env = load_env_manual(env_path)
    embedding_model = (env.get("EMBEDDING_MODEL_NAME") or "gemini-embedding-2-preview").strip()
    
    print(f"\n--- Tomehub Comprehensive API Diagnostic (Full Suite) ---")
    print(f"Loaded {len(env)} keys from .env")
    
    results = {}
    
    # 1. CORE AI
    results["NVIDIA"] = test_api("NVIDIA", "https://integrate.api.nvidia.com/v1/chat/completions", 
                                 {"Authorization": f"Bearer {env.get('NVIDIA_API_KEY')}"}, 
                                 {"model": env.get("LLM_EXPLORER_PRIMARY_MODEL", "qwen/qwen3.5-122b-a10b"), 
                                  "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}, "POST")
    
    results["Gemini"] = test_api("Gemini", f"https://generativelanguage.googleapis.com/v1beta/models/{embedding_model}:embedContent?key={env.get('GEMINI_API_KEY')}", 
                                 None, {"content": {"parts": [{"text": "test"}]}}, "POST")
    
    # 2. BOOKS & LIBRARIES
    results["OpenLibrary"] = test_api("Open Library", "https://openlibrary.org/search.json?q=test&limit=1")
    results["BigBookAPI"] = test_api("Big Book API", f"https://api.bigbookapi.com/search-books?query=ai&api-key={env.get('BIG_BOOK_API_KEY')}")
    results["Gutendex"] = test_api("Gutendex", "https://gutendex.com/books/?search=test")
    results["InternetArchive"] = test_api("Internet Archive", "https://archive.org/advancedsearch.php?q=test&output=json&rows=1")
    results["PoetryDB"] = test_api("PoetryDB", "https://poetrydb.org/title/test")

    # 3. RESEARCH & ACADEMIC
    results["OpenAlex"] = test_api("OpenAlex", f"https://api.openalex.org/works?search=ai&mailto={env.get('OPENALEX_EMAIL', 'test@test.com')}")
    results["Crossref"] = test_api("Crossref", f"https://api.crossref.org/works?query=test&rows=1")
    results["SemanticScholar"] = test_api("Semantic Scholar", f"https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1", {"x-api-key": env.get('SEMANTIC_SCHOLAR_API_KEY')})
    results["arXiv"] = test_api("arXiv", "https://export.arxiv.org/api/query?search_query=all:test&max_results=1")
    results["SHARE"] = test_api("SHARE", "https://share.osf.io/api/v2/search/creativeworks/?q=test&size=1")
    
    # 4. CULTURAL & ARTS
    results["Europeana"] = test_api("Europeana", f"https://api.europeana.eu/record/v2/search.json?query=test&wskey={env.get('EUROPEANA_API_KEY')}")
    results["ArtSearchAPI"] = test_api("Art Search (AIC)", "https://api.artic.edu/api/v1/artworks/search?q=test&limit=1")
    
    # 5. LANGUAGE & DICTIONARY
    rapid_key = env.get("WORDS_API_KEY") or env.get("LINGUA_ROBOT_API_KEY")
    results["WordsAPI"] = test_api("Words API", "https://wordsapiv1.p.rapidapi.com/words/test", {"x-rapidapi-key": rapid_key, "x-rapidapi-host": "wordsapiv1.p.rapidapi.com"})
    results["LinguaRobot"] = test_api("Lingua Robot", "https://lingua-robot.p.rapidapi.com/language/v1/entries/en/test", {"x-rapidapi-key": rapid_key, "x-rapidapi-host": "lingua-robot.p.rapidapi.com"})

    # 6. RELIGIOUS
    results["QuranFoundation"] = test_api("Quran Foundation", "https://api.quran.com/api/v4/chapters")
    # Using production URL for Diyanet
    results["Diyanet"] = test_api("Diyanet Quran", "https://acikkaynakkuran.diyanet.gov.tr/api/v1/surah", {"Authorization": f"Bearer {env.get('DIYANET_QURAN_API_KEY')}"})
    results["HadeethEnc"] = test_api("HadeethEnc", "https://hadeethenc.com/api/v1/categories/list/?language=tr")
    # 7. MEDIA
    results["TMDB"] = test_api("TMDB", f"https://api.themoviedb.org/3/search/movie?query=Inception&api_key={env.get('TMDB_API_KEY')}")

    print("\n" + "="*60)
    print("   FINAL LIVE API STATUS SUMMARY")
    print("="*60)
    for k, v in results.items():
        print(f"{k:<20}: {v}")

if __name__ == "__main__":
    run_all()
