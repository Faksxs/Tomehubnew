import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from config import settings


RAW_BASE = Path(os.getenv("RELIGIOUS_DATASET_RAW_BASE_PATH", "/opt/tomehub/religious-data/raw")).resolve()
NORMALIZED_BASE = Path(os.getenv("RELIGIOUS_DATASET_NORMALIZED_PATH", "/opt/tomehub/religious-data/normalized")).resolve()
MANIFEST_BASE = Path(os.getenv("RELIGIOUS_DATASET_MANIFEST_PATH", "/opt/tomehub/religious-data/manifests")).resolve()
CHECKPOINT_BASE = Path(os.getenv("RELIGIOUS_DATASET_CHECKPOINT_PATH", "/opt/tomehub/religious-data/checkpoints")).resolve()
TYPESENSE_BASE = str(getattr(settings, "RELIGIOUS_DATASET_TYPESENSE_URL", "") or "").strip().rstrip("/")
IMPORT_BATCH_SIZE = max(25, int(os.getenv("RELIGIOUS_DATASET_IMPORT_BATCH_SIZE", "100")))
HADITH_LANGS = {
    token.strip().lower()
    for token in str(os.getenv("RELIGIOUS_DATASET_HADITH_LANGS", "eng,tur") or "eng,tur").split(",")
    if token.strip()
}
HADITH_COLLECTION_ALLOWLIST = {
    token.strip().lower()
    for token in str(os.getenv("RELIGIOUS_DATASET_HADITH_COLLECTIONS", "") or "").split(",")
    if token.strip()
}

QURAN_TRANSLATION_PRIORITY = [
    "Translation - Muhammad Tahir-ul-Qadri",
    "Translation - Marmaduke Pickthall",
    "Translation - Arthur J",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    for base in [NORMALIZED_BASE, MANIFEST_BASE, CHECKPOINT_BASE]:
        base.mkdir(parents=True, exist_ok=True)


def _normalize_ascii(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("ç", "c")
        .replace("ğ", "g")
        .replace("ı", "i")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ü", "u")
        .replace("Ã§", "c")
        .replace("ÄŸ", "g")
        .replace("Ä±", "i")
        .replace("Ã¶", "o")
        .replace("ÅŸ", "s")
        .replace("Ã¼", "u")
    )


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize_ascii(text)).strip("_")


def _tokenize(text: str) -> List[str]:
    return [tok for tok in re.findall(r"[^\W_]+", _normalize_ascii(text), flags=re.UNICODE) if len(tok) >= 2]


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}


def _write_jsonl(path: Path, docs: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def _sha256_dir(path: Path) -> str:
    hasher = hashlib.sha256()
    if not path.exists():
        return ""
    for file_path in sorted([p for p in path.rglob("*") if p.is_file()]):
        hasher.update(str(file_path.relative_to(path)).encode("utf-8"))
        hasher.update(str(file_path.stat().st_size).encode("utf-8"))
    return hasher.hexdigest()


def _manifest_path(dataset: str) -> Path:
    return MANIFEST_BASE / f"{dataset}_manifest.json"


def _checkpoint_path(dataset: str) -> Path:
    return CHECKPOINT_BASE / f"{dataset}_checkpoint.json"


def _normalized_partition_path(dataset: str, partition_name: str) -> Path:
    return NORMALIZED_BASE / dataset / f"{partition_name}.jsonl"


def _typesense_api_key() -> str:
    return str(getattr(settings, "RELIGIOUS_DATASET_TYPESENSE_API_KEY", "") or "").strip()


def _json_request(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(
        url=url,
        method=method.upper(),
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-TYPESENSE-API-KEY": _typesense_api_key(),
        },
    )
    with urllib_request.urlopen(req, timeout=10.0) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset, errors="replace"))


