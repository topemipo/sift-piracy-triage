"""Feature engineering for the triage model. (PRD FR-4.x)

CRITICAL — leakage control (FR-4.3): any feature that uses historical outcomes
(e.g. a requester's past hit rate) must be computed using ONLY rows strictly before
the current row's date. Build these as time-ordered expanding aggregates, never over
the whole dataset.

The functions here operate on a pandas DataFrame sourced from the cleaned
``sample/joined`` Parquet (or the full ``processed/joined`` on a large machine).
Every function is a pure transform: it returns a new DataFrame with extra columns
added, never mutating the input.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import tldextract

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tokens that hint at piracy in a domain name (from config.yaml; refined later
# in Phase 5 from what the historical data actually shows).
DEFAULT_SUSPICIOUS_TOKENS: tuple[str, ...] = (
    "stream",
    "live",
    "hd",
    "sport",
    "sports",
    "futbol",
    "foot",
    "match",
    "tv",
    "watch",
    "free",
)

# TLDs over-represented in the known pirate domain list (from config.yaml).
RISKY_TLDS: frozenset[str] = frozenset(
    ["xyz", "ru", "su", "top", "cc", "sbs", "club", "online", "stream"]
)

_NON_ALPHA_RE = re.compile(r"[^a-z]")


# ---------------------------------------------------------------------------
# Request-level features  (FR-4.1)
# ---------------------------------------------------------------------------


def add_request_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add request-level features; return augmented DataFrame.

    Features added
    --------------
    urls_log1p : log1p(urls_specified) — compresses the heavy right tail.
    not_in_index_ratio : urls_not_in_index / urls_specified — proxy for
        "URL was already removed / never existed"; high ratio → noise.
    no_action_ratio : urls_no_action / urls_specified — direct noise signal.
    dow : day-of-week (0=Mon … 6=Sun) — filing patterns vary by day.
    month : calendar month (1–12) — seasonality around major sports events.
    org_historical_hit_rate : the reporting organisation's mean removal_rate
        on all requests filed **strictly before** this row's date.
        Null for a requester's very first request (no history yet).
    owner_historical_hit_rate : same logic for the copyright owner.

    Leakage guarantee
    -----------------
    The historical-rate features are built with a date-ordered expanding
    merge: for each row dated D, we average removal_rate over all rows where
    date < D (strictly less), grouped by org / owner id.  The current row's
    outcome never enters its own feature.
    """
    df = df.copy()

    # --- Date parsing ---
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)

    # --- Simple numeric features ---
    df["urls_log1p"] = np.log1p(df["urls_specified"].clip(lower=0))
    specified = df["urls_specified"].replace(0, np.nan)
    df["not_in_index_ratio"] = (df["urls_not_in_index"] / specified).fillna(0.0)
    df["no_action_ratio"] = (df["urls_no_action"] / specified).fillna(0.0)

    # --- Calendar features ---
    df["dow"] = df["date"].dt.dayofweek.astype("int8")
    df["month"] = df["date"].dt.month.astype("int8")

    # --- Leakage-safe historical hit rates ---
    df = _add_historical_hit_rate(
        df,
        group_col="reporting_org_id",
        new_col="org_historical_hit_rate",
    )
    df = _add_historical_hit_rate(
        df,
        group_col="copyright_owner_id",
        new_col="owner_historical_hit_rate",
    )

    return df


