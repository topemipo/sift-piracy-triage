"""Validate the Google copyright CSVs once they are in raw storage. (PRD FR-1.1)

CLOUD-FIRST: the actual download + unzip happens on the Databricks cluster, not the
laptop (the dataset is ~13GB). See notebooks/00_ingest_databricks.py. This module is
a lightweight validator used to confirm the expected files exist in the S3 raw
location and that their headers match the data dictionary.
"""

from __future__ import annotations

import gzip
import io
from urllib.parse import urlparse

EXPECTED_FILES = ("requests.csv", "domains.csv")

# A token that must appear in each file's header, as a cheap sanity check that
# the staged object is the file we think it is (real source column names).
EXPECTED_HEADER_TOKENS = {
    "requests.csv": "Reporting organization name",
    "domains.csv": "Domain",
}


def _split_s3_uri(raw_uri: str) -> tuple[str, str]:
    """Split ``s3://bucket/prefix/`` into ``(bucket, prefix)``."""
    parsed = urlparse(raw_uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Expected an s3:// URI, got {raw_uri!r}")
    prefix = parsed.path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return parsed.netloc, prefix


def _read_header(client, bucket: str, key: str) -> str:
    """Read just the first line of an object (gunzipping if needed)."""
    obj = client.get_object(Bucket=bucket, Key=key, Range="bytes=0-8191")
    data = obj["Body"].read()
    if key.endswith(".gz"):
        # A partial gzip stream raises EOFError once the buffer is exhausted;
        # the first line is well within the first chunk.
        try:
            data = gzip.decompress(data)
        except (EOFError, OSError):
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
                data = fh.read(8192)
    return data.decode("utf-8", errors="replace").splitlines()[0]


def validate_raw(raw_uri: str) -> list[str]:
    """Confirm the expected raw files exist in S3 and look right. (PRD FR-1.1)

    Lists objects under ``raw_uri``, confirms each name in :data:`EXPECTED_FILES`
    is present (allowing a ``.gz`` suffix since the staging script gzips them),
    and sanity-checks each header against the expected source column tokens.
    Returns the list of validated ``s3://`` URIs.
    """
    import boto3

    bucket, prefix = _split_s3_uri(raw_uri)
    client = boto3.client("s3")

    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = {obj["Key"] for obj in response.get("Contents", [])}

    validated: list[str] = []
    for name in EXPECTED_FILES:
        plain, gz = f"{prefix}{name}", f"{prefix}{name}.gz"
        key = plain if plain in keys else gz if gz in keys else None
        if key is None:
            raise FileNotFoundError(
                f"Expected raw file {name!r} (or {name}.gz) not found under {raw_uri}"
            )
        header = _read_header(client, bucket, key)
        token = EXPECTED_HEADER_TOKENS[name]
        if token not in header:
            raise ValueError(
                f"Header of {key} missing expected column {token!r}: {header!r}"
            )
        validated.append(f"s3://{bucket}/{key}")

    return validated
