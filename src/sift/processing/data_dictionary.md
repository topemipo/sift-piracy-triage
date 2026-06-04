# Data dictionary — cleaned dataset

This documents the analysis-ready dataset produced by `clean_spark.py`, mapped
from the **real** source columns in the Google Transparency Report download
(confirmed against `raw/README.txt` and the CSV headers staged in S3).

## Source → cleaned column mapping

The source has **no "URLs specified" column** and the domains file has **no
"% of domain" column** — both were assumed by an earlier draft. Instead the
source reports four mutually-exclusive outcome buckets per request/domain. We
derive `urls_specified` as their sum and `removal_rate` from it.

### requests.csv (source columns)

| Source column | Cleaned column | Type |
|---|---|---|
| `Request ID` | `request_id` | long |
| `Date` | `date` | date (parsed from ISO 8601 `…Z`) |
| `Lumen URL` | `lumen_url` | string |
| `Copyright owner ID` | `copyright_owner_id` | long |
| `Copyright owner name` | `copyright_owner` | string (canonicalised) |
| `Reporting organization ID` | `reporting_org_id` | long |
| `Reporting organization name` | `reporting_org` | string (canonicalised) |
| `URLs removed` | `urls_removed` | int |
| `URLs that were not in Google's search index` | `urls_not_in_index` | int |
| `URLs for which we took no action` | `urls_no_action` | int |
| `URLs pending review` | `urls_pending` | int |
| `From Abuser` | `from_abuser` | bool |

### domains.csv (source columns)

| Source column | Cleaned column | Type |
|---|---|---|
| `Request ID` | `request_id` | long |
| `Domain` | `domain` | string (lowercased, trimmed) |
| `URLs removed` | `urls_removed` | int |
| `URLs that were not in Google's search index` | `urls_not_in_index` | int |
| `URLs for which we took no action` | `urls_no_action` | int |
| `URLs pending review` | `urls_pending` | int |
| `From Abuser` | `from_abuser` | bool |

## Cleaned tables

### requests (one row per removal request)

| Column | Type | Description |
|---|---|---|
| request_id | long | Unique request identifier. Join key to `domains`. |
| date | date | Date the request was filed (UTC). Drives the temporal split. |
| reporting_org_id | long | Stable id of the reporting organisation. |
| reporting_org | string | Reporting organisation, canonicalised to the modal spelling per id. |
| copyright_owner_id | long | Stable id of the copyright owner. |
| copyright_owner | string | Rights holder, canonicalised to the modal spelling per id. |
| urls_specified | int | Derived: `urls_removed + urls_not_in_index + urls_no_action + urls_pending`. |
| urls_removed | int | URLs Google actioned. Label numerator. |
| urls_no_action | int | URLs Google declined to action. Noise signal. |
| urls_not_in_index | int | URLs not in Google's index. Data-quality signal. |
| urls_pending | int | URLs still pending review at extract time. |
| removal_rate | float | `urls_removed / urls_specified`, clamped to [0, 1]; null when nothing specified. The model's label source. |
| from_abuser | bool | Google's flag that the filer is believed to be abusing the process. Strong noise signal. |
| lumen_url | string | Link to the Lumen notice documenting the request. |

### domains (one row per domain per request)

| Column | Type | Description |
|---|---|---|
| request_id | long | Join key to `requests`. |
| domain | string | Targeted domain (normalised, lowercased, trailing dot stripped). |
| urls_specified | int | Derived sum of the four outcome buckets for this domain. |
| urls_removed | int | URLs actioned for this domain. |
| urls_no_action | int | URLs not actioned for this domain. |
| urls_not_in_index | int | URLs not in Google's index for this domain. |
| urls_pending | int | URLs pending review for this domain. |
| removal_rate | float | `urls_removed / urls_specified` for this domain, clamped to [0, 1]; null when nothing specified. |
| from_abuser | bool | Abuser flag carried at domain grain. |

### joined (analysis-ready, one row per domain per request)

The domains table left-joined to request-level context. Domain-level count
columns keep their names; request-level counts are prefixed `request_` to avoid
collision.

| Column | Type | Description |
|---|---|---|
| request_id, domain, urls_specified, urls_removed, urls_no_action, urls_not_in_index, urls_pending, removal_rate, from_abuser | — | As in `domains`. |
| date | date | Request date (for the temporal split). |
| reporting_org_id, reporting_org | long, string | Reporting organisation. |
| copyright_owner_id, copyright_owner | long, string | Copyright owner. |
| request_urls_specified | int | Request-level URLs specified. |
| request_urls_removed | int | Request-level URLs removed. |
| request_removal_rate | float | Request-level removal rate. |
| request_from_abuser | bool | Request-level abuser flag. |

## Notes
- `urls_specified` and `removal_rate` are derived, not raw; the `action` label
  (`removal_rate >= ACTION_THRESHOLD`) is derived in feature engineering (Phase 2).
- `removal_rate` is clamped to [0, 1] and is null when `urls_specified == 0`
  (divide-by-zero guarded).
- Organisation and owner names are deduplicated by choosing the modal spelling
  for each stable id, which resolves inconsistent casing/whitespace variants.
