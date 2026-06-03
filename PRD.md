# Product Requirements Document

## Project: Takedown Triage and Early-Warning System for Content Piracy

**Codename:** Sift
**Author:** Akintunde
**Status:** Draft v1.0
**Last updated:** 2 June 2026
**Context:** Portfolio project built to mirror a real problem faced by Friend MTS, in support of an application for the Junior / Graduate Data Scientist role (Engineering, Birmingham / London, hybrid).

---

## 1. Executive summary

Friend MTS is the world's leading content-protection and anti-piracy company. Its core operational loop is to **monitor** the internet for pirated content, **identify** the source, and **disrupt** it through takedowns and enforcement. The single hardest constraint in this loop is time: a live sports fixture is the most pirated and most time-sensitive content in media, the commercial window is only a few hours, and a single fixture can generate thousands of pirate streams. Human analysts cannot action everything before the value expires, and a meaningful share of what reaches them is noise that will never be actioned at all.

Sift is a decision-support system that does two things on real, public data:

1. **Triage.** Given a flood of incoming takedown candidates, it scores and ranks them so an analyst spends limited time on the requests most likely to succeed and matter, learned from the historical record of which takedowns actually stuck.
2. **Early warning.** It watches a live feed of newly created websites and flags emerging pirate-style domains before they are widely reported, so the system looks forwards as well as backwards.

The deliverable is a Streamlit dashboard backed by a Python and SQL data pipeline, with a "replay mode" that evaluates the system honestly against historical data it has never seen, and presents it as though it were happening live.

This document specifies the problem, the data, the functional and non-functional requirements, the architecture, the evaluation method, and an honest account of the project's limits.

---

## 2. Problem statement

### 2.1 The operational problem (the client's pain)

Rights holders pay enormous sums for content, especially live sport, and piracy attacks that value in real time. Friend MTS's own published material states that during major events illegal streams "can number in the thousands per fixture", and that at that volume "automation of monitoring to work alongside watermarking is not optional; it is the only viable approach." The commercial window of a fixture lasts only a few hours, so a takedown actioned after the final whistle is close to worthless.

Two distinct pain points fall out of this:

- **Volume versus time.** More takedown candidates arrive than analysts can process inside the window that matters. Without prioritisation, high-value targets can sit in a queue while low-value ones are actioned first.
- **Noise.** Not every detection or request is valid. Google's own transparency documentation confirms it regularly receives "inaccurate or unjustified copyright removal requests for search results that clearly do not link to infringing content", and even gives the example of a content-protection organisation filing requests that were rejected. Time spent on requests that will never be actioned is time the genuine pirate streams stay live.

### 2.2 The infrastructure problem

Pirate operations are resilient by design. Industry reporting shows illegal operators swap content delivery networks within minutes of a takedown and "register new domains the moment their existing ones are suspended." Any system trained only on historical takedown records is therefore always one step behind: by the time a domain appears in the record, it is already known. There is a need to detect *new* infrastructure as it appears, not only to rank what has already been caught.

### 2.3 Why a data science approach fits

Both problems are data problems. Triage is a supervised learning and optimisation problem with a real, labelled outcome attached to every historical request. Early warning is an anomaly-detection problem over a live, high-volume data stream. Neither requires access to Friend MTS's proprietary systems to demonstrate the core thinking, because suitable public data exists for both.

---

## 3. Goals and non-goals

### 3.1 Goals

- Build a working triage model that ranks takedown candidates by predicted outcome, trained and evaluated on real public data.
- Frame the analyst's "what do I action in the next ten minutes" decision as an explicit constrained optimisation, not just a sort.
- Build an early-warning module that flags emerging pirate-style domains from a live network data feed.
- Validate the system rigorously using temporal backtesting (a time-based holdout), and present it through a replay mode that feels live.
- Communicate findings through an interactive dashboard aimed at a non-technical operational user.
- Exercise the specific tools, libraries and concepts named in the target job description, honestly and where they genuinely fit.

### 3.2 Non-goals

- **Not** a live integration with Friend MTS or any rights holder's systems. The project uses only public data.
- **Not** a watermark embedding or extraction system. Watermarking is Friend MTS's proprietary technology; Sift sits at the monitoring and triage layer, not the watermarking layer.
- **Not** a fully automated enforcement tool. Sift recommends and ranks; a human remains in the loop.
- **Not** a computer-vision project. See Section 13 for an honest treatment of this gap.

---

## 4. Target users and personas

