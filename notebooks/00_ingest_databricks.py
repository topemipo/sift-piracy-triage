# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Clean the Google copyright data (runs on Databricks serverless)
# MAGIC
# MAGIC **Ingest is done first, off-cluster:** the raw CSVs were streamed straight from
# MAGIC the local zip into S3 by `scripts/stage_zip_to_s3.sh`.
# MAGIC They land gzipped at `s3://<bucket>/raw/*.csv.gz`.
# MAGIC
# MAGIC This notebook starts from S3: read the gzipped CSVs with Spark, clean, derive
# MAGIC the label, join, and write Parquet back to S3 plus a small sample for the
# MAGIC local dashboard. The ~75 GB unzipped data is never materialised anywhere.
# MAGIC
# MAGIC **S3 access:** handled by the Unity Catalog external location `sift_piracy_data`
# MAGIC (credential `sift_s3_cred`). Paths use the `s3://` scheme; no static AWS keys
# MAGIC or Hadoop config are needed on serverless.
# MAGIC
# MAGIC **To run:** Connect → Serverless, then Run all.

# COMMAND ----------

# MAGIC %md ## 0. Install the sift package
# MAGIC
# MAGIC The wheel was built locally and uploaded to the UC volume
# MAGIC `workspace.default.sift_libs`. Installed via `subprocess` (not `%pip`) so the
# MAGIC kernel is **not** restarted and "Run all" works in a single pass.

# COMMAND ----------

import importlib
import subprocess
import sys

# Install via subprocess rather than %pip so the kernel is NOT restarted.
# %pip triggers a kernel restart on first install, which breaks "Run All".
# subprocess.run installs into the running interpreter without any restart.
if importlib.util.find_spec("sift") is None:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install",
         "/Volumes/workspace/default/sift_libs/sift-0.1.0-py3-none-any.whl", "--quiet"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pip install failed:\n{result.stderr}")
    # Make the newly installed package importable in this interpreter session.
    importlib.invalidate_caches()
    print("sift installed")
else:
    print("sift already installed, skipping")

# COMMAND ----------

# MAGIC %md ## 1. Configuration

# COMMAND ----------

import os

S3_BUCKET = os.environ.get("S3_BUCKET", "sift-piracy-data")
# Serverless + UC: use s3:// — Unity Catalog handles credentials via sift_s3_cred.
RAW = f"s3://{S3_BUCKET}/raw"
PROCESSED = f"s3://{S3_BUCKET}/processed"
SAMPLE = f"s3://{S3_BUCKET}/sample"

# Max rows per local-dashboard sample extract (mirrors config.yaml storage.local_sample_rows).
SAMPLE_ROWS = int(os.environ.get("LOCAL_SAMPLE_ROWS", "200000"))
RANDOM_SEED = int(os.environ.get("RANDOM_SEED", "42"))

print(f"S3_BUCKET={S3_BUCKET}  RAW={RAW}  SAMPLE_ROWS={SAMPLE_ROWS}")

# COMMAND ----------

# MAGIC %md ## 2. Read, clean, label and join

# COMMAND ----------

from sift.processing.clean_spark import clean_domains, clean_requests, join_and_persist

requests_clean = clean_requests(spark, f"{RAW}/requests.csv.gz")  # noqa: F821
domains_clean = clean_domains(spark, f"{RAW}/domains.csv.gz")      # noqa: F821

# Note: .cache() / PERSIST TABLE is not supported on Databricks serverless.
# This is a one-shot clean job so re-scanning the S3 source across the count
# and write actions is acceptable.

# COMMAND ----------

# MAGIC %md ## 3. Log row counts before/after (data-quality evidence)

# COMMAND ----------

def read_google_csv(uri):
    return (
        spark.read.option("header", "true")  # noqa: F821
        .option("multiLine", "true")
        .option("escape", '"')
        .csv(uri)
    )


raw_requests_rows = (
    read_google_csv(f"{RAW}/requests.csv.gz").count()
)
raw_domains_rows = (
    read_google_csv(f"{RAW}/domains.csv.gz").count()
)
clean_requests_rows = requests_clean.count()
clean_domains_rows = domains_clean.count()

print(f"requests: raw={raw_requests_rows:,} -> clean={clean_requests_rows:,}")
print(f"domains:  raw={raw_domains_rows:,} -> clean={clean_domains_rows:,}")

# COMMAND ----------

# MAGIC %md ## 4. Write cleaned Parquet to S3

# COMMAND ----------

requests_clean.write.mode("overwrite").parquet(f"{PROCESSED}/requests")
domains_clean.write.mode("overwrite").parquet(f"{PROCESSED}/domains")
joined_uri = join_and_persist(requests_clean, domains_clean, f"{PROCESSED}/joined")
print(f"wrote joined analysis table -> {joined_uri}")

# COMMAND ----------

# MAGIC %md ## 5. Write small samples back to S3 for the local dashboard

# COMMAND ----------

frac = min(1.0, SAMPLE_ROWS / max(clean_requests_rows, 1))
requests_sample = (
    requests_clean.sample(withReplacement=False, fraction=frac, seed=RANDOM_SEED)
    .limit(SAMPLE_ROWS)
)
sampled_ids = requests_sample.select("request_id")
domains_sample = domains_clean.join(sampled_ids, on="request_id", how="inner")
joined_sample = (
    spark.read.parquet(f"{PROCESSED}/joined")  # noqa: F821
    .join(sampled_ids, on="request_id", how="inner")
)

requests_sample.write.mode("overwrite").parquet(f"{SAMPLE}/requests")
domains_sample.write.mode("overwrite").parquet(f"{SAMPLE}/domains")
joined_sample.write.mode("overwrite").parquet(f"{SAMPLE}/joined")
print(f"wrote samples (target {SAMPLE_ROWS:,} requests) -> {SAMPLE}/")

# COMMAND ----------

# MAGIC %md
# MAGIC **Output:** cleaned Parquet in `processed/` (requests, domains, joined) and a
# MAGIC small `sample/` extract. Nothing large remains on the cluster or the laptop.
