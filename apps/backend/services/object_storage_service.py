from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Generator, Iterable, Optional

import oci

from config import settings
from services.pdf_service import get_oci_config

logger = logging.getLogger(__name__)


class ObjectStorageConfigError(RuntimeError):
    pass


def _get_bucket_name() -> str:
    bucket = str(getattr(settings, "OCI_OBJECT_STORAGE_BUCKET", "") or "").strip()
    if not bucket:
        raise ObjectStorageConfigError("OCI_OBJECT_STORAGE_BUCKET is not configured")
    return bucket


def _get_compartment_id() -> str:
    compartment = str(getattr(settings, "OCI_COMPARTMENT_OCID", "") or "").strip()
    if compartment:
        return compartment
    tenancy = str(getattr(settings, "OCI_TENANCY_OCID", "") or os.getenv("OCI_TENANCY_OCID", "")).strip()
    if tenancy:
        return tenancy
    raise ObjectStorageConfigError("OCI compartment/tenancy OCID is not configured")


def _get_namespace(client) -> str:
    configured = str(getattr(settings, "OCI_OBJECT_STORAGE_NAMESPACE", "") or "").strip()
    if configured:
        return configured
    response = client.get_namespace()
    namespace = str(response.data or "").strip()
    if not namespace:
        raise ObjectStorageConfigError("Unable to resolve Object Storage namespace")
    return namespace


def get_object_storage_client():
    return oci.object_storage.ObjectStorageClient(get_oci_config())


def get_bucket_context(bucket_name: Optional[str] = None) -> Dict[str, str]:
    client = get_object_storage_client()
    bucket = bucket_name or _get_bucket_name()
    namespace = _get_namespace(client)
    return {"bucket_name": bucket, "namespace_name": namespace}


def compute_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def build_pdf_object_key(firebase_uid: str, book_id: str, sha256_hex: str) -> str:
    return f"users/{firebase_uid}/books/{book_id}/source/{sha256_hex}.pdf"


def build_output_prefix(firebase_uid: str, book_id: str, job_id: str) -> str:
    return f"users/{firebase_uid}/books/{book_id}/oci-output/{job_id}/"


def build_canonical_object_key(firebase_uid: str, book_id: str) -> str:
    return f"users/{firebase_uid}/books/{book_id}/canonical/latest.json"


def upload_pdf(file_path: str, firebase_uid: str, book_id: str, sha256_hex: Optional[str] = None) -> Dict[str, str | int]:
    sha256_value = sha256_hex or compute_sha256(file_path)
    object_key = build_pdf_object_key(firebase_uid, book_id, sha256_value)
    client = get_object_storage_client()
    ctx = get_bucket_context()

    with open(file_path, "rb") as handle:
        client.put_object(
            ctx["namespace_name"],
            ctx["bucket_name"],
            object_key,
            handle,
            content_type="application/pdf",
        )

    return {
        "bucket_name": ctx["bucket_name"],
        "namespace_name": ctx["namespace_name"],
        "object_key": object_key,
        "sha256": sha256_value,
        "size_bytes": int(os.path.getsize(file_path)),
    }


def put_json_object(bucket_name: str, object_key: str, payload: Dict[str, object] | list[object]) -> None:
    client = get_object_storage_client()
    ctx = get_bucket_context(bucket_name=bucket_name)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    client.put_object(
        ctx["namespace_name"],
        bucket_name,
        object_key,
        body,
        content_type="application/json",
    )


def get_object_headers(bucket_name: str, object_key: str) -> Dict[str, str | int]:
    client = get_object_storage_client()
    ctx = get_bucket_context(bucket_name=bucket_name)
    response = client.head_object(ctx["namespace_name"], bucket_name, object_key)
    headers = response.headers
    return {
        "content_length": int(headers.get("Content-Length", 0) or 0),
        "content_type": headers.get("Content-Type", "application/octet-stream"),
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
    }


