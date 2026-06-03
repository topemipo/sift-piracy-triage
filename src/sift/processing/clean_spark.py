"""PySpark cleaning of the full Google copyright dataset. (PRD FR-2.1, FR-2.2)

Justified by dataset size (millions of rows). Runnable as a local Spark session or
as a Databricks notebook. Output: a cleaned, analysis-ready dataset written back to
processed storage, plus a documented schema.

Known data-quality issues to handle (per the Google FAQ):
  - duplicate organisation / copyright-owner names and inconsistent spellings
  - self-reported, sometimes inaccurate fields
  - URL-count columns that must be coerced to integers
"""

from __future__ import annotations


def build_spark(app_name: str = "sift-clean"):
    """Create or get a SparkSession.

    TODO: configure for local use; on Databricks the session is provided.
    """
    raise NotImplementedError


def clean_requests(spark, raw_uri: str):
    """Clean the requests table.

    TODO:
      - parse dates, coerce URL counts to int
      - normalise + deduplicate organisation/owner names
      - derive removal_rate = urls_removed / urls_specified (guard divide-by-zero)
      - return a Spark DataFrame
    """
    raise NotImplementedError


def clean_domains(spark, raw_uri: str):
    """Clean the domains table (normalise domain strings, coerce counts)."""
    raise NotImplementedError


def join_and_persist(requests_df, domains_df, out_uri: str) -> str:
    """Join on request_id, persist Parquet to processed storage, return URI."""
    raise NotImplementedError
