"""Streamlit dashboard for Sift. (PRD FR-9.x)

Run: streamlit run src/sift/dashboard/app.py

Four views:
  1. Triage      — live-style ranked candidate list with scores, reasons, and a
                   visible cut line for the current time budget; noise de-emphasised.
  2. Early warning — emerging-domain watchlist with risk scores and timestamps.
  3. Outcomes    — backtest metrics + trends for the operations lead
                   (precision@K, estimated analyst time saved).
  4. Replay      — play / pause / step through a chosen historical period.

Charts are Plotly. Keep heavy computation out of the render loop (cache it).
"""

from __future__ import annotations


def main() -> None:
    """Build the Streamlit app.

    TODO:
      - st.set_page_config + sidebar navigation across the four views
      - load cached scored/backtest data
      - render each view with Plotly figures
      - replay controls driving sift.backtest.replay
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
