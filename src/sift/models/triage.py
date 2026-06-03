"""Triage model: predict probability a takedown candidate will be actioned.
(PRD FR-5.x)

Two approaches for comparison:
  - baseline: interpretable logistic regression (statistical modelling)
  - challenger: gradient-boosted trees (XGBoost)
Output probabilities must be calibrated, and per-prediction feature contributions
exposed so the dashboard can explain WHY a candidate ranks highly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TriageModel:
    """Wraps a fitted estimator + the feature columns it expects."""

    estimator: object
    feature_cols: list[str]
    calibrated: bool = False

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        """Return calibrated probability of action for each row. TODO."""
        raise NotImplementedError

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return top feature contributions per row for the dashboard. TODO."""
        raise NotImplementedError


def train_baseline(X: pd.DataFrame, y: pd.Series) -> TriageModel:
    """Fit logistic regression (+ calibration). TODO."""
    raise NotImplementedError


def train_challenger(X: pd.DataFrame, y: pd.Series) -> TriageModel:
    """Fit XGBoost (+ calibration). TODO."""
    raise NotImplementedError
