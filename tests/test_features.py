"""Tests for feature engineering. (PRD NFR-2, NFR-3)

The most important test here guards against TARGET LEAKAGE: a historical-rate
feature for a row must not be influenced by that row's own outcome or any later row.
"""

import pytest


@pytest.mark.skip(reason="implement in Phase 2")
def test_make_label_threshold():
    """removal_rate >= threshold -> 1, below -> 0."""
    raise NotImplementedError


@pytest.mark.skip(reason="implement in Phase 2")
def test_historical_hit_rate_is_leakage_safe():
    """A row's requester-hit-rate feature must use only strictly-earlier rows."""
    raise NotImplementedError