**Primary user: the anti-piracy analyst ("Maya").** Works real-time shifts during live events. Technical enough to read a dashboard, not a data scientist. Needs to know, right now, which of hundreds of detections to chase first, and which to ignore. Success for Maya is catching more high-value streams before the event ends, with less wasted effort.

**Secondary user: the operations or client-success lead ("David").** Reports outcomes to rights-holder clients. Needs summary views and evidence that the process is effective and improving. Cares about trends, hit rates and time saved, not model internals.

**Tertiary audience: a hiring data scientist or engineer at Friend MTS.** Will read the repository to judge the candidate's structured thinking, code quality, evaluation discipline and ability to communicate. The project must be legible to this reader through clean code, a clear README, and this PRD.

---

## 5. Solution overview

Sift has two cooperating halves that share one dashboard.

**Half A — Triage engine (looks backwards to prioritise).**
Trained on the Google Transparency Report copyright dataset, which contains millions of past takedown requests with their outcomes attached. The engine predicts, for each new candidate, the probability it would be actioned, attaches an estimated value, and solves a constrained optimisation to recommend the best set of actions for a given time budget.

**Half B — Early-warning radar (looks forwards to warn).**
Consumes a live feed of newly issued TLS certificates (Certificate Transparency logs), effectively a real-time stream of new websites coming online. Using naming patterns learned from the known pirate domains in the Google data, it scores fresh domains for piracy risk and surfaces a watchlist before those domains are widely reported.

The two halves connect through the domain layer: the historical data teaches what "bad" looks like, and the live feed applies that knowledge to find the next offenders.

---

## 6. Data sources

### 6.1 Google Transparency Report — Copyright removals (primary)

A public dataset covering more than 95% of copyright removal requests made to Google Search since July 2011, released for study and downloadable as CSV files with a README. It is the closest public analogue to Friend MTS's monitor-identify-disrupt records.

The data arrives as linked tables, joined on a request identifier:

**Requests table** (one row per removal request):

| Field | Meaning | Use in Sift |
|---|---|---|
| Request ID | Unique request identifier | Join key |
| Date | When the request was filed | Temporal split, velocity, burst features |
| Reporting organisation | Agent who filed (e.g. MarkMonitor, Web Sheriff) | Categorical feature |
| Copyright owner | Rights holder (e.g. a league or broadcaster) | Categorical feature; segment filter |
| URLs removed | Count Google actioned | Label numerator |
| URLs for which no action taken | Count Google refused | Label denominator / noise signal |
| URLs not in index | Count not in Google's index | Feature / data-quality signal |

**Domains table** (one row per domain per request):

| Field | Meaning | Use in Sift |
|---|---|---|
| Request ID | Join key | Link to request |
| Domain | The targeted domain | Clustering, naming-pattern learning |
| URLs specified | Count requested for this domain | Feature |
| URLs removed | Count actioned for this domain | Label |
| Percentage of domain | Share of the domain targeted | Feature |

**Derived label — the removal rate.** For each request or domain, `removal_rate = URLs removed / URLs specified`. A high rate is a genuine, high-value target; a rate near zero is noise the model should learn to deprioritise. This is the supervised signal, and it is already present in real historical outcomes, so no synthetic labelling is required.

### 6.2 Certificate Transparency logs (secondary, live)

Certificate Transparency is a public, append-only log of every TLS certificate issued across the web, streamable in near real time (for example via a CertStream-style feed). Each new entry effectively announces a brand-new website. It is free, real, and genuinely network-infrastructure data.

| Field | Meaning | Use in Sift |
|---|---|---|
| Domain / SAN entries | The newly certified hostname(s) | Pattern scoring |
| Issuer | Certificate authority | Feature / filter |
| Timestamp | When issued | Real-time ordering, burst detection |

**Honest scope note.** This is live, network-style data, but it is *not* packet or session telemetry from a video stream. It tells us a new website has appeared, not how video is flowing through it. It is one step removed from the stream-level data Friend MTS works with internally. This limit is stated plainly and is not hidden. See Section 13.

### 6.3 Data volume and quality

The Google dataset runs to millions of rows and is genuinely noisy: the source FAQ itself warns of duplicate organisation and owner names, inconsistent spellings, and self-reported fields that are not always verifiable. Cleaning this is a real part of the work, not a formality.

---

## 7. Functional requirements

### 7.1 Data ingestion and storage

