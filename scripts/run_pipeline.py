"""End-to-end pipeline runner.

Ties the phases together so the whole thing rebuilds with one command:
ingest -> clean (Spark) -> features -> train -> backtest -> persist scored outputs
that the dashboard reads.

Usage:
    python scripts/run_pipeline.py
"""

from __future__ import annotations


def main() -> None:
    """Run the full pipeline. TODO: wire phases once each module is implemented."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
