# -*- coding: utf-8 -*-
"""
TomeHub Feature Test Suite
Tests all 4 major enhancements:
1. Work AI + Judge AI Pattern
2. Rubric-Based Feedback System
3. GraphStrategy Integration
4. Network Scoring System
"""

import os
import sys
import asyncio

# Set feature flag
os.environ["ENABLE_DUAL_AI"] = "true"

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_feature_1_work_judge_pattern():
    """Test Work AI + Judge AI Pattern"""
    print("\n" + "="*60)
    print("FEATURE 1: Work AI + Judge AI Pattern")
    print("="*60)
    
    try:
        from services.work_ai_service import generate_work_ai_answer
        from services.judge_ai_service import evaluate_answer
        from services.dual_ai_orchestrator import generate_evaluated_answer
        print("✓ All modules imported successfully")
        
        # Check function signatures
        import inspect
        sig = inspect.signature(generate_evaluated_answer)
        params = list(sig.parameters.keys())
        assert 'question' in params, "Missing 'question' param"
        assert 'chunks' in params, "Missing 'chunks' param"
        assert 'network_status' in params, "Missing 'network_status' param"
        print("✓ Orchestrator signature verified (includes network_status)")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_feature_2_rubric_system():
    """Test Rubric-Based Feedback System"""
    print("\n" + "="*60)
    print("FEATURE 2: Rubric-Based Feedback System")
    print("="*60)
    
    try:
        from services.rubric import (
            DEFAULT_RUBRIC, 
            DIRECT_RUBRIC, 
            SYNTHESIS_RUBRIC,
            get_rubric_for_question,
            get_hints_for_failures
        )
        print("✓ Rubric module imported")
        
        # Test rubric selection
        rubric = get_rubric_for_question("Vicdan nedir?", "DIRECT")
        assert 'source_accuracy' in rubric, "Missing source_accuracy criterion"
        print(f"✓ DIRECT rubric has {len(rubric)} criteria")
        
        # Test hint generation
        failures = [{'criterion': 'source_accuracy', 'score': 0.3}]
        hints = get_hints_for_failures(failures)
        assert len(hints) > 0, "No hints generated"
        print(f"✓ Hint generation working: '{hints[0][:50]}...'")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_feature_3_graph_integration():
    """Test GraphStrategy Integration"""
    print("\n" + "="*60)
    print("FEATURE 3: GraphStrategy Integration")
    print("="*60)
    
    try:
        from services.search_service import get_rag_context, get_graph_candidates
        print("✓ Search service imported")
        
        # Check that get_rag_context includes graph logic
        import inspect
        source = inspect.getsource(get_rag_context)
        
        assert 'run_graph_search' in source or 'get_graph_candidates' in source, "Graph search not in get_rag_context"
        print("✓ Graph search is integrated in get_rag_context")
        
        assert 'ThreadPoolExecutor' in source, "Parallel execution not found"
        print("✓ Parallel execution (ThreadPoolExecutor) verified")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_feature_4_network_scoring():
    """Test Network Scoring System"""
    print("\n" + "="*60)
    print("FEATURE 4: Network Scoring System")
    print("="*60)
    
    try:
        from services.network_classifier import classify_network_status
        print("✓ Network classifier imported")
        
        # Test with empty chunks (OUT_OF_NETWORK)
        result = classify_network_status("Test query", [])
        assert result['status'] == 'OUT_OF_NETWORK', f"Expected OUT_OF_NETWORK, got {result['status']}"
        print(f"✓ Empty chunks → {result['status']} (correct)")
        
        # Test with mock chunks (should be IN_NETWORK or HYBRID)
        mock_chunks = [
            {'content_chunk': 'Vicdan insanın iç sesidir.', 'answerability_score': 5},
            {'content_chunk': 'Vicdan değişmez bir ölçüdür.', 'answerability_score': 4},
        ]
        result2 = classify_network_status("Vicdan nedir?", mock_chunks)
        print(f"✓ With chunks → {result2['status']} (confidence: {result2['confidence']:.2f})")
        
        # Verify prompt integration
        from services.epistemic_service import get_prompt_for_mode
        import inspect
        sig = inspect.signature(get_prompt_for_mode)
        assert 'network_status' in sig.parameters, "network_status not in get_prompt_for_mode"
        print("✓ network_status integrated into prompt generation")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_feature_5_smart_orchestration():
    """Test Smart Orchestration Logic (Fast Track)"""
    print("\n" + "="*60)
    print("FEATURE 5: Smart Orchestration (Optimization)")
    print("="*60)
    
    try:
        from services.dual_ai_orchestrator import should_trigger_audit
        
        # Case 1: High Confidence + Direct + In-Network -> FAST TRACK
        audit, reason = should_trigger_audit(6.0, "DIRECT", "IN_NETWORK")
        assert audit is False, f"Should Skip Judge (Fast Track). Got: {audit} ({reason})"
        print(f"✓ Fast Track works: {reason}")
        
        # Case 2: Low Confidence -> AUDIT
        audit, reason = should_trigger_audit(3.5, "DIRECT", "IN_NETWORK")
        assert audit is True, f"Should Trigger Audit (Low Conf). Got: {audit} ({reason})"
        print(f"✓ Low Confidence trigger works: {reason}")
        
        # Case 3: Out of Network -> AUDIT
        audit, reason = should_trigger_audit(7.0, "DIRECT", "OUT_OF_NETWORK")
        assert audit is True, f"Should Trigger Audit (Out of Net). Got: {audit} ({reason})"
        print(f"✓ Out of Network trigger works: {reason}")
        
        # Case 4: Complex Intent -> AUDIT
        audit, reason = should_trigger_audit(6.0, "COMPARATIVE", "IN_NETWORK")
        assert audit is True, f"Should Trigger Audit (Complex). Got: {audit} ({reason})"
        print(f"✓ Complex Intent trigger works: {reason}")

        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def run_all_tests():
    print("\n" + "#"*60)
    print("# TomeHub Enhancement Test Suite")
    print("#"*60)
    
    results = {
        "Feature 1: Work+Judge AI": test_feature_1_work_judge_pattern(),
        "Feature 2: Rubric System": test_feature_2_rubric_system(),
        "Feature 3: Graph Integration": test_feature_3_graph_integration(),
        "Feature 4: Network Scoring": test_feature_4_network_scoring(),
        "Feature 5: Smart Orchestration": test_feature_5_smart_orchestration(),
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} | {name}")
        if not passed:
            all_passed = False
    
    print("="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️ SOME TESTS FAILED - Review output above")
    
    return all_passed

if __name__ == "__main__":
    run_all_tests()
