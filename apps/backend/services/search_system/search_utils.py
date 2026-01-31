from typing import List, Dict, Any, Optional

def compute_rrf(rankings: List[List[str]], k=60, weights: Optional[List[float]] = None) -> Dict[str, float]:
    """
    Computes Reciprocal Rank Fusion scores with optional weighting.
    
    Args:
        rankings: List of ranked lists (each list contains item IDs/Keys)
                  Expected order: [bm25_ranking, vector_ranking, graph_ranking]
        k: Constant to dampen high ranks (default 60)
        weights: Optional list of weights for each ranking.
                 Default: [0.5, 0.25, 0.25] (BM25 prioritized over Vector/Graph)
    Returns:
        Dictionary {item_key: rrf_score}
    """
    # Default weights: BM25 first (0.5), then Vector (0.25), then Graph (0.25)
    if weights is None:
        num_rankings = len(rankings)
        if num_rankings == 3:
            weights = [0.5, 0.25, 0.25]  # BM25, Vector, Graph
        else:
            weights = [1.0] * num_rankings  # Equal weights for other cases
    
    rrf_map = {}
    
    for i, rank_list in enumerate(rankings):
        weight = weights[i] if i < len(weights) else 1.0
        for rank, item_key in enumerate(rank_list):
            if item_key not in rrf_map:
                rrf_map[item_key] = 0.0
            rrf_map[item_key] += weight * (1 / (k + rank + 1))
            
    return rrf_map