def _create_collection_if_missing(name: str, fields: List[Dict[str, Any]]) -> None:
    try:
        existing = _json_request("GET", f"{TYPESENSE_BASE}/collections/{name}")
        if isinstance(existing, dict) and existing.get("name"):
            return
    except Exception:
        pass
    _json_request("POST", f"{TYPESENSE_BASE}/collections", {"name": name, "fields": fields})


def _delete_collection(name: str) -> None:
    try:
        _json_request("DELETE", f"{TYPESENSE_BASE}/collections/{name}")
    except Exception:
        return


def _upsert_alias(alias_name: str, collection_name: str) -> None:
    _json_request("PUT", f"{TYPESENSE_BASE}/aliases/{alias_name}", {"collection_name": collection_name})


def _parse_import_response(raw: bytes) -> None:
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not payload.get("success", False):
            raise RuntimeError(f"Typesense import failed: {payload}")


def _new_checkpoint(dataset: str, collection_version: str) -> Dict[str, Any]:
    return {
        "dataset": dataset,
        "status": "pending",
        "collection_version": collection_version,
        "completed_partitions": [],
        "current_partition": None,
        "last_offset": 0,
        "updated_at": _now_iso(),
        "import_batch_size": IMPORT_BATCH_SIZE,
    }


def _save_checkpoint(payload: Dict[str, Any]) -> None:
    payload["updated_at"] = _now_iso()
    _write_json(_checkpoint_path(str(payload.get("dataset") or "")), payload)


def _resolve_dataset_root(dataset_name: str) -> Path:
    base = RAW_BASE / dataset_name
    if not base.exists():
        return base
    subdirs = [path for path in base.iterdir() if path.is_dir()]
    if len(subdirs) == 1:
        child = subdirs[0]
        if dataset_name == "hadith-api" and (child / "editions").exists():
            return child
        if dataset_name == "quran-nlp" and (child / "data").exists():
            return child
    return base


def _hadith_fields() -> List[Dict[str, Any]]:
    return [
        {"name": "id", "type": "string"},
        {"name": "dataset", "type": "string"},
        {"name": "provider", "type": "string"},
        {"name": "language", "type": "string", "facet": True},
        {"name": "text", "type": "string"},
        {"name": "normalized_text", "type": "string"},
        {"name": "collection", "type": "string", "facet": True},
        {"name": "book", "type": "string", "optional": True},
        {"name": "chapter", "type": "string", "optional": True},
        {"name": "hadith_no", "type": "string", "facet": True},
        {"name": "grade", "type": "string", "optional": True, "facet": True},
        {"name": "canonical_ref", "type": "string", "facet": True},
        {"name": "source_url", "type": "string", "optional": True},
        {"name": "tags", "type": "string[]", "optional": True, "facet": True},
        {"name": "source_kind", "type": "string", "facet": True},
        {"name": "embedding_text", "type": "string", "optional": True},
    ]


def _quran_fields() -> List[Dict[str, Any]]:
    return [
        {"name": "id", "type": "string"},
        {"name": "dataset", "type": "string"},
        {"name": "provider", "type": "string"},
        {"name": "language", "type": "string"},
        {"name": "verse_text_ar", "type": "string", "optional": True},
        {"name": "translation_text", "type": "string", "optional": True},
        {"name": "normalized_text", "type": "string"},
        {"name": "surah_no", "type": "int32", "facet": True},
        {"name": "ayah_no", "type": "int32", "facet": True},
        {"name": "canonical_ref", "type": "string", "facet": True},
        {"name": "lemmas", "type": "string", "optional": True},
        {"name": "roots", "type": "string", "optional": True},
        {"name": "morphology_tags", "type": "string", "optional": True},
        {"name": "source_url", "type": "string", "optional": True},
        {"name": "source_kind", "type": "string", "facet": True},
        {"name": "embedding_text", "type": "string", "optional": True},
    ]


