"""Budget-constrained takedown selection. (PRD FR-6.x)

Turns model scores into an action plan. Given each candidate's probability of action
(p), an importance weight (w) and a cost (minutes), and a total time budget, select
the subset of candidates that maximises total expected value:

    maximise  sum_i  (p_i * w_i)            [expected value]
    subject to sum_i (cost_i) <= budget     [analyst time]
    x_i in {0, 1}

This is a 0/1 knapsack. Provide both:
  - greedy ranking by value-per-minute (the naive analyst behaviour, and a baseline)
  - an optimal/near-optimal solver (DP for integer costs, or scipy.optimize.milp)
and report the difference in expected value captured (the win).
"""

from __future__ import annotations

import pandas as pd


def expected_value(df: pd.DataFrame, prob_col: str, weight_col: str) -> pd.Series:
    """Per-candidate expected value = probability * importance weight. TODO."""
    raise NotImplementedError


def greedy_select(df: pd.DataFrame, budget_minutes: float, cost_minutes: float) -> pd.DataFrame:
    """Naive baseline: sort by value-per-minute, take until budget exhausted. TODO."""
    raise NotImplementedError


def optimal_select(df: pd.DataFrame, budget_minutes: float, cost_minutes: float) -> pd.DataFrame:
    """Knapsack-optimal selection. TODO (DP or scipy.optimize.milp)."""
    raise NotImplementedError
