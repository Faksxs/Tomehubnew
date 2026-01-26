
# Re-ranking Prompts

RERANK_PROMPT_TEMPLATE = """
You are an expert Search Relevance Ranker.

Query: "{query}"

Task: Rank the following candidates based on their relevance to the query.
- Rate each candidate from 0.0 (irrelevant) to 1.0 (highly relevant).
- Consider semantic meaning, not just keyword overlap.
- Return ONLY a JSON list of objects: {{"index": <int>, "score": <float>}}.

Candidates:
{candidates_text}
"""
