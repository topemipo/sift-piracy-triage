#!/usr/bin/env bash
#
# Create the AWS IAM role that lets Databricks Unity Catalog (serverless) read and
# write the project's external S3 bucket. Free Edition is serverless-only and routes
# all external S3 access through Unity Catalog, which requires an IAM *role* (static
# access keys cannot be registered).
#
# Run this with AWS credentials that can manage IAM (e.g. your admin profile), NOT
# the bucket-scoped sift-app keys. After it succeeds, the Databricks side (storage
# credential is already created; external location + validation) is done over the API.
#
# Reproducible: all workspace-specific values are read from the environment with the
# already-discovered defaults; nothing secret is baked in.
#
# Usage:
#   AWS_PROFILE=admin S3_BUCKET=sift-piracy-data ./scripts/setup_uc_s3_credential.sh
#
set -euo pipefail

# Load .env if present (for S3_BUCKET); IAM-capable AWS creds come from your profile.
if [[ -f .env ]]; then set -a; source .env; set +a; fi
# .env may carry the bucket-scoped sift-app keys; clear them so AWS_PROFILE (admin)
# is honoured for the IAM calls (env access keys otherwise override the profile).
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

BUCKET="${S3_BUCKET:?Set S3_BUCKET (e.g. sift-piracy-data)}"
ROLE_NAME="${UC_ROLE_NAME:-sift-databricks-uc-s3}"
# Discovered from the Databricks workspace (storage credential sift_s3_cred):
UC_MASTER_ROLE_ARN="${UC_MASTER_ROLE_ARN:-arn:aws:iam::414351767826:role/unity-catalog-prod-UCMasterRole-14S5ZJVKOTYTL}"
UC_EXTERNAL_ID="${UC_EXTERNAL_ID:-2e790d89-dc44-4755-83d0-c9391856504d}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo ">> Account ${ACCOUNT_ID}, role ${ROLE_ARN}, bucket ${BUCKET}"

# Initial trust: UC master role only (the role's own ARN can't be referenced until it
# exists). Self-reference is added in the update step below.
cat > "$TMP/trust-initial.json" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UCAssume",
      "Effect": "Allow",
      "Principal": { "AWS": "${UC_MASTER_ROLE_ARN}" },
      "Action": "sts:AssumeRole",
      "Condition": { "StringEquals": { "sts:ExternalId": "${UC_EXTERNAL_ID}" } }
    }
  ]
}
JSON

# Final trust: UC master role AND the role itself (Databricks self-assuming pattern).
cat > "$TMP/trust-final.json" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UCAssume",
      "Effect": "Allow",
      "Principal": { "AWS": ["${UC_MASTER_ROLE_ARN}", "${ROLE_ARN}"] },
      "Action": "sts:AssumeRole",
      "Condition": { "StringEquals": { "sts:ExternalId": "${UC_EXTERNAL_ID}" } }
    }
  ]
}
JSON

# S3 permissions scoped to the one bucket (read for raw, write for processed/sample).
cat > "$TMP/s3-policy.json" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SiftS3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
        "s3:ListBucket", "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET}",
        "arn:aws:s3:::${BUCKET}/*"
      ]
    }
  ]
}
JSON

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo ">> Role exists; updating trust + policy"
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" \
    --policy-document "file://$TMP/trust-final.json"
else
  echo ">> Creating role with initial trust"
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$TMP/trust-initial.json" \
    --description "Unity Catalog access to ${BUCKET} for Sift" >/dev/null
  echo ">> Updating trust to self-assuming form"
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" \
    --policy-document "file://$TMP/trust-final.json"
fi

echo ">> Attaching inline S3 policy"
aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name sift-s3-access --policy-document "file://$TMP/s3-policy.json"

echo ">> Done. Role ARN: ${ROLE_ARN}"
echo ">> IAM propagation can take ~1-2 minutes before Databricks validation passes."
