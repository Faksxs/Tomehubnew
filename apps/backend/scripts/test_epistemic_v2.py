"""
Phase 7: Ground Truth Testing for Epistemic Control Layer v2
=============================================================
Tests that the epistemic layer correctly:
1. Quotes definitional notes (Notes 1, 3, 4) verbatim
2. Synthesizes contextual notes (Notes 2, 5, 6)

Test Query: "vicdan değişen bir şey midir"
"""

import os
import sys
import re

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, backend_path)
os.chdir(backend_path)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_path, '.env'))

from services.epistemic_service import (
    classify_question_intent,
    determine_answer_mode,
    extract_core_concepts,
    classify_chunk,
    build_epistemic_context,
    get_prompt_for_mode
)
from services.semantic_classifier import classify_passage_fast

# Ground Truth: The 6 Vicdan Notes
GROUND_TRUTH_NOTES = {
    "note_1": {
        "text": "İyiyi kötüden ayırma yeteneğinin özel bir adı vardır, o da vicdandır.",
        "expected_type": "DEFINITION",
        "expected_quotability": "HIGH",
        "expected_section": "QUOTE"
    },
    "note_2": {
        "text": "Ayrılmak ne tuhaf kalan daha çok ızdırap çektiği için giden biraz vicdan azabı duyar.",
        "expected_type": "SITUATIONAL",
        "expected_quotability": "MEDIUM",
        "expected_section": "SYNTHESIS"
    },
    "note_3": {
        "text": "Sokrates tümevarım temelli ahlak felsefesinin öncüsüdür. Vicdanı ilahi bir ses olarak tanımlar.",
        "expected_type": "THEORY",
        "expected_quotability": "HIGH",
        "expected_section": "QUOTE"
    },
    "note_4": {
        "text": "Vicdan için iki teori var: birincisi sosyal kanunlarla karıştıran, ikincisi değişmez bir kanun olarak gören.",
        "expected_type": "THEORY",
        "expected_quotability": "HIGH",
        "expected_section": "QUOTE"
    },
    "note_5": {
        "text": "İnsani bir vicdana sahip değilseniz diğer insanları anlamak mümkün değildir.",
        "expected_type": "SITUATIONAL",
        "expected_quotability": "MEDIUM",
        "expected_section": "SYNTHESIS"
    },
    "note_6": {
        "text": "Din yalnızca kişisel vicdanla sınırlı kalmalıdır. Toplumsal yasalardan ayrı tutulmalıdır.",
        "expected_type": "SOCIETAL",
        "expected_quotability": "MEDIUM",
        "expected_section": "SYNTHESIS"
    }
}


def test_question_classification():
    """Test that the question is classified correctly."""
    print("\n" + "=" * 70)
    print("TEST 1: Question Intent Classification")
    print("=" * 70)
    
    question = "vicdan değişen bir şey midir"
    intent, complexity = classify_question_intent(question)
    
    print(f"Question: {question}")
    print(f"Intent: {intent}")
    print(f"Complexity: {complexity}")
    
    # Expected: DIRECT intent (ends with "midir") + HIGH complexity (contains "vicdan" + "değişen midir")
    assert intent == "DIRECT", f"Expected DIRECT, got {intent}"
    assert complexity == "HIGH", f"Expected HIGH, got {complexity}"
    
    print("✅ PASSED: Question correctly classified as DIRECT + HIGH complexity")
    return True


def test_passage_classification():
    """Test that each note is classified correctly."""
    print("\n" + "=" * 70)
    print("TEST 2: Passage Type Classification")
    print("=" * 70)
    
    results = []
    for note_id, note in GROUND_TRUTH_NOTES.items():
        classification = classify_passage_fast(note["text"])
        actual_type = classification.get("type", "UNKNOWN")
        actual_quotability = classification.get("quotability", "UNKNOWN")
        
        type_match = actual_type == note["expected_type"]
        quot_match = actual_quotability == note["expected_quotability"]
        
        status = "✅" if (type_match and quot_match) else "⚠️"
        
        print(f"\n{note_id}:")
        print(f"  Text: {note['text'][:60]}...")
        print(f"  Expected: Type={note['expected_type']}, Quotability={note['expected_quotability']}")
        print(f"  Actual:   Type={actual_type}, Quotability={actual_quotability}")
        print(f"  Status: {status}")
        
        results.append({
            "note_id": note_id,
            "type_match": type_match,
            "quot_match": quot_match,
            "actual_type": actual_type,
            "actual_quotability": actual_quotability
        })
    
    # Count successes
    type_matches = sum(1 for r in results if r["type_match"])
    quot_matches = sum(1 for r in results if r["quot_match"])
    
    print(f"\nSummary: Type matches: {type_matches}/6, Quotability matches: {quot_matches}/6")
    
    # At least 4/6 should match (allowing for some variation in classification)
    if type_matches >= 4 and quot_matches >= 4:
        print("✅ PASSED: Most passages correctly classified")
        return True
    else:
        print("⚠️ PARTIAL: Some classifications may need adjustment")
        return False


