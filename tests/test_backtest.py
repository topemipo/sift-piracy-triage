"""Tests for the backtest engine. (PRD FR-8.x)"""

import pytest


@pytest.mark.skip(reason="implement in Phase 4")
def test_temporal_split_has_no_overlap():
    """Train dates strictly before cutoff; holdout dates on/after. No leakage."""
    raise NotImplementedError


@pytest.mark.skip(reason="implement in Phase 4")
def test_precision_at_k_basic():
    """precision_at_k returns correct fractions on a small hand-checked example."""
    raise NotImplementedError
