"""Validate the Google copyright CSVs once they are in raw storage. (PRD FR-1.1)

CLOUD-FIRST: the actual download + unzip happens on the Databricks cluster, not the
laptop (the dataset is ~13GB). See notebooks/00_ingest_databricks.py. This module is
a lightweight validator used to confirm the expected files exist in the S3 raw
location and that their headers match the data dictionary.
"""

from __future__ import annotations

EXPECTED_FILES = ("requests.csv", "domains.csv")


def validate_raw(raw_uri: str) -> list[str]:
    """Confirm the expected raw files exist in S3 and look right.

    TODO:
      - list objects under raw_uri (s3://<bucket>/raw/) via s3_io / boto3
      - confirm EXPECTED_FILES are present
      - sanity-check headers against processing/data_dictionary.md
      - return the list of validated URIs
    """
    raise NotImplementedError