def _add_historical_hit_rate(
    df: pd.DataFrame,
    group_col: str,
    new_col: str,
) -> pd.DataFrame:
    """Add a leakage-safe expanding mean of ``removal_rate`` grouped by ``group_col``.

    For each row at position i (ordered by date), the value is the mean of
    ``removal_rate`` for all rows with the same ``group_col`` value whose
    ``date`` is **strictly earlier** than row i's date.

    Rows tied on the same date contribute to each other's history only if
    they were sorted before the current row — which is ambiguous for same-day
    ties.  We conservatively exclude all same-day rows from a row's own
    history, so the feature is always strictly-prior.

    Implementation
    --------------
    Sort by date, compute a cumulative sum/count grouped by ``group_col``,
    then subtract the current day's contribution before dividing.  This is
    O(n log n) and avoids any lookahead.
    """
    # Work on a sorted copy; keep the original index to merge back.
    work = df[["date", group_col, "removal_rate"]].copy()
    work = work.sort_values("date", kind="stable")

    # Per-group cumulative sum and count (includes current row).
    work["_cum_sum"] = work.groupby(group_col)["removal_rate"].cumsum()
    work["_cum_cnt"] = work.groupby(group_col).cumcount() + 1

    # Per-group, per-date totals: sum and count of ALL rows on the same date.
    day_totals = (
        work.groupby([group_col, "date"])["removal_rate"]
        .agg(day_sum="sum", day_cnt="count")
        .reset_index()
    )
    work = work.merge(day_totals, on=[group_col, "date"], how="left")

    # Strictly-prior = cumulative up to and including today, minus today's rows.
    prior_sum = work["_cum_sum"] - work["day_sum"]
    prior_cnt = work["_cum_cnt"] - work["day_cnt"]

    work[new_col] = np.where(prior_cnt > 0, prior_sum / prior_cnt, np.nan)

    # Merge back on original index.
    df = df.copy()
    df[new_col] = work[new_col].values
    return df


# ---------------------------------------------------------------------------
# Domain-level features  (FR-4.2)
# ---------------------------------------------------------------------------


def add_domain_features(
    df: pd.DataFrame,
    suspicious_tokens: tuple[str, ...] = DEFAULT_SUSPICIOUS_TOKENS,
) -> pd.DataFrame:
    """Add domain-level features; return augmented DataFrame.

    Features added
    --------------
    domain_has_suspicious_token : 1 if any token in ``suspicious_tokens``
        appears as a word-boundary substring of the domain name.
    suspicious_token_count : number of distinct tokens matched.
    tld : registered suffix extracted by tldextract (e.g. ``'xyz'``).
    tld_is_risky : 1 if TLD is in ``RISKY_TLDS``.
    domain_length : character count of the full domain string.
    digit_ratio : fraction of characters in the domain that are digits.
    hyphen_count : number of hyphens (pirate domains often hyphenate).
    domain_historical_hit_rate : leakage-safe expanding mean removal_rate
        for this exact domain across all **strictly-earlier** appearances.
        Null on first appearance.

    Note: ``date`` must be present (join from requests before calling this).
    """
    df = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)

    domain_lower = df["domain"].fillna("").str.lower()

    # --- Naming-pattern features ---
    token_pattern = "|".join(re.escape(t) for t in suspicious_tokens)
    df["domain_has_suspicious_token"] = domain_lower.str.contains(
        token_pattern, regex=True, na=False
    ).astype("int8")
    df["suspicious_token_count"] = domain_lower.apply(
        lambda d: sum(1 for t in suspicious_tokens if t in d)
    ).astype("int8")

    # --- TLD features ---
    parsed = domain_lower.apply(lambda d: tldextract.extract(d))
    df["tld"] = parsed.apply(lambda e: e.suffix or "")
    df["tld_is_risky"] = df["tld"].isin(RISKY_TLDS).astype("int8")

    # --- Structural features ---
    df["domain_length"] = domain_lower.str.len().astype("int16")
    df["digit_ratio"] = domain_lower.apply(
        lambda d: (sum(c.isdigit() for c in d) / len(d)) if d else 0.0
    )
    df["hyphen_count"] = domain_lower.str.count("-").astype("int8")

    # --- Leakage-safe domain targeting frequency ---
    df = _add_historical_hit_rate(
        df,
        group_col="domain",
        new_col="domain_historical_hit_rate",
    )

    return df


# ---------------------------------------------------------------------------
# Label  (FR-5.1)
# ---------------------------------------------------------------------------


def make_label(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Add binary ``action`` label: 1 if ``removal_rate >= threshold`` else 0.

    Rows where ``removal_rate`` is null (no URLs were specified) are labelled
    0 (treat as non-actionable rather than dropping them).
    """
    df = df.copy()
    df["action"] = (df["removal_rate"].fillna(0.0) >= threshold).astype("int8")
    return df
