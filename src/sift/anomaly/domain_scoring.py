"""Early-warning radar: score newly seen domains for piracy risk. (PRD FR-7.x)

Patterns are learned from KNOWN pirate domains in the Google data (high removal
rate), then applied to the live CertStream feed to flag emerging sites before they
are widely reported. Includes burst detection for clusters of similar new domains
appearing close together (e.g. around a fixture).
"""

from __future__ import annotations

import pandas as pd


def fit_pattern_scorer(known_pirate_domains: pd.Series):
    """Learn naming signals (tokens, TLDs, char patterns) from known-bad domains.

    TODO: return a scorer object/callable mapping a domain string -> risk score.
    """
    raise NotImplementedError


def score_domain(scorer, domain: str) -> float:
    """Risk score in [0, 1] for a single new domain. TODO."""
    raise NotImplementedError


def detect_bursts(events: pd.DataFrame, window_minutes: int = 15) -> pd.DataFrame:
    """Flag unusual spikes of similar new domains within a time window.

    TODO: group by time window + token signature, flag counts beyond an expected
    baseline (e.g. z-score / Poisson surprise).
    """
    raise NotImplementedError
