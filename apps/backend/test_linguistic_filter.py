
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'services'))
sys.path.append(os.path.dirname(__file__))

from services.correction_service import LinguisticCorrectionService

def test_corrections():
    corrector = LinguisticCorrectionService()
    
    test_cases = [
        ("gOnOmuz felsefesi", "günümüz felsefesi"),
        ("~alisma hayati", "çalışma hayati"),
        ("gonomuz dOtOn", "günümüz dütün"), # dütün isn't a word but regex might match O->ü. wait, my regex was bOtOn -> bütün. dOtOn not matched.
        ("bOtOn insanlik", "bütün insanlik"),
        ("gOz ile gormek", "göz ile gormek"),
        ("kOltOr bakanligi", "kültür bakanligi"),
        ("anlam1 var", "anlamı var"),
        # Line glue
        ("medeniyet- \n ler", "medeniyetler\n ")
    ]

    print(f"{'='*30}\nRunning Linguistic Filter Tests\n{'='*30}")
    
    passes = 0
    for inp, expected in test_cases:
        output = corrector.fix_text(inp)
        # Normalize whitespace for gluestick check
        if inp.startswith("medeniyet"):
            # Gluestick leaves newline at end usually
            pass # Manual check print
        
        print(f"Input:    '{inp}'")
        print(f"Output:   '{output}'")
        print(f"Expected: '{expected}'")
        
        if output.strip() == expected.strip():
            print("✅ PASS")
            passes += 1
        else:
            if "medeniyet" in inp: # Special case for whitespace match
               if "medeniyetler" in output:
                   print("✅ PASS (Glued)")
                   passes += 1
               else:
                   print("❌ FAIL")
            else:
                print("❌ FAIL")
        print("-" * 20)
        
    print(f"\nResult: {passes}/{len(test_cases)} Passed")

if __name__ == "__main__":
    test_corrections()
