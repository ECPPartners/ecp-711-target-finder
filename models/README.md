# Scoring-model history

Every version of the scoring model is kept here so we can always revert. Confidential to ECP Partners.

| Version | Date | What changed | Approved | Status |
|---|---|---|---|---|
| v0.9 | 2026-11-03 | Tool Spec weights (rooftops 30, pipeline 10, grocery 15, traffic 15, gap 10, node 10, signal 10). 8 counties. No raw-land filter. | Ross, Nov 3 | Reference only, never published |
| v1.0 | 2026-11-11 | Option B weights (traffic 25, grocery 10, pipeline 5; apartments count half), Polk added, raw-land corner filter (1.3+ ac within 50 m), Top 50 spaced 1 mi apart | Ross, Nov 11 | **Live.** Luke reviewed ranks 1–26 on Nov 17 |

## Rules
- `models/<version>.json` holds everything that changes results: counties, weights, filters, land screen, tiers, output rules.
- A published version's file is never edited. Any change becomes a new version file, with a line added to the table above.
- `models/CURRENT` names the version the pipeline runs by default.
- `models/snapshots/<version>/` keeps the exact data files that were published to the artifact (candidates, meta, backtest), so the list can be restored without rerunning anything.
- Each published version gets a git tag `model-<version>`.
- Deal-maker reviews of a version's output are kept in `reviews/`, named with the date and model version.

## How to revert
**Fast (minutes): restore the published list.** Republish `models/snapshots/<version>/*.json` to the artifact as `data/*.json`
(publish_files, mode patch). Then set `models/CURRENT` back to that version so the next scheduled refresh doesn't overwrite it.

**Full: rerun an old model on fresh data.** `MODEL=v1.0 python3 -I pipeline/11_candidates_score.py ...`, then steps 16 and 12 as in
the main README. The rerun uses today's data, so the results will differ from the snapshot where the underlying data has changed.

Older code: `git checkout model-<version>` gets the pipeline exactly as it was when that version was published.
