from typing import List, Dict, Any

def compute_rrf(rankings: List[List[str]], k=60) -> Dict[str, float]:
    """
    Computes Reciprocal Rank Fusion scores.
    Args:
        rankings: List of ranked lists (each list contains item IDs/Keys)
        k: Constant to dampen high ranks (default 60)
    Returns:
        Dictionary {item_key: rrf_score}
    """
    rrf_map = {}
    
    for rank_list in rankings:
        for rank, item_key in enumerate(rank_list):
            if item_key not in rrf_map:
                rrf_map[item_key] = 0.0
            rrf_map[item_key] += 1 / (k + rank + 1)
            
    return rrf_map