def stream_object(
    bucket_name: str,
    object_key: str,
    byte_range: Optional[str] = None,
    chunk_size: int = 1024 * 1024,
) -> tuple[Generator[bytes, None, None], Dict[str, str | int]]:
    client = get_object_storage_client()
    ctx = get_bucket_context(bucket_name=bucket_name)
    kwargs = {}
    if byte_range:
        kwargs["range"] = byte_range
    response = client.get_object(ctx["namespace_name"], bucket_name, object_key, **kwargs)

    def iterator() -> Generator[bytes, None, None]:
        try:
            stream = getattr(response.data, "raw", response.data)
            reader = getattr(stream, "stream", None)
            if callable(reader):
                for chunk in reader(chunk_size, decode_content=False):
                    if chunk:
                        yield chunk
                return

            while True:
                chunk = response.data.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                response.data.close()
            except Exception:
                pass

    headers = {
        "content_length": int(response.headers.get("Content-Length", 0) or 0),
        "content_type": response.headers.get("Content-Type", "application/octet-stream"),
        "content_range": response.headers.get("Content-Range"),
        "accept_ranges": response.headers.get("Accept-Ranges", "bytes"),
        "etag": response.headers.get("ETag"),
    }
    return iterator(), headers


def download_object_to_tempfile(bucket_name: str, object_key: str, suffix: str = ".pdf") -> str:
    generator, _ = stream_object(bucket_name, object_key)
    fd, temp_path = tempfile.mkstemp(prefix="tomehub_pdf_", suffix=suffix)
    os.close(fd)
    with open(temp_path, "wb") as handle:
        for chunk in generator:
            handle.write(chunk)
    return temp_path


def list_objects(bucket_name: str, prefix: str) -> list[Dict[str, str | int]]:
    client = get_object_storage_client()
    ctx = get_bucket_context(bucket_name=bucket_name)
    start = None
    collected: list[Dict[str, str | int]] = []
    while True:
        response = client.list_objects(
            ctx["namespace_name"],
            bucket_name,
            prefix=prefix,
            start=start,
            fields="name,size,timeCreated",
        )
        data = response.data
        for item in getattr(data, "objects", []) or []:
            collected.append(
                {
                    "name": item.name,
                    "size": int(getattr(item, "size", 0) or 0),
                }
            )
        start = getattr(data, "next_start_with", None)
        if not start:
            break
    return collected


def read_json_objects(bucket_name: str, prefix: str) -> list[dict]:
    import json

    payloads: list[dict] = []
    for item in list_objects(bucket_name, prefix):
        object_name = str(item.get("name") or "")
        if not object_name.lower().endswith(".json"):
            continue
        client = get_object_storage_client()
        ctx = get_bucket_context(bucket_name=bucket_name)
        response = client.get_object(ctx["namespace_name"], bucket_name, object_name)
        body = response.data.text if hasattr(response.data, "text") else response.data.read().decode("utf-8")
        try:
            payloads.append(json.loads(body))
        except Exception as exc:
            logger.warning("Failed to parse OCI output json '%s': %s", object_name, exc)
    return payloads


def delete_object(bucket_name: str, object_key: str) -> None:
    client = get_object_storage_client()
    ctx = get_bucket_context(bucket_name=bucket_name)
    client.delete_object(ctx["namespace_name"], bucket_name, object_key)


def delete_prefix(bucket_name: str, prefix: str) -> None:
    objects = list_objects(bucket_name, prefix)
    for item in objects:
        object_name = str(item.get("name") or "")
        if not object_name:
            continue
        delete_object(bucket_name, object_name)


def cleanup_pdf_artifacts(bucket_name: str, object_key: Optional[str], output_prefix: Optional[str]) -> None:
    if object_key:
        delete_object(bucket_name, object_key)
    if object_key:
        parts = str(object_key).split("/")
        if len(parts) >= 5:
            canonical_object_key = f"{'/'.join(parts[:4])}/canonical/latest.json"
            try:
                delete_object(bucket_name, canonical_object_key)
            except Exception:
                logger.debug("Canonical sidecar delete skipped for %s", canonical_object_key)
    if output_prefix:
        delete_prefix(bucket_name, output_prefix)


def get_storage_quota_summary(current_bytes: int, incoming_bytes: int) -> Dict[str, float | bool]:
    warn_gb = float(getattr(settings, "PDF_STORAGE_WARN_GB", 15.0))
    block_gb = float(getattr(settings, "PDF_STORAGE_BLOCK_GB", 19.0))
    limit_gb = float(getattr(settings, "PDF_STORAGE_LIMIT_GB", 20.0))

    projected_bytes = int(current_bytes) + int(incoming_bytes)
    projected_gb = projected_bytes / float(1024 ** 3)
    return {
        "storage_used_gb": round(projected_gb, 3),
        "storage_limit_gb": limit_gb,
        "warn": projected_gb >= warn_gb,
        "block": projected_gb >= block_gb,
    }
