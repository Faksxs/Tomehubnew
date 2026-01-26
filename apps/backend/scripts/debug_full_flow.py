
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.epistemic_service import (
    classify_chunk, 
    determine_answer_mode, 
    classify_question_intent,
    extract_core_concepts
)

def debug_full_flow():
    print("DEBUG: Simulating Full Epistemic Flow...\n")
    
    question = "vicdan degisen bir sey midir"
    
    # 1. Intent Classification
    intent, complexity = classify_question_intent(question)
    print(f"Question: {question}")
    print(f"Intent: {intent}, Complexity: {complexity}")
    
    # 2. Extract Keywords
    keywords = extract_core_concepts(question)
    print(f"Keywords: {keywords}\n")
    
    # 3. Simulate Chunks (Exact text from screenshot)
    chunks = [
        {
            "title": "Karilar Kogusu",
            "content_chunk": "Yiğidi kılıç kesmez bir kötü söz öldürür... vicdan azabı..."
        },
        {
            "title": "Düşüş",
            "content_chunk": "Yaşamımı değiştirmedim kendimi sevmeye başkalarını kullanmaya devam ediyorum ancak hatalarımın itirafı daha hafiflemiş olarak yeniden başlamama önce doğamın sonra tatlı bir pişmanlığın keyfin sürerek iki kez zevk almama izin veriyor"
        },
        {
             "title": "Felsefenin Tesellisi",
             "content_chunk": "Gerçek dostlar bizi toplumsal yaşamın sahte ölçütlerine göre değerlendirmezler onların asıl ilgilendikleri şey bizim kendi benliğimizdir"
        },
        {
            "title": "Binboğalar Efsanesi",
            "content_chunk": "Para eder mi Müslüm diye sordu. Allah bizi bırakmadı mı? Bizi bırakıp dağlardan koca kentlere inmedi mi? Bizde Allahın gittiği indiği yere inmeliyiz"
        }
    ]
    
    print("--- Classifying Chunks ---")
    matches = 0
    for i, c in enumerate(chunks):
        level = classify_chunk(keywords, c)
        score = c.get('answerability_score')
        features = c.get('epistemic_features')
        
        print(f"Chunk {i+1} ({c['title']}):")
        print(f"  Level: {level}")
        print(f"  Score: {score}")
        print(f"  Features: {features}")
        
        if score >= 1:
            matches += 1
            
    print(f"\nTotal Matches (Score >= 1): {matches}")
    
    # 4. Determine Answer Mode
    mode = determine_answer_mode(chunks, intent, complexity)
    print(f"\nFinal Answer Mode: {mode}")

if __name__ == "__main__":
    debug_full_flow()
