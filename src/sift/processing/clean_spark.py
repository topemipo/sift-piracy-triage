"""PySpark cleaning of the full Google copyright dataset. (PRD FR-2.1, FR-2.2)

Justified by dataset size (millions of rows). Runnable as a local Spark session
or as a Databricks notebook. Output: a cleaned, analysis-ready dataset written
back to processed storage, plus a documented schema.

Known data-quality issues handled (per the Google FAQ and the real README):
  - duplicate organisation / copyright-owner names and inconsistent spellings,
    resolved to a canonical spelling per stable owner/org *id*;
  - self-reported, sometimes inaccurate fields (a ``from_abuser`` flag is kept
    as an explicit noise signal rather than dropped);
  - URL-count columns coerced to integers;
  - there is no "URLs specified" column in the source, so it is *derived* as the
    sum of the four outcome buckets (removed + not-in-index + no-action +
    pending), and ``removal_rate = urls_removed / urls_specified``.

The scalar transforms (name normalisation, removal-rate maths) are written as
plain Python helpers so they can be unit-tested without a JVM; the Spark code
mirrors them with native column expressions for scale.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pyspark.sql import DataFrame, SparkSession

# --- Source-to-schema column maps (real Google Transparency Report columns) ---

REQUESTS_COLUMN_MAP: dict[str, str] = {
    "Request ID": "request_id",
    "Date": "date",
    "Lumen URL": "lumen_url",
    "Copyright owner ID": "copyright_owner_id",
    "Copyright owner name": "copyright_owner",
    "Reporting organization ID": "reporting_org_id",
    "Reporting organization name": "reporting_org",
    "URLs removed": "urls_removed",
    "URLs that were not in Google's search index": "urls_not_in_index",
    "URLs for which we took no action": "urls_no_action",
    "URLs pending review": "urls_pending",
    "From Abuser": "from_abuser",
}

DOMAINS_COLUMN_MAP: dict[str, str] = {
    "Request ID": "request_id",
    "Domain": "domain",
    "URLs removed": "urls_removed",
    "URLs that were not in Google's search index": "urls_not_in_index",
    "URLs for which we took no action": "urls_no_action",
    "URLs pending review": "urls_pending",
    "From Abuser": "from_abuser",
}

# The four mutually-exclusive outcome buckets whose sum is the URLs specified.
URL_COUNT_COLUMNS = (
    "urls_removed",
    "urls_not_in_index",
    "urls_no_action",
    "urls_pending",
)

# ISO 8601 with a trailing Z, e.g. "2012-05-23T21:59:06Z".
_SOURCE_TIMESTAMP_FORMAT = "yyyy-MM-dd'T'HH:mm:ss'Z'"

_WHITESPACE_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Pure-Python helpers (unit-testable without Spark)                           #
# --------------------------------------------------------------------------- #


def normalise_name(name: str | None) -> str | None:
    """Collapse whitespace and strip a free-text name; preserve casing.

    Used to fold trivial spelling variants ("Web  Sheriff " -> "Web Sheriff")
    before choosing a canonical spelling per id. Returns ``None`` for blanks.
    """
    if name is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", name).strip()
    return cleaned or None


def name_key(name: str | None) -> str | None:
    """Case-insensitive grouping key for a normalised name."""
    norm = normalise_name(name)
    return norm.casefold() if norm is not None else None


def normalise_domain(domain: str | None) -> str | None:
    """Lowercase, trim, and strip a trailing dot from a domain string."""
    if domain is None:
        return None
    cleaned = domain.strip().lower().rstrip(".")
    return cleaned or None


def safe_removal_rate(
    urls_removed: int | None, urls_specified: int | None
) -> float | None:
    """``urls_removed / urls_specified``, guarding divide-by-zero.

    Returns ``None`` when nothing was specified (rate undefined), and clamps the
    result to [0, 1] to absorb dirty rows where removed exceeds specified.
    """
    if not urls_specified:
        return None
    rate = (urls_removed or 0) / urls_specified
    return max(0.0, min(1.0, rate))


# --------------------------------------------------------------------------- #
# Spark session                                                               #
# --------------------------------------------------------------------------- #


def build_spark(app_name: str = "sift-clean") -> SparkSession:
    """Create or get a local SparkSession.

    For local runs and tests. On Databricks the session is provided as the
    global ``spark``, so this is not called there.
    """
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


# --------------------------------------------------------------------------- #
# Cleaning                                                                    #
# --------------------------------------------------------------------------- #


def _coerce_int(column):
    """Strip non-digit characters from a count column and cast to int (default 0)."""
    from pyspark.sql import functions as F

    digits = F.regexp_replace(F.col(column).cast("string"), r"[^0-9-]", "")
    return F.coalesce(digits.cast("int"), F.lit(0)).alias(column)


def _rename(df: DataFrame, column_map: dict[str, str]) -> DataFrame:
    """Select and rename source columns to the snake_case schema."""
    from pyspark.sql import functions as F

    present = [src for src in column_map if src in df.columns]
    missing = [src for src in column_map if src not in df.columns]
    if missing:
        raise ValueError(f"Source columns missing from input: {missing}")
    return df.select([F.col(f"`{src}`").alias(column_map[src]) for src in present])


def _add_url_aggregates(df: DataFrame) -> DataFrame:
    """Coerce the four count columns, derive urls_specified and removal_rate."""
    from pyspark.sql import functions as F

    df = df.select(
        *[c for c in df.columns if c not in URL_COUNT_COLUMNS],
        *[_coerce_int(c) for c in URL_COUNT_COLUMNS],
    )
    specified = sum(F.col(c) for c in URL_COUNT_COLUMNS)
    df = df.withColumn("urls_specified", specified)
    removal_rate = F.when(
        F.col("urls_specified") > 0,
        F.least(
            F.lit(1.0),
            F.greatest(F.lit(0.0), F.col("urls_removed") / F.col("urls_specified")),
        ),
    ).otherwise(F.lit(None).cast("double"))
    return df.withColumn("removal_rate", removal_rate)


def _canonicalise_names(df: DataFrame, id_col: str, name_col: str) -> DataFrame:
    """Replace ``name_col`` with the modal normalised spelling per ``id_col``.

    Folds inconsistent spellings/whitespace of the same entity onto one
    canonical name, disambiguated by the stable id. Ids with no name fall back
    to their original (normalised) value.
    """
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    norm = F.trim(F.regexp_replace(F.col(name_col), r"\s+", " "))
    df = df.withColumn(name_col, F.when(norm == "", None).otherwise(norm))

    counts = df.groupBy(id_col, name_col).count().where(F.col(name_col).isNotNull())
    window = Window.partitionBy(id_col).orderBy(F.col("count").desc(), F.col(name_col))
    canonical = (
        counts.withColumn("_rank", F.row_number().over(window))
        .where(F.col("_rank") == 1)
        .select(F.col(id_col), F.col(name_col).alias("_canonical_name"))
    )

    joined = df.join(canonical, on=id_col, how="left")
    return joined.withColumn(
        name_col, F.coalesce(F.col("_canonical_name"), F.col(name_col))
    ).drop("_canonical_name")


def _to_bool(column: str):
    """Cast a "true"/"false" string column to boolean."""
    from pyspark.sql import functions as F

    return (F.lower(F.trim(F.col(column).cast("string"))) == "true").alias(column)


def clean_requests(spark: SparkSession, raw_uri: str) -> DataFrame:
    """Clean the requests table into the documented schema."""
    from pyspark.sql import functions as F

    raw = (
        spark.read.option("header", "true")
        .option("multiLine", "true")
        .option("escape", '"')
        .csv(raw_uri)
    )
    df = _rename(raw, REQUESTS_COLUMN_MAP)

    df = df.withColumn(
        "date", F.to_date(F.to_timestamp(F.col("date"), _SOURCE_TIMESTAMP_FORMAT))
    )
    df = df.withColumn("request_id", F.col("request_id").cast("long"))
    df = df.withColumn("copyright_owner_id", F.col("copyright_owner_id").cast("long"))
    df = df.withColumn("reporting_org_id", F.col("reporting_org_id").cast("long"))
    df = df.select(
        *[c for c in df.columns if c != "from_abuser"], _to_bool("from_abuser")
    )

    df = _canonicalise_names(df, "copyright_owner_id", "copyright_owner")
    df = _canonicalise_names(df, "reporting_org_id", "reporting_org")
    df = _add_url_aggregates(df)

    return df.select(
        "request_id",
        "date",
        "reporting_org_id",
        "reporting_org",
        "copyright_owner_id",
        "copyright_owner",
        "urls_specified",
        "urls_removed",
        "urls_no_action",
        "urls_not_in_index",
        "urls_pending",
        "removal_rate",
        "from_abuser",
        "lumen_url",
    )


def clean_domains(spark: SparkSession, raw_uri: str) -> DataFrame:
    """Clean the domains table (normalise domain strings, coerce counts)."""
    from pyspark.sql import functions as F

    raw = (
        spark.read.option("header", "true")
        .option("multiLine", "true")
        .option("escape", '"')
        .csv(raw_uri)
    )
    df = _rename(raw, DOMAINS_COLUMN_MAP)

    df = df.withColumn("request_id", F.col("request_id").cast("long"))
    domain = F.regexp_replace(F.lower(F.trim(F.col("domain"))), r"\.+$", "")
    df = df.withColumn("domain", F.when(domain == "", None).otherwise(domain))
    df = df.select(
        *[c for c in df.columns if c != "from_abuser"], _to_bool("from_abuser")
    )
    df = _add_url_aggregates(df)

    return df.select(
        "request_id",
        "domain",
        "urls_specified",
        "urls_removed",
        "urls_no_action",
        "urls_not_in_index",
        "urls_pending",
        "removal_rate",
        "from_abuser",
    )


def join_and_persist(
    requests_df: DataFrame, domains_df: DataFrame, out_uri: str
) -> str:
    """Join domains to request-level attributes, persist Parquet, return URI.

    The joined frame is at domain grain (one row per domain per request) with
    request-level context attached, which is the analysis-ready table both the
    triage model and the pirate-naming patterns build on. Request-level count
    columns are prefixed ``request_`` to avoid colliding with the domain counts.
    """
    from pyspark.sql import functions as F

    request_attrs = requests_df.select(
        "request_id",
        "date",
        "reporting_org_id",
        "reporting_org",
        "copyright_owner_id",
        "copyright_owner",
        F.col("urls_specified").alias("request_urls_specified"),
        F.col("urls_removed").alias("request_urls_removed"),
        F.col("removal_rate").alias("request_removal_rate"),
        F.col("from_abuser").alias("request_from_abuser"),
    )

    joined = domains_df.join(request_attrs, on="request_id", how="left")
    joined.write.mode("overwrite").parquet(out_uri)
    return out_uri
