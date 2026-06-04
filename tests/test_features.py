"""Tests for feature engineering. (PRD NFR-2, NFR-3)

The most important tests here guard against TARGET LEAKAGE: a historical-rate
feature for a row must not be influenced by that row's own outcome or any
later row.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sift.features.build_features import (
    add_domain_features,
    add_request_features,
    make_label,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_requests(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal requests DataFrame from a list of dicts."""
    defaults = {
        "request_id": 0,
        "date": "2024-01-01",
        "reporting_org_id": 1,
        "reporting_org": "Org A",
        "copyright_owner_id": 10,
        "copyright_owner": "Owner X",
        "urls_specified": 100,
        "urls_removed": 80,
        "urls_no_action": 10,
        "urls_not_in_index": 10,
        "urls_pending": 0,
        "removal_rate": 0.8,
        "from_abuser": False,
        "lumen_url": "",
    }
    records = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["request_id"] = df["request_id"].astype("int64")
    df["reporting_org_id"] = df["reporting_org_id"].astype("int64")
    df["copyright_owner_id"] = df["copyright_owner_id"].astype("int64")
    for col in (
        "urls_specified",
        "urls_removed",
        "urls_no_action",
        "urls_not_in_index",
        "urls_pending",
    ):
        df[col] = df[col].astype("int32")
    return df


