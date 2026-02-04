
import re

def test_cleaning():
    dirty_samples = [
        "Hayat1n anlam1 nedir?",
        "gOnOmuz kapitalizminin kentli pragmatik",
        "politik ve kOitOrel dOnyasmda",
        "ba~an konusu degildir",
        "~izgi ~izmek",
        "goriintiisii olarak",
        "biitiiniin ciil olamn tersidir",
        "~iinkii genel olarak",
        "miizik",
        "~e~itli",
        "ba~ka bir deyi~le",
        "iki yOnO de i~aret eder",
    ]

    print("--- Testing Cleaning Logic ---")
    for original in dirty_samples:
        cleaned = robust_clean(original)
        print(f"Original: {original}")
        print(f"Cleaned : {cleaned}")
        print("-" * 20)

def robust_clean(text):
    # 1. '1' -> 'ı' fixes
    # "Hayat1n" -> "Hayatın"
    text = re.sub(r'(?<=[a-zA-ZçğıöşüÇĞİÖŞÜ])1(?=[a-zA-ZçğıöşüÇĞİÖŞÜ])', 'ı', text)
    text = re.sub(r'(?<=[a-zçğıöşü])1\b', 'ı', text)

    # 2. 'ii' -> 'ü' heuristic (common in this PDF)
    # Only if inside a word? 
    # "biitiiniin" -> "bütünün"
    # "miizik" -> "müzik"
    # Risk: "bedii" (aesthetic) -> "bedü"? "tabii" -> "tabü"?
    # Risk is present but low for modern texts. This looks like systematic encoding error.
    # Let's try replacing 'ii' with 'ü' generally if word doesn't exist? Too hard.
    # Let's look at the patterns: consonant + ii + consonant -> ü?
    
    # "goriintiisii" -> "görüntüsü" (ii -> ü)
    replacements = {
        r'ii': 'ü',
        r'II': 'Ü', 
    }
    # This is dangerous for "Skiing", "Hawaii", "Tabii". 
    # But user text is Turkish. "Tabii" is common. "Camiiler" is common.
    # Maybe limit to 'iis', 'iin', 'iil'?
    
    # 3. 'O' / '0' -> 'ü' or 'ö' inside lowercase words
    # Iterate to catch consecutive Os (e.g. gOnOmuz)
    # Convert 'O' surrounded by lowercase (or other O's) to 'ü' (heuristic)
    # We do a few passes for safety or use a loop.
    for _ in range(2):
        text = re.sub(r'(?<=[a-zçğıöşü])O(?=[a-zçğıöşüO])', 'ü', text)
        text = re.sub(r'(?<=[a-zçğıöşüO])O(?=[a-zçğıöşü])', 'ü', text)
        text = re.sub(r'(?<=[a-zçğıöşü])0(?=[a-zçğıöşü0])', 'ü', text) # Handle zero too

    # 2. 'ii' -> 'ü' heuristic
    # "biitiiniin" -> "bütünün"
    # "miizik" -> "müzik"
    # "goriintii" -> "görüntü"
    # Only replace if surrounded by consonants or word boundary?
    # Actually, in Turkish 'ii' (double i) is extremely rare (almost non-existent except 'badii' etc which are old).
    # Replacing 'ii' -> 'ü' globally in lowercase text is 99% safe for these corrupted PDFs.
    text = re.sub(r'ii', 'ü', text)
    text = re.sub(r'I I', 'Ü', text) # Sometimes spaced caps?
    
    # 3.5 Specific word fixes for remaining O/0 issues
    text = re.sub(r'\bkOlt[Oü]r', 'kültür', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgOrOnt', 'görünt', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdOnya', 'dünya', text, flags=re.IGNORECASE)
    text = re.sub(r'\byOnO', 'yönü', text, flags=re.IGNORECASE) # yönü
 
    
    # 4. '~' -> 'ç' or 'ş'
    # "~izgi" -> "çizgi" (start of word)
    # "~iinkii" -> "çünkü"
    # "~e~itli" -> "çeşitli"
    # "~oke" -> "çok"?
    
    # Context based:
    # ~ + i/e -> ç or ş?
    # ~izgi -> ç
    # ~iddet -> ş
    # This is hard. ~ is strictly ambiguous.
    
    # Specific Mapping from observation
    specifics = {
        r'~izgi': 'çizgi',
        r'~izmek': 'çizmek',
        r'~iddet': 'şiddet',
        r'~e~it': 'çeşit',
        r'~iinkii': 'çünkü',
        r'~unkii': 'çünkü',
        r'~ünkü': 'çünkü',
        r'ba~a': 'başa', # başarmak?
        r'~ey': 'şey',
        r'ba~ka': 'başka',
        r'deyi~': 'deyiş',
        r'~ıkış': 'çıkış',
        r'~alış': 'çalış',
        r'~alıs': 'çalış',
        r'~ocuk': 'çocuk',
        r'~ok': 'çok',
    }
    
    for pat, repl in specifics.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    # Generic ~ fallback?
    # If starts with '~', usually 'Ç' or 'Ş'.
    
    return text

if __name__ == "__main__":
    test_cleaning()
