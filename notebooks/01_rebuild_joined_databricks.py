# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Rebuild joined tables only
# MAGIC
# MAGIC Use this when the cleaned `processed/requests` and `processed/domains` tables
# MAGIC already exist, but the joined schema needs to be regenerated.
# MAGIC
# MAGIC This skips the expensive raw CSV read/clean/count path in
# MAGIC `00_ingest_databricks.py`. It only reads cleaned Parquet, applies the explicit
# MAGIC `domain_*` / `request_*` aliases, and overwrites:
# MAGIC
# MAGIC - `s3://<bucket>/processed/joined`
# MAGIC - `s3://<bucket>/sample/joined`
# MAGIC
# MAGIC By default it rebuilds the full joined table. To refresh only the sample joined
# MAGIC table, set `REBUILD_FULL_JOINED=false` in the Databricks environment.

# COMMAND ----------

import os

from pyspark.sql import functions as F  # noqa: F401

S3_BUCKET = os.environ.get("S3_BUCKET", "sift-piracy-data")
PROCESSED = f"s3://{S3_BUCKET}/processed"
SAMPLE = f"s3://{S3_BUCKET}/sample"
SAMPLE_ROWS = int(os.environ.get("LOCAL_SAMPLE_ROWS", "200000"))
RANDOM_SEED = int(os.environ.get("RANDOM_SEED", "42"))
REBUILD_FULL_JOINED = os.environ.get("REBUILD_FULL_JOINED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

print(
    f"S3_BUCKET={S3_BUCKET}  "
    f"REBUILD_FULL_JOINED={REBUILD_FULL_JOINED}  "
    f"SAMPLE_ROWS={SAMPLE_ROWS:,}"
)

# COMMAND ----------

requests = spark.read.parquet(f"{PROCESSED}/requests")  # noqa: F821
domains = spark.read.parquet(f"{PROCESSED}/domains")  # noqa: F821

print(f"requests={requests.count():,}")
print(f"domains={domains.count():,}")

# COMMAND ----------

request_attrs = requests.select(
    "request_id",
    "date",
    "reporting_org_id",
    "reporting_org",
    "copyright_owner_id",
    "copyright_owner",
    F.col("urls_specified").alias("request_urls_specified"),
    F.col("urls_removed").alias("request_urls_removed"),
    F.col("urls_no_action").alias("request_urls_no_action"),
    F.col("urls_not_in_index").alias("request_urls_not_in_index"),
    F.col("urls_pending").alias("request_urls_pending"),
    F.col("removal_rate").alias("request_removal_rate"),
    F.col("from_abuser").alias("request_from_abuser"),
)

domain_attrs = domains.select(
    "request_id",
    "domain",
    F.col("urls_specified").alias("domain_urls_specified"),
    F.col("urls_removed").alias("domain_urls_removed"),
    F.col("urls_no_action").alias("domain_urls_no_action"),
    F.col("urls_not_in_index").alias("domain_urls_not_in_index"),
    F.col("urls_pending").alias("domain_urls_pending"),
    F.col("removal_rate").alias("domain_removal_rate"),
    F.col("from_abuser").alias("domain_from_abuser"),
)

# COMMAND ----------

if REBUILD_FULL_JOINED:
    joined = domain_attrs.join(request_attrs, on="request_id", how="left")
    joined.write.mode("overwrite").parquet(f"{PROCESSED}/joined")
    print(f"wrote full joined table -> {PROCESSED}/joined")
else:
    print("skipped full joined rebuild")

# COMMAND ----------

try:
    sample_requests = spark.read.parquet(f"{SAMPLE}/requests")  # noqa: F821
    print(f"using existing sample requests -> {SAMPLE}/requests")
except Exception:
    print("sample requests missing; creating a fresh request sample")
    frac = min(1.0, SAMPLE_ROWS / max(requests.count(), 1))
    sample_requests = (
        requests.sample(withReplacement=False, fraction=frac, seed=RANDOM_SEED)
        .limit(SAMPLE_ROWS)
    )
    sample_requests.write.mode("overwrite").parquet(f"{SAMPLE}/requests")

sampled_ids = sample_requests.select("request_id").distinct()

sample_joined = (
    domain_attrs.join(sampled_ids, on="request_id", how="inner")
    .join(request_attrs, on="request_id", how="left")
)
sample_joined.write.mode("overwrite").parquet(f"{SAMPLE}/joined")
print(f"wrote sample joined table -> {SAMPLE}/joined")

# COMMAND ----------

check = spark.read.parquet(f"{SAMPLE}/joined")  # noqa: F821
check.printSchema()

ambiguous = {"urls_specified", "urls_removed", "removal_rate", "from_abuser"}.intersection(
    set(check.columns)
)
if ambiguous:
    raise RuntimeError(f"sample/joined still has ambiguous columns: {sorted(ambiguous)}")

required = {
    "domain_urls_specified",
    "domain_removal_rate",
    "domain_from_abuser",
    "request_urls_specified",
    "request_removal_rate",
    "request_from_abuser",
}
missing = required.difference(set(check.columns))
if missing:
    raise RuntimeError(f"sample/joined missing required prefixed columns: {sorted(missing)}")

print("joined schema repair complete")
