"""Tests for Phase 1 cleaning logic and configuration.

The scalar helpers run anywhere; the end-to-end Spark test is skipped when no
JVM/Spark is available (e.g. a laptop without Java), and runs on Databricks/CI.
"""

from __future__ import annotations

import pytest

from sift.processing.clean_spark import (
    DOMAINS_COLUMN_MAP,
    REQUESTS_COLUMN_MAP,
    URL_COUNT_COLUMNS,
    name_key,
    normalise_domain,
    normalise_name,
    safe_removal_rate,
)


class TestNormaliseName:
    def test_collapses_whitespace_and_strips(self) -> None:
        assert normalise_name("  Web   Sheriff ") == "Web Sheriff"

    def test_preserves_casing(self) -> None:
        assert normalise_name("MarkMonitor") == "MarkMonitor"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_blanks_become_none(self, value: str | None) -> None:
        assert normalise_name(value) is None

    def test_name_key_is_case_insensitive(self) -> None:
        assert name_key("Web Sheriff") == name_key("web  sheriff ")
        assert name_key(None) is None


class TestNormaliseDomain:
    def test_lowercases_and_trims(self) -> None:
        assert normalise_domain("  RojaDirecta-Live.XYZ ") == "rojadirecta-live.xyz"

    def test_strips_trailing_dot(self) -> None:
        assert normalise_domain("example.com.") == "example.com"

    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_blanks_become_none(self, value: str | None) -> None:
        assert normalise_domain(value) is None


class TestSafeRemovalRate:
    def test_basic_ratio(self) -> None:
        assert safe_removal_rate(50, 100) == 0.5

    def test_divide_by_zero_returns_none(self) -> None:
        assert safe_removal_rate(0, 0) is None
        assert safe_removal_rate(5, None) is None

    def test_clamped_to_unit_interval(self) -> None:
        # Dirty rows where removed exceeds specified are clamped, not >1.
        assert safe_removal_rate(120, 100) == 1.0

    def test_none_removed_treated_as_zero(self) -> None:
        assert safe_removal_rate(None, 10) == 0.0


class TestColumnMaps:
    def test_maps_target_snake_case_schema(self) -> None:
        assert REQUESTS_COLUMN_MAP["Request ID"] == "request_id"
        assert REQUESTS_COLUMN_MAP["From Abuser"] == "from_abuser"
        assert DOMAINS_COLUMN_MAP["Domain"] == "domain"

    def test_count_columns_are_mapped_targets(self) -> None:
        targets = set(REQUESTS_COLUMN_MAP.values())
        assert set(URL_COUNT_COLUMNS).issubset(targets)


# --------------------------------------------------------------------------- #
# Spark integration test (skips without a JVM)                                #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def spark():
    pyspark = pytest.importorskip("pyspark")  # noqa: F841
    try:
        from sift.processing.clean_spark import build_spark

        session = build_spark("sift-test")
    except Exception as exc:  # pragma: no cover - depends on local JVM
        pytest.skip(f"Spark/JVM unavailable: {exc}")
    yield session
    session.stop()


def test_clean_requests_derives_specified_and_rate(spark, tmp_path) -> None:
    """End-to-end: real source headers in, documented schema + derived label out."""
    csv = tmp_path / "requests.csv"
    header = ",".join(REQUESTS_COLUMN_MAP)
    rows = [
        # request 1: 50 removed of (50+0+0+0)=50 specified -> rate 1.0
        "1,2024-08-17T10:00:00Z,http://l/1,22818,Web  Sheriff,1847,Web Sheriff,50,0,0,0,false",
        # request 2: 0 removed of (0+96+0+0)=96 specified -> rate 0.0, abuser
        "2,2024-08-18T11:00:00Z,http://l/2,22818,web sheriff,1847,Web Sheriff,0,0,96,0,true",
    ]
    csv.write_text(header + "\n" + "\n".join(rows) + "\n")

    from sift.processing.clean_spark import clean_requests

    out = {r["request_id"]: r for r in clean_requests(spark, str(csv)).collect()}

    assert out[1]["urls_specified"] == 50
    assert out[1]["removal_rate"] == 1.0
    assert out[2]["urls_specified"] == 96
    assert out[2]["removal_rate"] == 0.0
    assert out[2]["from_abuser"] is True
    # Owner name canonicalised to the modal spelling across both rows.
    assert out[1]["copyright_owner"] == out[2]["copyright_owner"]