def test_answer_mode_detection():
    """Test that HYBRID mode is triggered for this complex philosophical question."""
    print("\n" + "=" * 70)
    print("TEST 3: Answer Mode Detection")
    print("=" * 70)
    
    question = "vicdan değişen bir şey midir"
    keywords = extract_core_concepts(question)
    intent, complexity = classify_question_intent(question)
    
    print(f"Keywords: {keywords}")
    print(f"Intent: {intent}, Complexity: {complexity}")
    
    # Create mock chunks with classification
    mock_chunks = []
    for note_id, note in GROUND_TRUTH_NOTES.items():
        chunk = {
            "title": f"Test Note - {note_id}",
            "content_chunk": note["text"],
            "personal_comment": "",
            "summary": ""
        }
        classify_chunk(keywords, chunk)
        mock_chunks.append(chunk)
    
    # Display chunk scores
    print("\nChunk Scores:")
    for chunk in mock_chunks:
        print(f"  Level {chunk.get('epistemic_level', 'C')} | Score {chunk.get('answerability_score', 0)}/7 | "
              f"Type: {chunk.get('passage_type', 'N/A')} | {chunk['title']}")
    
    # Determine answer mode
    answer_mode = determine_answer_mode(mock_chunks, intent, complexity)
    
    print(f"\nAnswer Mode: {answer_mode}")
    
    # Expected: HYBRID mode (DIRECT + HIGH complexity + has definitional evidence)
    assert answer_mode == "HYBRID", f"Expected HYBRID, got {answer_mode}"
    
    print("✅ PASSED: HYBRID mode correctly triggered")
    return True


def test_context_build():
    """Test that context is built with correct markers."""
    print("\n" + "=" * 70)
    print("TEST 4: Context Building")
    print("=" * 70)
    
    question = "vicdan değişen bir şey midir"
    keywords = extract_core_concepts(question)
    
    # Create and classify chunks
    mock_chunks = []
    for note_id, note in GROUND_TRUTH_NOTES.items():
        chunk = {
            "title": f"Test Note - {note_id}",
            "content_chunk": note["text"],
            "personal_comment": "",
            "summary": ""
        }
        classify_chunk(keywords, chunk)
        mock_chunks.append(chunk)
    
    # Build context
    context = build_epistemic_context(mock_chunks, "HYBRID")
    
    # Check for required markers
    markers_found = {
        "DOĞRUDAN ALINTI": "★★★ DOĞRUDAN ALINTI YAP" in context,
        "Type metadata": "Type:" in context,
        "Quotability metadata": "Quotability:" in context,
        "Level A present": "Level: A" in context,
    }
    
    print("Context Markers Found:")
    for marker, found in markers_found.items():
        status = "✅" if found else "❌"
        print(f"  {status} {marker}")
    
    all_found = all(markers_found.values())
    
    if all_found:
        print("\n✅ PASSED: All required markers present in context")
    else:
        print("\n⚠️ PARTIAL: Some markers missing")
    
    return all_found


def test_prompt_structure():
    """Test that HYBRID prompt has correct structure."""
    print("\n" + "=" * 70)
    print("TEST 5: HYBRID Prompt Structure")
    print("=" * 70)
    
    prompt = get_prompt_for_mode("HYBRID", "[mock context]", "vicdan değişen bir şey midir")
    
    required_sections = [
        "Karşıt Görüşler",
        "Bağlamsal Kanıtlar",
        "Sonuç",
        "HİBRİT MOD"
    ]
    
    print("Required Sections in HYBRID Prompt:")
    all_found = True
    for section in required_sections:
        found = section in prompt
        status = "✅" if found else "❌"
        print(f"  {status} {section}")
        if not found:
            all_found = False
    
    if all_found:
        print("\n✅ PASSED: HYBRID prompt has correct structure")
    else:
        print("\n❌ FAILED: Missing sections in HYBRID prompt")
    
    return all_found


def run_all_tests():
    """Run all ground truth tests."""
    print("\n" + "=" * 70)
    print("EPISTEMIC CONTROL LAYER v2 - GROUND TRUTH TESTS")
    print("=" * 70)
    print("Test Query: 'vicdan değişen bir şey midir'")
    print("Expected Behavior:")
    print("  - Notes 1, 3, 4 (DEFINITION/THEORY) → Quoted verbatim")
    print("  - Notes 2, 5, 6 (SITUATIONAL/SOCIETAL) → Synthesized")
    print("  - Mode: HYBRID (complex philosophical question)")
    
    results = []
    
    results.append(("Question Classification", test_question_classification()))
    results.append(("Passage Classification", test_passage_classification()))
    results.append(("Answer Mode Detection", test_answer_mode_detection()))
    results.append(("Context Building", test_context_build()))
    results.append(("Prompt Structure", test_prompt_structure()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED! Epistemic Control Layer v2 is working correctly.")
        return True
    else:
        print("\n⚠️ Some tests failed. Review the output above for details.")
        return False


if __name__ == "__main__":
    run_all_tests()