- FR-1.1 Cloud-first ingest: because the raw dataset is ~13GB, it is downloaded and unzipped on a Databricks cluster (never on the laptop) and the raw CSVs are written to an AWS S3 bucket as the canonical source. See `notebooks/00_ingest_databricks.py`.
- FR-1.2 Read raw data from S3 into the processing layer; never mutate the raw files in place.
- FR-1.3 Stand up a streaming consumer for the Certificate Transparency feed that appends new-domain records to a rolling store for scoring.

### 7.2 Data cleaning and processing

- FR-2.1 Use PySpark to clean and process the full Google dataset, justified by its size: deduplicate organisation and owner names, normalise spellings, parse dates, and resolve the requests-to-domains join.
- FR-2.2 Run the PySpark processing on a Databricks cluster reading raw data from S3 and persisting a cleaned, analysis-ready dataset back to S3, plus a small sample extract for the local dashboard. The laptop is never used for the heavy data.
- FR-2.3 Produce a documented data dictionary for the cleaned dataset.

### 7.3 Exploratory analysis

- FR-3.1 Profile the data: distributions of removal rates, top reporting organisations and owners, request volumes over time, and domain-level patterns.
- FR-3.2 Quantify the noise problem: what share of requests have near-zero removal rates, and which organisations or domain types they cluster around.
- FR-3.3 Surface findings in clear visualisations suitable for a non-technical reader.

### 7.4 Feature engineering

- FR-4.1 Build request-level features: reporting organisation, copyright owner, URL counts, share not in index, day-of-week and time features, and the requester's historical hit rate.
- FR-4.2 Build domain-level features: naming patterns (presence of tokens such as stream, live, hd, sport, league names), top-level domain risk, domain age proxy, and historical targeting frequency.
- FR-4.3 Prevent leakage: any historical-rate feature must be computed only from data strictly before the row's own date.

### 7.5 Triage model

- FR-5.1 Train a supervised model to predict the probability a request or domain will be actioned (removal rate above a defined threshold, or the rate itself as a regression target).
- FR-5.2 Provide at least two modelling approaches for comparison, including an interpretable statistical baseline (e.g. logistic regression) and a stronger model (e.g. gradient-boosted trees), so the choice is evidenced rather than assumed.
- FR-5.3 Output a calibrated score per candidate, plus the top features driving each score, so the analyst sees *why* something is ranked highly.

### 7.6 Optimisation layer

- FR-6.1 Frame triage as a constrained optimisation: given a time or effort budget and a per-candidate cost, select the set of candidates that maximises total expected value (probability of action multiplied by an importance weight).
- FR-6.2 Implement and compare a simple greedy ranking against the optimised selection, and report the difference in expected value captured.

### 7.7 Anomaly and early-warning module

- FR-7.1 Score each new domain from the Certificate Transparency feed for piracy risk using patterns learned from known pirate domains in the Google data.
- FR-7.2 Apply outlier and burst detection to flag unusual spikes of similar new domains, for example clusters appearing close to major fixtures.
- FR-7.3 Maintain a ranked watchlist of emerging suspicious domains, refreshed as the feed updates.

### 7.8 Backtesting and replay engine

- FR-8.1 Implement a temporal holdout: train only on requests up to a cutoff date and evaluate on a strictly later period the model has never seen.
- FR-8.2 Replay the held-out period in time order, presenting candidates with outcomes hidden, scoring and ranking them, then revealing actual outcomes to score the ranking.
- FR-8.3 Drive a "replay mode" in the dashboard that steps through a past period as though live, with the ranked list updating and a countdown, while underneath it remains a rigorous backtest.

### 7.9 Dashboard

- FR-9.1 Build the interface in Streamlit with Plotly visualisations.
- FR-9.2 Triage view: a live-style ranked list of candidates with scores, key reasons, and a visible cut line for the current time budget; low-confidence noise is de-emphasised.
- FR-9.3 Early-warning view: the emerging-domain watchlist with risk scores and timestamps.
- FR-9.4 Outcomes view: backtest metrics and trends aimed at the operations lead, including precision at the top of the list and estimated analyst time saved.
- FR-9.5 Replay controls: play, pause and step through a chosen historical period.

---

## 8. Non-functional requirements

- NFR-1 **Reproducibility.** A documented, scripted pipeline from raw S3 data to dashboard; anyone can rebuild from the README.
- NFR-2 **Code quality.** Modular Python, typed where sensible, with unit tests on the data-processing and scoring logic.
- NFR-3 **Honesty of evaluation.** No target leakage; all reported metrics come from data the model did not train on.
- NFR-4 **Legibility.** A hiring reader can understand the project from the README and this PRD without running it.
- NFR-5 **Cost.** Kept low using public data and free tiers where possible (S3 free tier, public feeds). A small paid Databricks cluster may be needed to process the ~13GB within Community Edition limits; clusters are stopped when idle to keep cost to a few pounds.
- NFR-6 **Provenance.** Every external claim about the problem space is sourced.

