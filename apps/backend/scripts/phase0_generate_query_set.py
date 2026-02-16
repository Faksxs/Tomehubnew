#!/usr/bin/env python3
"""
Generate Phase-0 baseline query set (120 queries).

Output:
- apps/backend/data/phase0_query_set.json
"""

import json
from pathlib import Path


CONCEPTS = [
    "ahlak",
    "etik",
    "vicdan",
    "adalet",
    "ozgurluk",
    "sorumluluk",
    "erdem",
    "hakikat",
    "irade",
    "bilgelik",
    "toplum",
    "devlet",
    "hukuk",
    "esitlik",
    "kimlik",
    "anlam",
    "umut",
    "kaygi",
    "ozne",
    "diyalog",
]

ANALYTIC_TERMS = [
    "zaman",
    "adalet",
    "ahlak",
    "insan",
    "toplum",
    "vicdan",
    "ozgurluk",
    "hakikat",
    "erdem",
    "sorumluluk",
    "kimlik",
    "anlam",
    "umut",
    "kaygi",
    "irade",
    "hukuk",
    "esitlik",
    "dusunce",
    "bilgi",
    "deger",
]


def build_queries():
    rows = []

    # 1) DIRECT (20)
    direct_templates = [
        "{a} nedir?",
        "{a} ne demek?",
        "{a} kavramini kisa tanimlar misin?",
        "{a} ile ilgili temel tanim nedir?",
    ]
    for i, a in enumerate(CONCEPTS):
        t = direct_templates[i % len(direct_templates)]
        rows.append(
            {
                "id": "",
                "category": "DIRECT",
                "query": t.format(a=a),
                "expected_terms": [a],
            }
        )

    # 2) COMPARATIVE (20)
    comparative_templates = [
        "{a} ile {b} arasindaki fark nedir?",
        "{a} ve {b} hangi acidan ayrisir?",
        "{a} ile {b} arasinda benzerlik ve farklari acikla.",
        "{a} mi yoksa {b} mi daha temel bir kavramdir?",
    ]
    for i, a in enumerate(CONCEPTS):
        b = CONCEPTS[(i + 3) % len(CONCEPTS)]
        t = comparative_templates[i % len(comparative_templates)]
        rows.append(
            {
                "id": "",
                "category": "COMPARATIVE",
                "query": t.format(a=a, b=b),
                "expected_terms": [a, b],
            }
        )

    # 3) SYNTHESIS (20)
    synthesis_templates = [
        "{a} kavramini {b} baglaminda sentezleyerek acikla.",
        "{a} ile {b} iliskisini kapsamli ama net bir cercevede anlat.",
        "{a} konusu {b} ile birlikte nasil yorumlanabilir?",
        "{a} ve {b} uzerinden butunc ul bir aciklama yap.",
    ]
    for i, a in enumerate(CONCEPTS):
        b = CONCEPTS[(i + 5) % len(CONCEPTS)]
        t = synthesis_templates[i % len(synthesis_templates)]
        rows.append(
            {
                "id": "",
                "category": "SYNTHESIS",
                "query": t.format(a=a, b=b),
                "expected_terms": [a, b],
            }
        )

    # 4) PHILOSOPHICAL (20)
    philosophical_templates = [
        "{a} degisen bir sey midir, yoksa sabit bir ilke midir?",
        "{a} ile {b} arasindaki gerilim insan eylemini nasil etkiler?",
        "{a} olmadan {b} mumkun mudur?",
        "{a} tartismasinda birey-toplum dengesi nasil kurulmalidir?",
    ]
    for i, a in enumerate(CONCEPTS):
        b = CONCEPTS[(i + 2) % len(CONCEPTS)]
        t = philosophical_templates[i % len(philosophical_templates)]
        rows.append(
            {
                "id": "",
                "category": "PHILOSOPHICAL",
                "query": t.format(a=a, b=b),
                "expected_terms": [a, b],
            }
        )

    # 5) ANALYTIC (20)
    for i, term in enumerate(ANALYTIC_TERMS):
        rows.append(
            {
                "id": "",
                "category": "ANALYTIC",
                "query": f"Bu kitapta '{term}' kelimesi kac kez geciyor?",
                "expected_terms": [term],
            }
        )

    # 6) FOLLOW_UP (20)
    follow_up_queries = [
        "peki bu ne anlama geliyor?",
        "o zaman bunu nasil yorumlamaliyim?",
        "buna bir ornek verebilir misin?",
        "peki bunun tersi durumda ne olur?",
        "bu aciklama yeterli mi emin degilim, tekrar eder misin?",
        "bunu daha sade anlatir misin?",
        "tam olarak hangi noktayi vurguluyorsun?",
        "buna karsi arguman var mi?",
        "bu durumda neyi oncelemek gerekir?",
        "peki bunun pratik sonucu ne olur?",
        "bunu bir cümlede ozetler misin?",
        "buradaki ana fikir nedir?",
        "buna benzer baska bir bakis acisi var mi?",
        "buradaki risk nerede basliyor?",
        "bunu daha sistematik aciklar misin?",
        "peki neden boyle dusunuyorsun?",
        "bu sonuca nasil ulasiyorsun?",
        "bunu adim adim anlatabilir misin?",
        "bu iddianin dayanagi ne?",
        "peki ozetle neyi kabul etmeliyiz?",
    ]
    for q in follow_up_queries:
        rows.append(
            {
                "id": "",
                "category": "FOLLOW_UP",
                "query": q,
                "expected_terms": [],
            }
        )

    if len(rows) != 120:
        raise ValueError(f"Expected 120 rows, got {len(rows)}")

    for i, row in enumerate(rows, start=1):
        row["id"] = f"Q{i:03d}"

    return rows


def main():
    backend_dir = Path(__file__).resolve().parents[1]
    out_path = backend_dir / "data" / "phase0_query_set.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = build_queries()
    out_path.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {len(rows)} queries to: {out_path}")


if __name__ == "__main__":
    main()

