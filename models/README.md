# Scoring-model history

Every version of the scoring model is kept here so we can always revert. Confidential to ECP Partners.

| Version | Date | What changed | Approved | Status |
|---|---|---|---|---|
| v0.9 | 2026-11-03 | Tool Spec weights (rooftops 30, pipeline 10, grocery 15, traffic 15, gap 10, node 10, signal 10). 8 counties. No raw-land filter. | Ross, Nov 3 | Reference only, never published |
| v1.0 | 2026-11-11 | Option B weights (traffic 25, grocery 10, pipeline 5; apartments count half), Polk added, raw-land corner filter (1.3+ ac within 50 m), Top 50 spaced 1 mi apart | Ross, Nov 11 | **Live.** Luke reviewed ranks 1–26 on Nov 17 |
| v1.1 | 2026-11-17 | Same weights. Tighter land screen (upland acres near the corner after NWI wetlands, two-road frontage, competitor/rail/utility owners out, Walmart/Publix/church/hospital/school/government owners flagged). Two-step output: trade areas (corners within 3 mi) ranked by best corner, up to 3 corners each, top 25. | Scope: Ross, Nov 17; thresholds PROPOSED | **Draft**, not published |
| v1.2 | 2026-11-17 | From Luke's full review: weights traffic 35 / new homes 25 / gap 5; land screen warns instead of removing (removes only competitor/7-Eleven/rail/utility owners and <1.0 ac near the corner); rail and houses-on-farm-parcel warnings; best redevelopment corner per trade area; extra corners must score 60%+ of the area's best. Backtest 74th pct (v1.0 76th on the same rebuilt data). Signal-unknown at quarter credit tested, not adopted. | Scope: Ross, Nov 17; awaiting Ross's blind review | **Draft**, not published |
| v1.3 | 2026-11-23 | From Ross's comments on Luke's review: Top 50 trade areas (500+ new homes at one corner, 3 mi across) with every viable corner listed as 2a/2b/2c (raw land first, then one-owner land of vacant lots/farm/house on acreage); deal-maker corner status file (taken/pass); team-known 7-Eleven stores file; station-at-corner and road-side positioning notes (information only). Weights as v1.2 (re-checked with Ross's overrides: still best fit). | Scope: Ross, Nov 23 | **Draft**, not published |

## Rules
- `models/<version>.json` holds everything that changes results: counties, weights, filters, land screen, tiers, output rules.
- A published version's file is never edited. Any change becomes a new version file, with a line added to the table above.
- `models/CURRENT` names the version the pipeline runs by default.
- `models/snapshots/<version>/` keeps the exact data files that were published to the artifact (candidates, meta, backtest), so the list can be restored without rerunning anything.
- Each version file records `pipeline_commit`, the git commit of the code that produced it.
- Deal-maker reviews of a version's output are kept in `reviews/`, named with the date and model version.

## How to revert
**Fast (minutes): restore the published list.** Republish `models/snapshots/<version>/*.json` to the artifact as `data/*.json`
(publish_files, mode patch). Then set `models/CURRENT` back to that version so the next scheduled refresh doesn't overwrite it.

**Full: rerun an old model on fresh data.** `MODEL=v1.0 python3 -I pipeline/11_candidates_score.py ...`, then steps 16 and 12 as in
the main README. The rerun uses today's data, so the results will differ from the snapshot where the underlying data has changed.

Older code: `git checkout <pipeline_commit>` gets the pipeline exactly as it was when that version was published.