def _make_joined(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal joined (domain-grain) DataFrame."""
    defaults = {
        "request_id": 0,
        "domain": "example.com",
        "urls_specified": 10,
        "urls_removed": 8,
        "urls_no_action": 1,
        "urls_not_in_index": 1,
        "urls_pending": 0,
        "removal_rate": 0.8,
        "from_abuser": False,
        "date": "2024-01-01",
        "reporting_org_id": 1,
        "copyright_owner_id": 10,
    }
    records = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    for col in (
        "urls_specified",
        "urls_removed",
        "urls_no_action",
        "urls_not_in_index",
        "urls_pending",
    ):
        df[col] = df[col].astype("int32")
    return df


# ---------------------------------------------------------------------------
# make_label
# ---------------------------------------------------------------------------


def test_make_label_threshold():
    """removal_rate >= threshold -> 1, below -> 0."""
    df = _make_requests(
        [
            {"removal_rate": 1.0},
            {"removal_rate": 0.5},
            {"removal_rate": 0.49},
            {"removal_rate": 0.0},
        ]
    )
    out = make_label(df, threshold=0.5)
    assert list(out["action"]) == [1, 1, 0, 0]


def test_make_label_null_rate_is_zero():
    """Null removal_rate rows (no URLs specified) are labelled 0."""
    df = _make_requests([{"removal_rate": np.nan}])
    out = make_label(df, threshold=0.5)
    assert out["action"].iloc[0] == 0


def test_make_label_does_not_mutate_input():
    df = _make_requests([{"removal_rate": 0.8}])
    _ = make_label(df, threshold=0.5)
    assert "action" not in df.columns


# ---------------------------------------------------------------------------
# Leakage test — the most critical test in the project
# ---------------------------------------------------------------------------


def test_historical_hit_rate_is_leakage_safe():
    """A row's org_historical_hit_rate must use only strictly-earlier rows.

    Setup: org 1 has three requests in date order:
      2024-01-01: removal_rate=1.0  (row A — first ever, no prior history)
      2024-01-02: removal_rate=0.0  (row B — prior history = row A → mean=1.0)
      2024-01-03: removal_rate=0.5  (row C — prior history = A+B → mean=0.5)

    If there is leakage, row A's feature would be contaminated by B and C
    (mean ≈ 0.5), not null.  Row B would include its own outcome.
    """
    df = _make_requests(
        [
            {"request_id": 1, "date": "2024-01-01", "reporting_org_id": 1, "removal_rate": 1.0},
            {"request_id": 2, "date": "2024-01-02", "reporting_org_id": 1, "removal_rate": 0.0},
            {"request_id": 3, "date": "2024-01-03", "reporting_org_id": 1, "removal_rate": 0.5},
        ]
    )
    out = add_request_features(df).set_index("request_id")

    # Row A: no prior history → must be NaN, not contaminated by B or C.
    assert pd.isna(out.loc[1, "org_historical_hit_rate"]), (
        "First-ever request should have NaN historical rate, got "
        f"{out.loc[1, 'org_historical_hit_rate']}"
    )

    # Row B: only row A is prior → mean = 1.0, not influenced by B itself or C.
    assert out.loc[2, "org_historical_hit_rate"] == pytest.approx(1.0), (
        f"Expected 1.0, got {out.loc[2, 'org_historical_hit_rate']}"
    )

    # Row C: rows A+B are prior → mean = (1.0+0.0)/2 = 0.5.
    assert out.loc[3, "org_historical_hit_rate"] == pytest.approx(0.5), (
        f"Expected 0.5, got {out.loc[3, 'org_historical_hit_rate']}"
    )


def test_same_day_rows_excluded_from_each_others_history():
    """Two requests filed on the same day must not see each other's outcome."""
    df = _make_requests(
        [
            {"request_id": 1, "date": "2024-01-01", "reporting_org_id": 1, "removal_rate": 1.0},
            {"request_id": 2, "date": "2024-01-01", "reporting_org_id": 1, "removal_rate": 0.0},
        ]
    )
    out = add_request_features(df).set_index("request_id")
    # Both rows are on the same day with no prior history → both NaN.
    assert pd.isna(out.loc[1, "org_historical_hit_rate"])
    assert pd.isna(out.loc[2, "org_historical_hit_rate"])


def test_domain_historical_hit_rate_leakage_safe():
    """domain_historical_hit_rate uses only strictly-prior domain appearances."""
    df = _make_joined(
        [
            {"request_id": 1, "date": "2024-01-01", "domain": "pirate.xyz", "removal_rate": 1.0},
            {"request_id": 2, "date": "2024-01-02", "domain": "pirate.xyz", "removal_rate": 0.0},
        ]
    )
    out = add_domain_features(df).set_index("request_id")
    assert pd.isna(out.loc[1, "domain_historical_hit_rate"])
    assert out.loc[2, "domain_historical_hit_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Request features: basic shape and value checks
# ---------------------------------------------------------------------------


def test_add_request_features_columns_present():
    df = _make_requests([{}])
    out = add_request_features(df)
    for col in (
        "urls_log1p",
        "not_in_index_ratio",
        "no_action_ratio",
        "dow",
        "month",
        "org_historical_hit_rate",
        "owner_historical_hit_rate",
    ):
        assert col in out.columns, f"missing column: {col}"


def test_not_in_index_ratio_bounded():
    df = _make_requests([{"urls_specified": 100, "urls_not_in_index": 25}])
    out = add_request_features(df)
    assert 0.0 <= out["not_in_index_ratio"].iloc[0] <= 1.0


def test_zero_urls_specified_no_division_error():
    """urls_specified=0 must not raise and ratios must be 0."""
    df = _make_requests(
        [
            {
                "urls_specified": 0,
                "urls_removed": 0,
                "urls_no_action": 0,
                "urls_not_in_index": 0,
            }
        ]
    )
    out = add_request_features(df)
    assert out["not_in_index_ratio"].iloc[0] == 0.0
    assert out["no_action_ratio"].iloc[0] == 0.0


def test_add_request_features_does_not_mutate():
    df = _make_requests([{}])
    original_cols = set(df.columns)
    _ = add_request_features(df)
    assert set(df.columns) == original_cols


# ---------------------------------------------------------------------------
# Domain features: basic shape and value checks
# ---------------------------------------------------------------------------


def test_add_domain_features_columns_present():
    df = _make_joined([{}])
    out = add_domain_features(df)
    for col in (
        "domain_has_suspicious_token",
        "suspicious_token_count",
        "tld",
        "tld_is_risky",
        "domain_length",
        "digit_ratio",
        "hyphen_count",
        "domain_historical_hit_rate",
    ):
        assert col in out.columns, f"missing column: {col}"


def test_pirate_domain_flagged():
    df = _make_joined([{"domain": "rojadirecta-live.xyz"}])
    out = add_domain_features(df)
    assert out["domain_has_suspicious_token"].iloc[0] == 1
    assert out["tld"].iloc[0] == "xyz"
    assert out["tld_is_risky"].iloc[0] == 1
    assert out["hyphen_count"].iloc[0] == 1


def test_benign_domain_not_flagged():
    df = _make_joined([{"domain": "bbc.co.uk"}])
    out = add_domain_features(df)
    assert out["domain_has_suspicious_token"].iloc[0] == 0
    assert out["tld_is_risky"].iloc[0] == 0


def test_suspicious_token_count_correct():
    df = _make_joined([{"domain": "live-sport-stream.xyz"}])
    out = add_domain_features(df)
    # "live", "sport", "stream" all present
    assert out["suspicious_token_count"].iloc[0] >= 3


def test_add_domain_features_does_not_mutate():
    df = _make_joined([{}])
    original_cols = set(df.columns)
    _ = add_domain_features(df)
    assert set(df.columns) == original_cols
