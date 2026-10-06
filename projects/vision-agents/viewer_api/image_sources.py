"""Helpers for materializing local, HTTP, and GCS image sources."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from google.cloud import storage


def _resolve_suffix(source: str) -> str:
    """Infer a reasonable file suffix from a source string."""
    parsed = urlparse(source)
    suffix = Path(parsed.path).suffix
    return suffix or ".jpg"


def _download_gcs_object(source: str, destination_path: str) -> None:
    """Download a GCS object identified by ``gs://bucket/path``."""
    parsed = urlparse(source)
    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")
    if not bucket_name or not blob_name:
        raise ValueError(f"Invalid GCS source: {source}")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(destination_path)


def materialize_image_source(source: str) -> str:
    """Copy a local/remote image source to a temporary local file path."""
    suffix = _resolve_suffix(source)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        destination_path = temp_file.name

    if source.startswith("gs://"):
        _download_gcs_object(source, destination_path)
        return destination_path

    if source.startswith("http://") or source.startswith("https://"):
        with urlopen(source) as response, open(destination_path, "wb") as output_file:
            shutil.copyfileobj(response, output_file)
        return destination_path

    local_path = Path(source).expanduser().resolve()
    if not local_path.exists():
        raise FileNotFoundError(f"Image source not found: {source}")
    shutil.copyfile(local_path, destination_path)
    return destination_path
