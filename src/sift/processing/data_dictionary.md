# Data dictionary — cleaned dataset

This documents the analysis-ready dataset produced by `clean_spark.py`. Fill in /
correct against the real README that ships with the Google download.

## requests (one row per removal request)

| Column | Type | Description |
|---|---|---|
| request_id | int | Unique request identifier. Join key to `domains`. |
| date | date | Date the request was filed. Drives the temporal split. |
| reporting_org | string | Agent who filed the request (normalised). |
| copyright_owner | string | Rights holder (normalised). |
| urls_specified | int | Total URLs in the request. |
| urls_removed | int | URLs Google actioned. |
| urls_no_action | int | URLs Google declined to action. |
| urls_not_in_index | int | URLs not in Google's index. |
| removal_rate | float | urls_removed / urls_specified. The model's label source. |

## domains (one row per domain per request)

| Column | Type | Description |
|---|---|---|
| request_id | int | Join key to `requests`. |
| domain | string | Targeted domain (normalised, lowercased). |
| urls_specified | int | URLs requested for this domain. |
| urls_removed | int | URLs actioned for this domain. |
| pct_of_domain | string | Share of the domain targeted (banded, e.g. `<1%`, `<10%`). |
| removal_rate | float | urls_removed / urls_specified for this domain. |

## Notes
- Exact source column names must be confirmed against the downloaded README and
  mapped to the snake_case names above in `clean_spark.py`.
- `removal_rate` and the `action` label (rate >= ACTION_THRESHOLD) are derived, not
  raw.
