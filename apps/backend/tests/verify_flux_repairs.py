import re
import sys
import os

# Add project root to path
sys.path.append(r"c:\Users\aksoy\Desktop\yeni tomehub")
sys.path.append(r"c:\Users\aksoy\Desktop\yeni tomehub\apps\backend")

from apps.backend.services.flow_text_repair_service import FlowTextRepairService
from apps.backend.services.flow_service import _limit_flow_content

def test_repairs():
    print("Testing Flow Text Repairs...")
    service = FlowTextRepairService()
    
    # Test cases (Must be > 30 chars to bypass short-text skip)
    cases = [
        ("gOnOmuz sorunlari cok buyuktur ve cozulmelidir.", "günümüz sorunlari cok buyuktur ve cozulmelidir."),
        ("MAHUR BEST E bir romandir ve Ahmet Hamdi tarafindan yazilmistir.", "MAHUR BESTE bir romandir ve Ahmet Hamdi tarafindan yazilmistir."),
        ("Bu bir hayatinda... sonra geldi. Cumle devam ediyor.", "Bu bir hayatinda... sonra geldi. Cumle devam ediyor."), 
        ("This is a word-\n suffix case that should be fixed.", "This is a word-suffix case that should be fixed."), 
    ]
    
    for input_text, expected in cases:
        repaired = service.repair_for_flow_card(input_text, "PDF")
        # Note: repair doesn't do trimming, just text fix
        # For hyphenation, we expect "word-suffix" or "wordsuffix" depending on logic
        print(f"Input: '{input_text}'\nRepaired: '{repaired}'")

def test_trimming():
    print("\nTesting Flow Service Trimming...")
    # service = FlowService() -> Not needed for standalone function
    
    # Test cases for trimming
    cases = [
        ("...ve sonra geldi. Ahmet eve gitti.", "Ahmet eve gitti."),
        ("bunu dedi. Ancak simdi basliyoruz.", "Ancak simdi basliyoruz."),
        ("Normal cumle baslangici.", "Normal cumle baslangici."),
        ('"Quote starts are kept."', '"Quote starts are kept."'),
    ]
    
    for input_text, expected in cases:
        # We access the private method for testing logic
        try:
            trimmed = _limit_flow_content(input_text, 1000)
            print(f"Input: '{input_text}'\nTrimmed: '{trimmed}'\nPass: {trimmed == expected}")
        except Exception as e:
            print(f"Error testing '{input_text}': {e}")

if __name__ == "__main__":
    with open("verify_output.txt", "w") as f:
        sys.stdout = f
        test_repairs()
        test_trimming()
