# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Clean the Google copyright data (runs on Databricks)
# MAGIC
# MAGIC **Ingest is done first, off-cluster:** the raw CSVs are streamed straight from
# MAGIC the local zip into S3 by `scripts/stage_zip_to_s3.sh` (no unzip, nothing large
# MAGIC on the laptop). They land gzipped at `s3://<bucket>/raw/*.csv.gz`.
# MAGIC
# MAGIC This notebook starts from S3: read the gzipped CSVs with Spark, clean, derive
# MAGIC the label, join, and write Parquet back to S3 plus a small sample for the
# MAGIC local dashboard. The ~75GB unzipped data is never materialised anywhere.
# MAGIC
# MAGIC This is a stub. Claude Code fills in the TODOs in Phase 1.

# COMMAND ----------

# MAGIC %md ## 1. Configuration

# COMMAND ----------

import os

S3_BUCKET = os.environ.get("S3_BUCKET", "sift-piracy-data")
RAW = f"s3a://{S3_BUCKET}/raw"
PROCESSED = f"s3a://{S3_BUCKET}/processed"
SAMPLE = f"s3a://{S3_BUCKET}/sample"

# TODO: configure Spark to read+write S3 (spark.hadoop.fs.s3a.access.key / secret.key,
#       or an instance profile). Spark reads .csv.gz natively (gzip is not splittable,
#       which is fine for a one-off clean).

# COMMAND ----------

# MAGIC %md ## 2. Read raw gzipped CSVs from S3

# COMMAND ----------

# TODO:
#   - read f"{RAW}/requests.csv.gz" and f"{RAW}/domains.csv.gz" with header=True
#   - map the real column names (see {RAW}/README.txt) to the snake_case schema in
#     src/sift/processing/data_dictionary.md
#   - NOTE: urls-no-action-taken.csv (39GB) is intentionally NOT ingested for v1.

# COMMAND ----------

# MAGIC %md ## 3. Clean, label and join

# COMMAND ----------

# Reuse the project's cleaning logic (attach the repo via Databricks Repos first):
# from sift.processing.clean_spark import clean_requests, clean_domains, join_and_persist
#
# TODO:
#   - clean (parse dates, coerce URL counts to int, normalise + dedupe org/owner names,
#     lowercase domains)
#   - derive removal_rate safely (guard divide-by-zero)
#   - join on request_id

# COMMAND ----------

# MAGIC %md ## 4. Write Parquet + a small sample back to S3

# COMMAND ----------

# TODO:
#   - write cleaned Parquet to PROCESSED
#   - write a small sample (config storage.local_sample_rows) to SAMPLE for the
#     local Streamlit dashboard

# COMMAND ----------

# MAGIC %md
# MAGIC **Output:** cleaned Parquet in `processed/` and a small `sample/` extract.
# MAGIC Nothing large remains on the cluster or the laptop.
