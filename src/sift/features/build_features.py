"""Feature engineering for the triage model. (PRD FR-4.x)

CRITICAL — leakage control (FR-4.3): any feature that uses historical outcomes
(e.g. a requester's past hit rate) must be computed using ONLY rows strictly before
the current row's date. Build these as time-ordered expanding aggregates, never over
the whole dataset.
"""

from __future__ import annotations

import pandas as pd

# Tokens that hint at piracy in a domain name; refined from data in Phase 5.
DEFAULT_SUSPICIOUS_TOKENS = (
    "stream", "live", "hd", "sport", "sports", "match", "tv", "watch", "free",
)


def add_request_features(df: pd.DataFrame) -> pd.DataFrame:
    """Request-level features.

    TODO:
      - categorical encodings for reporting_org, copyright_owner
      - url counts and ratios (e.g. not_in_index / specified)
      - day-of-week / month from date
      - requester historical hit rate (LEAKAGE-SAFE expanding mean)
    """
    raise NotImplementedError


def add_domain_features(df: pd.DataFrame, suspicious_tokens=DEFAULT_SUSPICIOUS_TOKENS) -> pd.DataFrame:
    """Domain-level features.

    TODO:
      - token flags (suspicious_tokens present in domain)
      - TLD extraction + risk flag
      - domain length / digit ratio / hyphen count
      - historical targeting frequency (LEAKAGE-SAFE)
    """
    raise NotImplementedError


def make_label(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Add binary `action` label: 1 if removal_rate >= threshold else 0. (FR-5.1)"""
    raise NotImplementedError