---

## 9. Evaluation and success metrics

Sift is judged the way a real pre-deployment model would be: on data it has never seen.

- **Precision at K.** Of the top K candidates the system tells the analyst to action, what share were genuinely actioned in reality? This is the headline metric, because it reflects the analyst's real workflow of working a list top-down under time pressure.
- **Value captured under budget.** Comparing the optimised selection against a naive ranking, how much more expected value is secured within the same time budget?
- **Noise avoided.** How many would-be wasted actions (near-zero removal-rate requests) does the system push below the cut line?
- **Early-warning lead time.** For domains that later appear in takedown records, how much earlier did the radar flag them?
- **Model quality.** Standard discrimination and calibration measures (e.g. ROC AUC, precision-recall, calibration curves) on the temporal holdout.

A clear, defensible story on these metrics is the definition of done, more than any single number.

---

## 10. System architecture and tech-stack mapping

```
[Google Transparency Report CSVs]      [Certificate Transparency live feed]
              |                                        |
   download+unzip on Databricks cluster        streaming consumer
              |                                        |
   AWS S3 (raw, canonical)                    rolling new-domain store
              |                                        |
   PySpark cleaning (Databricks)                       |
              |                                        |
   S3 (cleaned, analysis-ready)                        |
              |                                        |
   Feature engineering (Python / SQL)                  |
              |                                        |
   Triage model + optimisation layer        Pattern + anomaly scoring
              |                                        |
   Temporal backtest / replay engine                   |
              \________________________  ______________/
                                       \/
                          Streamlit + Plotly dashboard
                  (Triage / Early-warning / Outcomes / Replay)

   Built throughout with Claude Code and GitHub Copilot.
```

---

## 11. Phased build plan

**Phase 0 — Setup.** Repository, environment, S3 bucket, README skeleton, this PRD. *Output: scaffolded project.*

**Phase 1 — Data foundation.** Download to S3, PySpark cleaning, data dictionary, exploratory analysis and the noise quantification. *Output: cleaned dataset and an EDA notebook.*

**Phase 2 — Triage model.** Feature engineering with leakage controls, baseline and stronger models, calibration, feature explanations. *Output: a scored, evaluated model.*

**Phase 3 — Optimisation.** Budget-constrained selection, compared against naive ranking. *Output: the prioritisation layer.*

**Phase 4 — Backtest and replay.** Temporal holdout and the replay engine. *Output: honest evaluation harness.*

**Phase 5 — Early-warning radar.** Certificate Transparency consumer, pattern scoring, anomaly and burst detection, watchlist. *Output: forward-looking module.*

**Phase 6 — Dashboard.** Streamlit app with all four views and replay controls. *Output: the demo.*

**Phase 7 — Polish.** Tests, README, write-up, a short stakeholder-facing brief. *Output: portfolio-ready repository.*

---

## 12. Job-description skills coverage

This project is deliberately designed to exercise the target role's requirements. Honest status for each:

| Skill / tool | Covered? | Where |
|---|---|---|
| Python (professional) | Yes | Throughout |
| SQL | Yes | Querying and joining the tables |
| Plotly | Yes | All dashboard charts |
| Streamlit | Yes | Dashboard and replay |
| AWS (S3) | Yes | Raw and cleaned data storage |
| PySpark | Yes | Cleaning the full dataset |
| Databricks | Yes | PySpark notebook (Community Edition) |
| ML modelling | Yes | Triage classifier |
| Statistical modelling | Yes | Interpretable baseline, tests on outcomes |
| Optimisation | Yes | Budget-constrained selection |
| Anomalous pattern detection | Yes | Early-warning radar |
| Data cleaning and processing | Yes | A real, substantial step |
| Data analysis and exploration | Yes | EDA phase |
| Data visualisation | Yes | Dashboard and EDA |
| Large, noisy datasets | Yes | Millions of rows, real duplication |
| Claude Code / Copilot / AI-assisted | Yes | Used to build it, documented in the repo |
| Streaming and network data | Partial | Certificate Transparency is live network-style data, but not stream telemetry (Section 13) |
| Security intelligence | Yes | Whole project framing |
| Illegal-activity identification | Yes | Core purpose |
| Content protection | Yes | Core domain |
| Communicating to non-technical stakeholders | Yes | Dashboard plus stakeholder brief |
| Structured problem solving | Yes | This PRD and phased plan |
| Taking models to production (with engineers) | Partial | Production discipline shown solo; not literal team collaboration (Section 13) |
| Computer vision (desirable) | No | Out of scope; honest gap (Section 13) |

