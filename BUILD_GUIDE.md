# Build guide — handover to Claude Code

This is the build plan for implementing Sift. The repository is already
scaffolded: every module in `src/sift/` has a typed stub with its contract and a
`TODO` referencing a functional requirement (FR) in [PRD.md](./PRD.md). Your job in
Claude Code is to fill those in, phase by phase, in order.

## How to use this guide

1. Open this folder in Claude Code.
2. Work one phase at a time. For each, paste the **prompt** into Claude Code, then
   check the **acceptance criteria** before moving on.
3. Commit after each phase with the suggested message. The commit history is part of
   the story — it shows AI-assisted development, which the role requires.
4. If something is ambiguous, the PRD is the source of truth. Keep the PRD and this
   guide in the chat context.

## Ground rules to give Claude Code (paste once at the start)

```
Read PRD.md and BUILD_GUIDE.md first; treat the PRD as the source of truth.
Conventions:
- Python 3.11+, type hints, docstrings, snake_case.
- Configuration only via src/sift/config.py (yaml + .env). Never read env vars
  directly elsewhere, and never hardcode secrets or bucket names.
- Lint/format with ruff. Add unit tests for any non-trivial logic.
- No target leakage: features using history must use only strictly-earlier rows.
- Work only within the current phase. Stop at its acceptance criteria and wait.
- Prefer small, reviewable commits.
```

---

## Phase 0 — Cloud setup (you, before Claude Code)

This project is **cloud-first** because the raw dataset is ~13GB and must not land on
your laptop. The download, unzip and cleaning all run on a Databricks cluster writing
to S3. Your laptop only runs Claude Code and, later, the dashboard.

Do these by hand:

1. **Light local environment** (no big data, no local Spark):
   ```bash
   cd piracy-takedown-triage
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
2. **AWS S3.** Create a bucket (e.g. `sift-piracy-data`) in your region. Create an IAM
   user with programmatic access scoped to that bucket. Put the bucket name, region
   and keys in `.env` (`USE_S3=true`).
3. **Databricks.** Create a workspace and a cluster. Generate a personal access token
   and put the host + token in `.env`. Connect this repo via **Databricks Repos**
   (git) so notebooks can `import sift...`.
4. **Stage the data to S3 without unzipping.** You already have the ~13GB zip
   (`google-websearch-copyright-removals.zip`); unzipped it is ~75GB, which will not
   fit on the laptop. Do **not** unzip it. Instead stream each file straight from the
   zip into S3 with the provided script (laptop is only a pass-through pipe):
   ```bash
   ./scripts/stage_zip_to_s3.sh /path/to/google-websearch-copyright-removals.zip s3://<your-bucket>/raw
   ```
   This uploads gzipped `requests.csv.gz` and `domains.csv.gz` (plus README.txt) and
   skips the 39GB `urls-no-action-taken.csv` by default (not needed for v1; pass
   `--include-no-action` only if you ever want it).

**Acceptance:** `pip install` succeeds; the S3 bucket exists and now holds
`raw/requests.csv.gz`, `raw/domains.csv.gz` and `raw/README.txt`; the Databricks
cluster runs and can see this repo; `.env` has S3 keys and Databricks host/token.

> Why this works: unzip streams one file to stdout, gzip shrinks it, aws s3 cp -
> uploads it. The ~75GB unzipped data is never written to disk anywhere.

---

## Phase 1 — Cloud ingest + cleaning (Databricks + S3)

**Prompt:**
```
Implement src/sift/config.py (load_settings) and src/sift/ingest/s3_io.py
(read_csv, write_processed, local_path) reading/writing S3 via boto3 when USE_S3=true
(the default), with a local-disk fallback for small samples when false.

The raw CSVs are already in S3 (gzipped: raw/requests.csv.gz, raw/domains.csv.gz,
raw/README.txt), staged off-cluster by scripts/stage_zip_to_s3.sh. The 39GB
urls-no-action-taken.csv is intentionally not ingested for v1.

Implement src/sift/processing/clean_spark.py (clean_requests, clean_domains,
join_and_persist) and call it from notebooks/00_ingest_databricks.py: read the
gzipped raw CSVs from s3://<bucket>/raw/ with Spark, map the real source column names
(from raw/README.txt) to the snake_case schema in
src/sift/processing/data_dictionary.md, clean them (parse dates, coerce URL counts to
int, normalise and deduplicate organisation/owner names, lowercase domains), derive
removal_rate safely, join on request_id, write Parquet to s3://<bucket>/processed/, and
write a small sample (config storage.local_sample_rows) to s3://<bucket>/sample/ for the
local dashboard. Update data_dictionary.md if the real columns differ.
```

**Acceptance criteria:**
- `load_settings()` returns merged config; no secrets in code.
- The notebook downloads + unzips on the cluster and writes raw CSVs to `s3://<bucket>/raw/`; nothing large remains on the cluster or the laptop.
- Cleaning produces Parquet in `s3://<bucket>/processed/` with the documented schema.
- A small `sample/` extract is written for local use.
- `removal_rate` is present and bounded to [0, 1]; divide-by-zero handled.
- `data_dictionary.md` matches the real columns; row counts before/after are logged.

**Commit:** `feat: cloud ingest (Databricks->S3) and Spark cleaning of Google data`

---

## Phase 2 — EDA + features

