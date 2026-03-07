# TomeHub RAG Eval Report

- Dataset: `golden_dataset`
- Generated: `2026-03-07 17:15 UTC`
- Cases: `24`
- Passed: `3`
- Pass rate: `12.5%`
- Average score: `2.29/5`
- Average latency: `32.52s`

## Classification Counts

- `generation`: 21
- `pass`: 3

## Case Results

| ID | Score | Faithfulness | Mode | Class | Sources | Notes |
|---|---:|---|---|---|---:|---|
| q1 | 0 | Unknown | QUOTE | generation | 12 | low_score |
| q2 | 5 | High | QUOTE | pass | 12 | pass |
| q3 | 0 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q4 | 1 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q5 | 5 | High | QUOTE | pass | 12 | pass |
| q6 | 2 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q7 | 2 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q8 | 0 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q9 | 2 | Low | HYBRID | generation | 12 | low_score, low_faithfulness, mode_mismatch:HYBRID, missing_required_phrase:iyiyi kötüden ayırma yeteneğinin özel bir adı vardır |
| q10 | 4 | High | HYBRID | generation | 12 | missing_required_phrase:vicdan için iki teori var, missing_synthesis_signal:vicdan azabı |
| q11 | 2 | Low | QUOTE | generation | 12 | low_score, low_faithfulness, missing_required_phrase:ilahi bir ses |
| q12 | 3 | High | QUOTE | generation | 12 | low_score, mode_mismatch:QUOTE, missing_required_phrase:diğer insanları anlamak mümkün değildir |
| q13 | 4 | High | QUOTE | generation | 12 | mode_mismatch:QUOTE, missing_required_phrase:kişisel vicdanla sınırlı kalmalıdır |
| q14 | 1 | Low | HYBRID | generation | 12 | low_score, low_faithfulness, missing_required_phrase:Ayrılmak ne tuhaf |
| q15 | 5 | High | QUOTE | generation | 12 | mode_mismatch:QUOTE, missing_synthesis_signal:Toplumsal yasalardan ayrı tutulmalıdır |
| q16 | 3 | Medium | QUOTE | generation | 12 | low_score, mode_mismatch:QUOTE, missing_required_phrase:iyiyi kötüden ayırma yeteneğinin özel bir adı vardır, missing_synthesis_signal:kişisel vicdanla sınırlı kalmalıdır |
| q17 | 1 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q18 | 0 | Low | QUOTE | generation | 12 | low_score, low_faithfulness, missing_required_phrase:ırmağa iki kez girilmez |
| q19 | 1 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q20 | 1 | Low | QUOTE | generation | 12 | low_score, low_faithfulness, missing_required_phrase:yok edilemez |
| q21 | 1 | Low | QUOTE | generation | 12 | low_score, low_faithfulness |
| q22 | 5 | High | QUOTE | pass | 12 | pass |
| q23 | 3 | Medium | QUOTE | generation | 12 | low_score |
| q24 | 4 | High | HYBRID | generation | 12 | missing_required_phrase:iyiyi kötüden ayırma yeteneğinin özel bir adı vardır, missing_synthesis_signal:vicdan için iki teori var |
