# RAG Quality Guard Checklist

## Groundedness
1. Every key claim maps to at least one retrieved source.
2. No fabricated detail outside visible context.
3. Ambiguous claims are labeled as uncertain.

## Retrieval adequacy
1. Retrieved set covers user intent breadth.
2. High-signal sources are present in top results.
3. Missing concept neighborhoods are noted.

## Failure classification
1. Retrieval failure: weak or missing evidence.
2. Generation failure: evidence exists but answer misuses it.
3. Mixed failure: both retrieval and generation issues.

## Output format
1. Pass or fail.
2. Evidence gaps.
3. Corrective action and quick retest definition.