**Prompt:**
```
Create notebooks/01_eda.ipynb reading the cleaned data from s3://<bucket>/processed/
(or the small sample/ extract): removal_rate
distribution, top reporting orgs and copyright owners, request volume over time, and
how much of the data is near-zero-removal "noise" (and where it clusters). Use Plotly.

Then implement src/sift/features/build_features.py (add_request_features,
add_domain_features, make_label). Enforce leakage safety: historical-rate features
must be expanding aggregates over strictly-earlier dates only. Implement the two
leakage and label tests in tests/test_features.py and make them pass.
```

**Acceptance criteria:**
- EDA notebook runs top-to-bottom and quantifies the noise share with a chart.
- Feature functions return the engineered frame; label is binary via
  `ACTION_THRESHOLD`.
- `pytest tests/test_features.py` passes, including the leakage test.

**Commit:** `feat: EDA and leakage-safe feature engineering`

---

## Phase 3 — Triage model

**Prompt:**
```
Implement src/sift/models/triage.py: train_baseline (logistic regression) and
train_challenger (XGBoost), both calibrated, plus TriageModel.predict_proba and
.explain (top feature contributions per row). Evaluate both on a temporal holdout
(not random) using ROC AUC, precision-recall and a calibration curve, and write a
short comparison to notebooks/02_modelling.ipynb. Pick the model with the better
ranking behaviour and justify it in a markdown cell.
```

**Acceptance criteria:**
- Both models train and produce calibrated probabilities.
- Evaluation uses a time-based split (reuse `backtest.temporal_split` once Phase 4
  exists, or a temporary split here and refactor in Phase 4).
- `.explain` returns usable per-row reasons for the dashboard.
- A clear, written model choice with evidence.

**Commit:** `feat: calibrated triage model (logistic baseline + XGBoost challenger)`

---

## Phase 4 — Optimisation + backtest/replay

**Prompt:**
```
Implement src/sift/models/optimise.py (expected_value, greedy_select,
optimal_select as a 0/1 knapsack via DP or scipy.optimize.milp) and
src/sift/backtest/replay.py (temporal_split, replay, precision_at_k). Report the
expected-value uplift of optimal over greedy under the configured budget. Implement
and pass tests/test_optimise.py and tests/test_backtest.py.
```

**Acceptance criteria:**
- `optimal_select` never exceeds budget and matches/beats greedy on expected value.
- `replay` walks the holdout in time order, ranking with outcomes hidden then
  revealing them.
- `precision_at_k` verified on a hand-checked example.
- Both test files pass.

**Commit:** `feat: budget-constrained optimisation and temporal backtest/replay`

---

## Phase 5 — Early-warning radar

**Prompt:**
```
Implement src/sift/ingest/cert_stream.py (live CertStream consumer plus a
replay-from-file mode for demos) and src/sift/anomaly/domain_scoring.py
(fit_pattern_scorer learned from known pirate domains in the Google data,
score_domain, detect_bursts). Capture a few minutes of the live feed to a file for
the demo, and refine the suspicious token/TLD lists in config.yaml from what the
historical data actually shows.
```

**Acceptance criteria:**
- A captured feed sample is saved for offline replay.
- `score_domain` ranks obvious pirate-style names above benign ones.
- `detect_bursts` flags a synthetic spike in a hand-checked test.
- Token/TLD lists in `config.yaml` updated from real data.

**Commit:** `feat: certificate-transparency early-warning radar`

---

## Phase 6 — Dashboard

**Prompt:**
```
Implement src/sift/dashboard/app.py in Streamlit with Plotly: four views
(Triage, Early warning, Outcomes, Replay) per PRD FR-9. The Triage view shows the
ranked candidate list with scores, per-row reasons and a visible budget cut line.
Outcomes shows precision@K and estimated analyst time saved. Replay plays/pauses/
steps through a historical period driving backtest.replay, looking live. Cache heavy
computation. Then wire scripts/run_pipeline.py to rebuild everything end to end.
```

**Acceptance criteria:**
- `streamlit run src/sift/dashboard/app.py` launches all four views.
- Replay visibly steps through time and the ranking updates.
- `python scripts/run_pipeline.py` rebuilds the scored outputs the dashboard reads.

**Commit:** `feat: Streamlit dashboard with replay mode and end-to-end pipeline`

---

## Phase 7 — Polish

(Cloud is already in place from Phase 0/1, so this phase is just finishing.)

**Prompt:**
```
Finalise: run ruff and fix lint, ensure pytest is green, flesh out the README results
section with real backtest numbers (precision@K and the optimisation uplift) and a
dashboard screenshot, and add a one-page stakeholder brief
(docs/STAKEHOLDER_BRIEF.md) explaining the outcome to a non-technical reader.
```

**Acceptance criteria:**
- `ruff check` clean, `pytest` green.
- README shows real precision@K and the optimisation uplift, with a screenshot.
- `docs/STAKEHOLDER_BRIEF.md` reads well for a non-technical audience.

**Commit:** `chore: polish, results and stakeholder brief`

---

## Definition of done

- All seven phases committed; tests green; ruff clean.
- The dashboard runs and the replay tells the story end to end.
- README and PRD let a Friend MTS reviewer understand the project without running it.
- Honest limitations (Section 13 of the PRD) remain visible, not hidden.

## Order of dependencies (quick reference)

```
Phase 0 (cloud setup) -> Phase 1 (cloud ingest + cleaning, Databricks->S3)
Phase 1 -> Phase 2 (features) -> Phase 3 (model)
                              -> Phase 4 (optimise + backtest)
Phase 5 (radar)  runs independently after Phase 1
Phase 6 (dashboard) needs Phases 3, 4 and 5
Phase 7 (polish) last
```
