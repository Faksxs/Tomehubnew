
import os
import sys
import json
import time
import oracledb
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Setup paths based on file location
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

# Load env - ensure we find it
env_path = os.path.join(backend_dir, '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not found in .env")
    sys.exit(1)
    
genai.configure(api_key=api_key)

# Import the RAG function (Layer 3)
try:
    from services.search_service import generate_answer
except ImportError as e:
    print(f"Could not import generate_answer: {e}")
    print(f"sys.path is: {sys.path}")
    sys.exit(1)

def load_golden_dataset():
    path = os.path.join(backend_dir, 'data', 'golden_dataset.json')
    if not os.path.exists(path):
        print(f"Dataset not found at {path}")
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def evaluate_answer(question, generated_answer, reference_answer):
    """
    Uses Gemini as a Judge to score the answer.
    """
    prompt = f"""
    You are an impartial judge evaluating the quality of an AI-generated answer.
    
    Question: {question}
    
    Reference Answer (Ground Truth): {reference_answer}
    
    Generated Answer: {generated_answer}
    
    Task:
    1. Score the Answer from 1 to 5 (5 = Perfect match with ground truth).
    2. Check for Hallucination (Is there info contradiction?).
    
    Output JSON ONLY:
    {{
        "score": <int>,
        "reasoning": "<short explanation>",
        "faithfulness": "High" | "Medium" | "Low"
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        if not text:
             return {"score": 0, "reasoning": "Empty Judge Response", "faithfulness": "Unknown"}
        return json.loads(text)
    except Exception as e:
        print(f"Evaluation Error: {e}")
        return {"score": 0, "reasoning": f"Eval Failed: {e}", "faithfulness": "Unknown"}

def run_evaluation(params_uid):
    print(f"--- Starting RAG Evaluation (UID: {params_uid}) ---")
    dataset = load_golden_dataset()
    
    if not dataset:
        print("Dataset is empty or missing!")
        return
    
    results = []
    total_score = 0
    
    for item in dataset:
        q_id = item['id']
        question = item['question']
        ref_ans = item['reference_answer']
        
        print(f"\nEvaluate Q: {question}")
        
        start_time = time.time()
        full_response = "ERROR"
        
        try:
            # generate_answer returns (answer_str, sources_list)
            # We don't need sources for scoring, just the text
            answer_text, sources = generate_answer(question, params_uid)
            full_response = answer_text if answer_text else "No Answer Generated"
            
        except Exception as e:
            print(f"RAG Execution Failed: {e}")
            import traceback
            traceback.print_exc()
            
        duration = time.time() - start_time
        print(f" -> Generated in {duration:.2f}s")
        
        # 2. Grade
        print(" -> Judging...")
        grade = evaluate_answer(question, full_response, ref_ans)
        
        score = grade.get('score', 0)
        reasoning = grade.get('reasoning', 'No reasoning')
        faithfulness = grade.get('faithfulness', 'Unknown')
        
        print(f" -> Score: {score}/5 | Faithfulness: {faithfulness}")
        
        results.append({
            "id": q_id,
            "question": question,
            "generated": full_response,
            "score": score,
            "reasoning": reasoning,
            "duration": duration
        })
        total_score += score
        
    # Report
    avg_score = total_score / len(dataset) if dataset else 0
    print(f"\n=== FINAL REPORT ===")
    print(f"Average Score: {avg_score:.2f}/5")
    
    # Save Report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = os.path.join(backend_dir, 'reports', f'qa_report_{timestamp}.md')
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# QA Report - {timestamp}\n\n")
        f.write(f"**Average Score:** {avg_score:.2f}/5\n\n")
        f.write("| ID | Question | Score | Reasoning |\n")
        f.write("|---|---|---|---|\n")
        for r in results:
            # Escape pipes to avoid breaking table
            r_reason = r['reasoning'].replace('|', '-') if r['reasoning'] else "None"
            # Truncate reasoning if too long
            if len(r_reason) > 200: r_reason = r_reason[:197] + "..."
            
            f.write(f"| {r['id']} | {r['question']} | {r['score']} | {r_reason} |\n")
            
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    # FOUND via find_user.py: 'vpq1p0UzcCSLAh1d18WgZZWPBE63' (771 notes)
    DEFAULT_UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", default=DEFAULT_UID, help="Firebase UID of the user to test against")
    args = parser.parse_args()
    
    run_evaluation(args.uid)