---

## 13. Risks, limitations and honest gaps

- **No live deployment.** The system cannot be tested against Friend MTS's real-time feed. This is addressed, not hidden, through temporal backtesting: the model is graded on later data it never trained on, which is the correct pre-deployment evaluation regardless. The replay mode makes this legible without pretending it is a live integration.
- **Streaming and network data is covered adjacently, not directly.** Certificate Transparency is real, live, network-infrastructure data, but it is not packet or session telemetry from a video stream. The framing is right; the exact data type is one step removed. Stated plainly wherever relevant.
- **Production collaboration is simulated.** As a solo project it shows the discipline that makes a model production-ready (tests, reproducibility, a deployment note) but not literal teamwork with engineers.
- **Computer vision is out of scope.** The project is tabular and streaming-metadata based; computer vision does not fit naturally and is a "desirable", not a requirement. It is better handled either as a small separate demo or discussed in interview rather than forced into this build.
- **Proxy data.** Google takedown records are an analogue for Friend MTS's internal monitoring records, not the same data. The transferable asset is the method and the thinking, which is stated openly.
- **Self-reported source data.** The Google data contains self-reported, sometimes inaccurate fields; this is a property of the domain and is handled in cleaning rather than assumed away.

---

## 14. Future work

- A small, separate computer-vision demo (for example, classifying screenshots of suspected pirate sites) to speak to that desirable directly.
- Graph-based clustering of pirate infrastructure across domains, hosting and registration signals.
- Incorporating additional public takedown sources (such as the Lumen database) to enrich and cross-check the Google data.

---

## 15. Appendix

### 15.1 Illustrative data snapshot (format, not verified rows)

`requests` (one row per request):

```
Request ID | Date       | Reporting org | Copyright owner | URLs removed | No action | Not in index
9482156    | 2024-08-17 | MarkMonitor   | LaLiga          | 482          | 11        | 7
9482160    | 2024-08-17 | Web Sheriff   | DAZN            | 51           | 0         | 2
9482171    | 2024-08-18 | Comeso GmbH   | beIN Media      | 0            | 96        | 4
9482190    | 2024-08-18 | Rivendell     | NBCUniversal    | 1            | 240       | 3
```

`domains` (one row per domain per request):

```
Request ID | Domain               | URLs specified | URLs removed | % of domain
9482156    | rojadirecta-live.xyz | 50             | 50           | <10%
9482156    | totalsportek-hd.ru   | 22             | 22           | <1%
9482171    | newsblog-example.com | 96             | 0            | <1%
9482190    | imdb.com             | 1              | 0            | <1%
```

The bottom two rows are real-style false positives (a news blog and an IMDb page that Google refused to remove); the top rows are genuine pirate-style targets fully actioned. The model learns to separate the two.

### 15.2 Glossary

- **Takedown / removal request:** a formal request to remove or delist allegedly infringing content.
- **Removal rate:** share of requested URLs that were actually actioned; Sift's core label.
- **Temporal backtest:** evaluating a model on data strictly later than its training data, to simulate real deployment.
- **Certificate Transparency:** public logs of newly issued TLS certificates, usable as a live feed of new websites.
- **Precision at K:** of the top K items recommended, the share that were genuinely correct.

### 15.3 Sources

- Friend MTS, "What we discovered using forensic watermarking in live sports": https://www.friendmts.com/blog/what-we-discovered-using-forensic-watermarking-in-live-sports
- Friend MTS, product and solutions overview: https://www.friendmts.com/
- Google Search removals due to copyright infringement, FAQs: https://support.google.com/transparencyreport/answer/7347743
- Google Transparency Report, Copyright removals, Explore the data: https://transparencyreport.google.com/copyright/explore
- Download Transparency Report data: https://support.google.com/transparencyreport/answer/7347561
- Lumen Database, information for researchers: https://lumendatabase.org/pages/researchers
- Remove Your Media, live sports piracy and the rise of IPTV: https://removeyourmedia.com/2026/02/24/live-sports-piracy-and-the-rise-of-iptv-streams-what-rights-holders-need-to-know/
- Irdeto, forensic watermarking at scale: https://irdeto.com/blog/modern-forensic-watermarking-at-scale
