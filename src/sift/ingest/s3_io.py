"""Read/write helpers for raw and processed data.

Abstracts over S3 vs local disk so the rest of the pipeline does not care where
data lives. Controlled by ``USE_S3`` in ``.env``. (PRD FR-1.1, FR-1.2)

Scope note: these pandas-based helpers are for *small* data — the dashboard
sample, local fixtures, and validation. The full ~13GB raw CSVs are read by
Spark on Databricks (via ``s3a://``), not here. ``read_csv`` will happily read a
gzipped object, but loading a multi-GB file through pandas is not the intended
path.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from sift.config import Settings, load_settings


def _s3_client(settings: Settings):
    """Create a boto3 S3 client.

    Credentials and region are resolved by boto3's standard chain (the
    AWS_* environment variables loaded from ``.env``), so no secrets are
    referenced here directly.
    """
    import boto3

    return boto3.client("s3")


def _prefix(settings: Settings, key: str, default: str) -> str:
    """Look up a storage prefix from config, ensuring a trailing slash."""
    value = settings.get("storage", "layout", key, default=default)
    return value if value.endswith("/") else f"{value}/"


def _read_bytes_csv(data: bytes, name: str) -> pd.DataFrame:
    """Parse CSV bytes into a DataFrame, inferring gzip from the name."""
    compression = "gzip" if name.endswith(".gz") else "infer"
    return pd.read_csv(io.BytesIO(data), compression=compression)


def read_csv(name: str) -> pd.DataFrame:
    """Read a raw CSV by logical name (e.g. ``'requests.csv'``).

    When ``USE_S3`` is set, reads ``s3://{bucket}/{raw_prefix}{name}`` via
    boto3, transparently falling back to a ``.gz`` object if the plain name is
    absent (the raw CSVs are staged gzipped). Otherwise reads from
    ``{local_data_dir}/raw/{name}``.
    """
    settings = load_settings()

    if settings.use_s3:
        if not settings.s3_bucket:
            raise ValueError("USE_S3 is true but S3_BUCKET is not configured")
        client = _s3_client(settings)
        raw_prefix = _prefix(settings, "raw_prefix", "raw/")
        candidates = [name] if name.endswith(".gz") else [name, f"{name}.gz"]
        last_error: Exception | None = None
        for candidate in candidates:
            key = f"{raw_prefix}{candidate}"
            try:
                obj = client.get_object(Bucket=settings.s3_bucket, Key=key)
                return _read_bytes_csv(obj["Body"].read(), candidate)
            except client.exceptions.NoSuchKey as exc:  # pragma: no cover - network
                last_error = exc
        raise FileNotFoundError(
            f"None of {candidates} found under s3://{settings.s3_bucket}/{raw_prefix}"
        ) from last_error

    path = local_path("raw", name)
    if not path.exists() and not name.endswith(".gz"):
        gz = local_path("raw", f"{name}.gz")
        if gz.exists():
            path = gz
    return pd.read_csv(path)


def write_processed(df: pd.DataFrame, name: str) -> str:
    """Write a processed dataset as Parquet and return its URI/path.

    Mirrors :func:`read_csv` for the processed location. Never writes to the
    raw prefix, so raw inputs are never overwritten.
    """
    if not name.endswith(".parquet"):
        name = f"{name}.parquet"

    settings = load_settings()

    if settings.use_s3:
        if not settings.s3_bucket:
            raise ValueError("USE_S3 is true but S3_BUCKET is not configured")
        client = _s3_client(settings)
        processed_prefix = _prefix(settings, "processed_prefix", "processed/")
        key = f"{processed_prefix}{name}"
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        client.put_object(Bucket=settings.s3_bucket, Key=key, Body=buffer.getvalue())
        return f"s3://{settings.s3_bucket}/{key}"

    path = local_path("processed", name)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return str(path)


def local_path(*parts: str) -> Path:
    """Resolve a path under the local data dir."""
    return load_settings().local_data_dir.joinpath(*parts)
