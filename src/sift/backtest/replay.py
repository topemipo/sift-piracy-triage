"""Temporal backtest + replay engine. (PRD FR-8.x)

This is how Sift is evaluated honestly without a live deployment: train only on
data before a cutoff, then replay a strictly-later period in time order, scoring and
ranking candidates with outcomes hidden, and only then revealing the real outcomes
to grade the ranking.

The same engine drives the dashboard "replay mode" — it looks live, but underneath
it is a rigorous backtest.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pandas as pd


def temporal_split(df: pd.DataFrame, cutoff_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into train (date < cutoff) and holdout (date >= cutoff). TODO."""
    raise NotImplementedError


@dataclass
class ReplayStep:
    timestamp: pd.Timestamp
    ranked_candidates: pd.DataFrame   # scored + ranked, outcomes hidden during ranking
    revealed_outcomes: pd.DataFrame   # the real outcomes, for scoring after the fact


def replay(holdout: pd.DataFrame, model, step: str = "1D") -> Iterator[ReplayStep]:
    """Yield ReplayStep objects walking the holdout period in time order. TODO."""
    raise NotImplementedError


def precision_at_k(ranked: pd.DataFrame, outcome_col: str, ks: list[int]) -> dict[int, float]:
    """Headline metric: of the top K recommended, share genuinely actioned. TODO."""
    raise NotImplementedError