def _iter_hadith_partitions() -> List[Dict[str, Any]]:
    root = _resolve_dataset_root("hadith-api")
    edition_dir = root / "editions"
    if not edition_dir.exists():
        return []
    partitions: List[Dict[str, Any]] = []
    pattern = re.compile(r"^(?P<lang>[a-z]{3})-(?P<collection>[a-z0-9]+?)(?P<part>\d+)?\.min$", flags=re.IGNORECASE)
    for path in sorted(edition_dir.glob("*.min.json")):
        match = pattern.match(path.stem)
        if not match:
            continue
        lang = match.group("lang").lower()
        collection = match.group("collection").lower()
        if HADITH_LANGS and lang not in HADITH_LANGS:
            continue
        if HADITH_COLLECTION_ALLOWLIST and collection not in HADITH_COLLECTION_ALLOWLIST:
            continue
        partitions.append(
            {
                "name": path.stem.replace(".min", ""),
                "path": path,
                "lang": lang,
                "collection_slug": collection,
            }
        )
    return partitions


def _load_hadith_partition_docs(partition: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = Path(partition["path"])
    with path.open("r", encoding="utf-8", errors="replace") as f:
        payload = json.load(f)
    metadata = payload.get("metadata") or {}
    hadiths = payload.get("hadiths") or []
    sections = metadata.get("sections") or {}
    book_title = str(metadata.get("name") or partition["collection_slug"]).strip()
    collection_slug = str(partition["collection_slug"]).strip().lower()
    language = str(partition["lang"]).strip().lower()
    docs: List[Dict[str, Any]] = []
    seen = set()
    for row in hadiths:
        hadith_no = str(row.get("hadithnumber") or row.get("hadith_number") or row.get("id") or "").strip()
        if not hadith_no:
            continue
        canonical_ref = f"{collection_slug}:{hadith_no}"
        doc_id = f"{partition['name']}:{hadith_no}"
        if doc_id in seen:
            continue
        seen.add(doc_id)
        reference = row.get("reference") or {}
        chapter_no = str(reference.get("book") or "").strip()
        chapter = str(sections.get(chapter_no) or "").strip()
        grade_payload = row.get("grades") or row.get("grade") or row.get("status") or ""
        if isinstance(grade_payload, list):
            grade = ", ".join(
                str((item or {}).get("grade") or "").strip()
                for item in grade_payload
                if isinstance(item, dict) and str((item or {}).get("grade") or "").strip()
            )
        else:
            grade = str(grade_payload or "").strip()
        text = str(row.get("text") or row.get("hadeeth") or row.get("english") or row.get("body") or "").strip()
        if not text:
            continue
        searchable = " ".join(part for part in [text, book_title, chapter, grade, canonical_ref] if part)
        docs.append(
            {
                "id": doc_id,
                "dataset": "hadith-api",
                "provider": "HADITH_API_DATASET",
                "language": language,
                "text": text,
                "normalized_text": _normalize_ascii(searchable),
                "collection": collection_slug,
                "book": book_title,
                "chapter": chapter,
                "hadith_no": hadith_no,
                "grade": grade,
                "canonical_ref": canonical_ref,
                "source_url": "",
                "tags": _tokenize(f"{book_title} {chapter} {collection_slug}")[:16],
                "source_kind": "HADITH",
                "embedding_text": _normalize_ascii(searchable),
            }
        )
    return docs


def _build_quran_docs() -> List[Dict[str, Any]]:
    root = _resolve_dataset_root("quran-nlp")
    data_root = root / "data"
    verse_map: Dict[str, Dict[str, Any]] = {}

    quran_csv = data_root / "quran" / "quran.csv"
    if quran_csv.exists():
        with quran_csv.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                surah_no = _safe_int(row.get("surah_no"))
                ayah_no = _safe_int(row.get("ayah_no_surah"))
                if not surah_no or not ayah_no:
                    continue
                canonical_ref = f"{surah_no}:{ayah_no}"
                verse_map.setdefault(
                    canonical_ref,
                    {
                        "surah_no": surah_no,
                        "ayah_no": ayah_no,
                        "verse_text_ar": "",
                        "translation_text": "",
                        "lemmas": "",
                        "roots": "",
                        "morphology_tags": "",
                    },
                )
                verse_map[canonical_ref]["verse_text_ar"] = str(row.get("ayah") or "").strip() or verse_map[canonical_ref]["verse_text_ar"]

    main_df = data_root / "main_df.csv"
    if main_df.exists():
        with main_df.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                surah_no = _safe_int(row.get("Surah"))
                ayah_no = _safe_int(row.get("Ayat"))
                if not surah_no or not ayah_no:
                    continue
                canonical_ref = f"{surah_no}:{ayah_no}"
                verse_map.setdefault(
                    canonical_ref,
                    {
                        "surah_no": surah_no,
                        "ayah_no": ayah_no,
                        "verse_text_ar": "",
                        "translation_text": "",
                        "lemmas": "",
                        "roots": "",
                        "morphology_tags": "",
                    },
                )
                entry = verse_map[canonical_ref]
                entry["verse_text_ar"] = str(row.get("Arabic") or "").strip() or entry["verse_text_ar"]
                for column in QURAN_TRANSLATION_PRIORITY:
                    candidate = str(row.get(column) or "").strip()
                    if candidate:
                        entry["translation_text"] = candidate
                        break
                entry["surah_title"] = str(row.get("EnglishTitle") or row.get("Name") or "").strip()
                entry["place_of_revelation"] = str(row.get("PlaceOfRevelation") or "").strip()

    morphology_csv = data_root / "quran" / "corpus" / "quran_morphology.csv"
    if morphology_csv.exists():
        with morphology_csv.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                location = str(row.get("LOCATION") or "").strip()
                match = re.match(r"\((\d+):(\d+):", location)
                if not match:
                    continue
                surah_no = int(match.group(1))
                ayah_no = int(match.group(2))
                canonical_ref = f"{surah_no}:{ayah_no}"
                if canonical_ref not in verse_map:
                    verse_map[canonical_ref] = {
                        "surah_no": surah_no,
                        "ayah_no": ayah_no,
                        "verse_text_ar": "",
                        "translation_text": "",
                        "lemmas": "",
                        "roots": "",
                        "morphology_tags": "",
                    }
                features = str(row.get("FEATURES") or "").strip()
                tags = str(row.get("TAG") or "").strip()
                lemmas = re.findall(r"LEM:([^|]+)", features)
                roots = re.findall(r"ROOT:([^|]+)", features)
                if lemmas:
                    current = set(filter(None, str(verse_map[canonical_ref].get("lemmas") or "").split()))
                    current.update(_normalize_ascii(" ".join(lemmas)).split())
                    verse_map[canonical_ref]["lemmas"] = " ".join(sorted(current))
                if roots:
                    current = set(filter(None, str(verse_map[canonical_ref].get("roots") or "").split()))
                    current.update(_normalize_ascii(" ".join(roots)).split())
                    verse_map[canonical_ref]["roots"] = " ".join(sorted(current))
                if tags:
                    current = set(filter(None, str(verse_map[canonical_ref].get("morphology_tags") or "").split()))
                    current.update(_normalize_ascii(tags).split())
                    verse_map[canonical_ref]["morphology_tags"] = " ".join(sorted(current))

    docs: List[Dict[str, Any]] = []
    for canonical_ref, row in sorted(verse_map.items(), key=lambda item: (item[1].get("surah_no", 0), item[1].get("ayah_no", 0))):
        searchable = " ".join(
            part
            for part in [
                str(row.get("translation_text") or "").strip(),
                str(row.get("verse_text_ar") or "").strip(),
                str(row.get("surah_title") or "").strip(),
                str(row.get("lemmas") or "").strip(),
                str(row.get("roots") or "").strip(),
                str(row.get("morphology_tags") or "").strip(),
            ]
            if part
        )
        docs.append(
            {
                "id": canonical_ref,
                "dataset": "quran-nlp",
                "provider": "QURAN_NLP_DATASET",
                "language": "en",
                "verse_text_ar": str(row.get("verse_text_ar") or "").strip(),
                "translation_text": str(row.get("translation_text") or "").strip(),
                "normalized_text": _normalize_ascii(searchable),
                "surah_no": int(row.get("surah_no") or 0),
                "ayah_no": int(row.get("ayah_no") or 0),
                "canonical_ref": canonical_ref,
                "lemmas": str(row.get("lemmas") or "").strip(),
                "roots": str(row.get("roots") or "").strip(),
                "morphology_tags": str(row.get("morphology_tags") or "").strip(),
                "source_url": "",
                "source_kind": "QURAN",
                "embedding_text": _normalize_ascii(searchable),
            }
        )
    return docs


def _dataset_state(dataset: str) -> Dict[str, Any]:
    if dataset == "hadith":
        partitions = _iter_hadith_partitions()
        return {
            "dataset": dataset,
            "raw_name": "hadith-api",
            "collection_version": "religious_hadith_v1",
            "alias_name": str(getattr(settings, "RELIGIOUS_DATASET_HADITH_COLLECTION", "religious_hadith_current") or "religious_hadith_current").strip(),
            "fields": _hadith_fields(),
            "partitions": [
                {
                    "name": partition["name"],
                    "source_path": str(Path(partition["path"]).resolve()),
                    "loader": (lambda part=partition: _load_hadith_partition_docs(part)),
                }
                for partition in partitions
            ],
        }
    if dataset == "quran":
        return {
            "dataset": dataset,
            "raw_name": "quran-nlp",
            "collection_version": "religious_quran_v1",
            "alias_name": str(getattr(settings, "RELIGIOUS_DATASET_QURAN_COLLECTION", "religious_quran_current") or "religious_quran_current").strip(),
            "fields": _quran_fields(),
            "partitions": [
                {
                    "name": "quran_core",
                    "source_path": str((_resolve_dataset_root("quran-nlp") / "data").resolve()),
                    "loader": _build_quran_docs,
                }
            ],
        }
    raise ValueError(f"unsupported dataset: {dataset}")


def _import_partition_docs(
    dataset: str,
    collection_name: str,
    partition_name: str,
    docs: List[Dict[str, Any]],
    checkpoint: Dict[str, Any],
) -> None:
    if not docs:
        checkpoint["completed_partitions"] = sorted(set(checkpoint.get("completed_partitions", []) + [partition_name]))
        checkpoint["current_partition"] = None
        checkpoint["last_offset"] = 0
        checkpoint["status"] = "importing"
        _save_checkpoint(checkpoint)
        return

    start_offset = 0
    if checkpoint.get("current_partition") == partition_name and checkpoint.get("status") == "importing":
        start_offset = min(max(0, int(checkpoint.get("last_offset", 0) or 0)), len(docs))
    timeout = max(20.0, float(getattr(settings, "RELIGIOUS_DATASET_TIMEOUT_SEC", 0.45) or 0.45) * 60.0)

    for offset in range(start_offset, len(docs), IMPORT_BATCH_SIZE):
        batch = docs[offset : offset + IMPORT_BATCH_SIZE]
        payload = "\n".join(json.dumps(doc, ensure_ascii=False) for doc in batch).encode("utf-8")
        req = urllib_request.Request(
            url=f"{TYPESENSE_BASE}/collections/{collection_name}/documents/import?action=upsert",
            method="POST",
            data=payload,
            headers={
                "Content-Type": "text/plain",
                "X-TYPESENSE-API-KEY": _typesense_api_key(),
            },
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                _parse_import_response(resp.read())
        except urllib_error.URLError as exc:
            checkpoint["status"] = "failed"
            checkpoint["current_partition"] = partition_name
            checkpoint["last_offset"] = offset
            checkpoint["last_error"] = str(exc)
            _save_checkpoint(checkpoint)
            raise
        checkpoint["status"] = "importing"
        checkpoint["current_partition"] = partition_name
        checkpoint["last_offset"] = min(offset + len(batch), len(docs))
        checkpoint["partition_doc_count"] = len(docs)
        checkpoint["last_error"] = ""
        _save_checkpoint(checkpoint)

    checkpoint["completed_partitions"] = sorted(set(checkpoint.get("completed_partitions", []) + [partition_name]))
    checkpoint["current_partition"] = None
    checkpoint["last_offset"] = 0
    checkpoint["status"] = "importing"
    checkpoint["partition_doc_count"] = len(docs)
    checkpoint["last_error"] = ""
    _save_checkpoint(checkpoint)


def run_load(dataset: str, *, rebuild: bool = False) -> None:
    _ensure_dirs()
    state = _dataset_state(dataset)
    checkpoint = _load_json(_checkpoint_path(dataset))
    if rebuild or checkpoint.get("collection_version") != state["collection_version"]:
        checkpoint = _new_checkpoint(dataset, state["collection_version"])
        _delete_collection(state["collection_version"])
        _save_checkpoint(checkpoint)

    _create_collection_if_missing(state["collection_version"], state["fields"])
    completed = set(checkpoint.get("completed_partitions", []))
    total_docs = 0
    partition_stats: List[Dict[str, Any]] = []

    for partition in state["partitions"]:
        partition_name = str(partition["name"])
        if partition_name in completed:
            shard_path = _normalized_partition_path(dataset, partition_name)
            if shard_path.exists():
                with shard_path.open("r", encoding="utf-8") as f:
                    doc_count = sum(1 for _ in f)
            else:
                doc_count = 0
            total_docs += doc_count
            partition_stats.append({"name": partition_name, "doc_count": doc_count, "status": "skipped"})
            continue

        docs = partition["loader"]()
        shard_path = _normalized_partition_path(dataset, partition_name)
        _write_jsonl(shard_path, docs)
        _import_partition_docs(dataset, state["collection_version"], partition_name, docs, checkpoint)
        total_docs += len(docs)
        partition_stats.append({"name": partition_name, "doc_count": len(docs), "status": "complete"})
        checkpoint = _load_json(_checkpoint_path(dataset))
        completed = set(checkpoint.get("completed_partitions", []))

    _upsert_alias(state["alias_name"], state["collection_version"])
    manifest = {
        "dataset": dataset,
        "source_path": str((_resolve_dataset_root(state["raw_name"])).resolve()),
        "source_version": _sha256_dir(_resolve_dataset_root(state["raw_name"])),
        "imported_at": _now_iso(),
        "collection_version": state["collection_version"],
        "alias_name": state["alias_name"],
        "doc_count": total_docs,
        "partition_count": len(state["partitions"]),
        "partitions": partition_stats,
        "normalized_path": str((NORMALIZED_BASE / dataset).resolve()),
    }
    checkpoint = _new_checkpoint(dataset, state["collection_version"])
    checkpoint["status"] = "complete"
    checkpoint["completed_partitions"] = [partition["name"] for partition in state["partitions"]]
    checkpoint["doc_count"] = total_docs
    _write_json(_manifest_path(dataset), manifest)
    _save_checkpoint(checkpoint)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def run_verify() -> None:
    out = {
        "typesense_url": TYPESENSE_BASE,
        "hadith_manifest": _load_json(_manifest_path("hadith")),
        "hadith_checkpoint": _load_json(_checkpoint_path("hadith")),
        "quran_manifest": _load_json(_manifest_path("quran")),
        "quran_checkpoint": _load_json(_checkpoint_path("quran")),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual indexer for religious dataset search")
    parser.add_argument("command", choices=["load", "rebuild", "verify"])
    parser.add_argument("dataset", nargs="?", choices=["hadith", "quran"])
    args = parser.parse_args()

    if args.command == "verify":
        run_verify()
        return
    if not args.dataset:
        parser.error("dataset is required for load/rebuild")
    run_load(args.dataset, rebuild=args.command == "rebuild")


if __name__ == "__main__":
    main()
