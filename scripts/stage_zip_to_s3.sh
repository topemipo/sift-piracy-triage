#!/usr/bin/env bash
#
# Stream the Google copyright CSVs straight from the local zip into S3, WITHOUT
# unzipping. The laptop is only a pass-through pipe: unzip -p decompresses one member
# to stdout, gzip shrinks it, aws s3 cp - uploads it via multipart. Nothing large is
# ever written to local disk.
#
# Unzipped the dataset is ~75GB; this script never materialises any of it.
#
# Prereqs: awscli installed and configured (aws configure), and the bucket exists.
#
# Usage:
#   ./scripts/stage_zip_to_s3.sh /path/to/google-websearch-copyright-removals.zip s3://sift-piracy-data/raw
#   ./scripts/stage_zip_to_s3.sh /path/to/archive.zip s3://bucket/raw --include-no-action
#
set -euo pipefail

ZIP="${1:?Pass the path to the .zip as the first argument}"
DEST="${2:?Pass the S3 destination prefix, e.g. s3://bucket/raw}"
INCLUDE_NO_ACTION="${3:-}"

INNER="google-websearch-copyright-removals"   # folder name inside the zip

# Bigger multipart chunks = fewer parts for the large gzipped streams.
aws configure set default.s3.multipart_chunksize 64MB

stage() {   # stage <member-filename>
  local name="$1"
  echo ">> streaming ${name} -> ${DEST}/${name}.gz (no local unzip)"
  unzip -p "$ZIP" "${INNER}/${name}" | gzip | aws s3 cp - "${DEST}/${name}.gz"
}

# README (tiny, uncompressed) so the real column docs live in S3 too.
echo ">> staging README.txt"
unzip -p "$ZIP" "${INNER}/README.txt" | aws s3 cp - "${DEST}/README.txt"

# Core files needed for v1.
stage "requests.csv"     # ~5.9GB  -> request-level label + features
stage "domains.csv"      # ~30GB   -> domain-level features + pirate naming patterns

# Optional: the 39GB per-URL no-action file. Not needed for v1.
if [[ "$INCLUDE_NO_ACTION" == "--include-no-action" ]]; then
  stage "urls-no-action-taken.csv"
fi

echo ">> done. Listing destination:"
aws s3 ls "${DEST}/"
