# Sift — Takedown Triage and Early-Warning System

Sift is a decision-support system for content-piracy enforcement. It helps an
anti-piracy analyst answer one question under time pressure: *of the flood of
takedown candidates arriving right now, which should I action first, and which are
noise I should ignore?* It also runs an early-warning radar that flags brand-new
pirate-style websites the moment they appear.

The project is built on **real public data** and mirrors a problem that Friend MTS,
the leading content-protection company, has described publicly: during a live
fixture, illegal streams number in the thousands, the commercial window is only a
few hours, and human attention is the bottleneck.

> Full rationale, requirements and honest limitations are in [PRD.md](./PRD.md).
> The step-by-step build plan for Claude Code is in [BUILD_GUIDE.md](./BUILD_GUIDE.md).

## What it does

1. **Triage (looks backwards to prioritise).** A model trained on the Google
   Transparency Report copyright dataset — millions of past takedown requests with
   their real outcomes attached — predicts how likely each new candidate is to be
   actioned, then a constrained optimisation picks the best set to chase within a
   time budget.
2. **Early warning (looks forwards to warn).** A consumer of the Certificate
   Transparency live feed scores newly created domains for piracy risk using
   patterns learned from the historical data.
3. **Honest evaluation.** A temporal backtest grades the system on later data it
   never trained on, presented through a "replay mode" that feels live.

## Data sources

- **Google Transparency Report — Copyright removals** (primary, historical, labelled).
  Download from <https://transparencyreport.google.com/copyright/explore> and place
  the CSVs in `data/raw/` (or the S3 raw prefix).
- **Certificate Transparency logs** (secondary, live). Streamed via CertStream.

## Tech stack

Python, SQL (DuckDB), PySpark (+ Databricks for cleaning), AWS S3, scikit-learn and
XGBoost, SciPy for optimisation, Streamlit and Plotly for the dashboard. Built with
Claude Code and GitHub Copilot.

## Project layout

```
piracy-takedown-triage/
├── PRD.md                  Product requirements document
├── BUILD_GUIDE.md          Phase-by-phase build plan for Claude Code
├── config/config.yaml      Non-secret configuration
├── .env.example            Secret template (copy to .env)
├── data/                   raw / interim / processed (gitignored)
├── notebooks/              00_ingest_databricks (cloud ingest), EDA, modelling
├── scripts/run_pipeline.py End-to-end runner
├── src/sift/
│   ├── ingest/             download, S3 IO, CertStream consumer
│   ├── processing/         PySpark cleaning + data dictionary
│   ├── features/           feature engineering (leakage-safe)
│   ├── models/             triage model + optimisation layer
│   ├── anomaly/            domain risk scoring + burst detection
│   ├── backtest/           temporal holdout + replay engine
│   └── dashboard/          Streamlit app
└── tests/                  unit tests
```

## Quick start

This project is **cloud-first**: the ~13GB raw dataset lives in S3 and is processed on
Databricks. It never touches your laptop. Your machine only runs Claude Code and,
later, the dashboard (which reads a small processed sample).

```bash
# 1. Light local environment (no big data, no local Spark needed)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Secrets
cp .env.example .env        # add S3 bucket + keys and Databricks host + token

# 3. Ingest + clean IN THE CLOUD
#    Run notebooks/00_ingest_databricks.py on a Databricks cluster. It downloads and
#    unzips the Google data on the cluster, writes raw CSVs to s3://<bucket>/raw/,
#    cleans with Spark to s3://<bucket>/processed/, and a small sample to sample/.

# 4. Launch the dashboard locally (reads the small sample from S3)
streamlit run src/sift/dashboard/app.py
```

See [BUILD_GUIDE.md](./BUILD_GUIDE.md) for the full phase-by-phase steps.

## Status

Scaffold and specification complete. Implementation is carried out phase by phase in
Claude Code following [BUILD_GUIDE.md](./BUILD_GUIDE.md). Each `src` module currently
contains a typed stub with its contract and a `TODO` referencing the relevant
functional requirement in the PRD.

## A note on scope

Sift uses public proxy data, not Friend MTS's internal systems, and does not do
watermarking or computer vision. The transferable asset is the method: monitoring
data in, prioritised action out, evaluated honestly. Limitations are set out in full
in Section 13 of the PRD.


## Shell Commands Used

To test the functions in the build_features module:
```bash
PYTHONPATH=src XDG_CACHE_HOME=/private/tmp .venv/bin/python -m pytest tests/test_features.py
```
