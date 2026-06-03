"""Read/write helpers for raw and processed data.

Abstracts over S3 vs local disk so the rest of the pipeline does not care where
data lives. Controlled by USE_S3 in .env. (PRD FR-1.1, FR-1.2)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_csv(name: str) -> pd.DataFrame:
    """Read a raw CSV by logical name (e.g. 'requests.csv').

    TODO: if USE_S3, read from s3://{bucket}/{raw_prefix}{name} via boto3;
    otherwise read from {local_data_dir}/raw/{name}.
    """
    raise NotImplementedError


def write_processed(df: pd.DataFrame, name: str) -> str:
    """Write a processed dataset (Parquet preferred) and return its URI/path.

    TODO: mirror read_csv for the processed location. Never overwrite raw inputs.
    """
    raise NotImplementedError


def local_path(*parts: str) -> Path:
    """Resolve a path under the local data dir."""
    raise NotImplementedError
