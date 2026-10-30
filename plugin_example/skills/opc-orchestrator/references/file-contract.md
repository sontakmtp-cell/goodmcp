# Project files and transition contract

Use authorized host storage for the logical opc-doc/ folder. Never put user project
data inside the installed plugin. Create only the directories needed.

## Paths and writers
Stage outputs are under outputs/01-resource-audit/, 02-niche-positioning/,
03-value-proposition/, 04-business-model/, 05-mvp-design/, 06-conversion-loop/,
07-asset-ops/ and 08-dashboard-review/. Use the filenames required by each skill.
The specialist prepares outputs; the lead saves them or delegates a confirmed write.
A directly invoked specialist's assistant also acts as lead.

Only the lead writes:
- state/current-stage.json — workflow checkpoint.
- state/decisions.json — decision history.
- state/assumptions.json — hypotheses and observed evidence.
- state/user-preferences.json — language, mode, timezone and preferences.
- reviews/dashboard.json — structured review history.
- outputs/00-orchestrator/session-summary.md — append-only shared summary.

## Save sequence
1. Identify confirmed decisions. Existing confirmation suffices. Label drafts;
   saving a draft must not advance completed state.
2. Read latest state, preserve unknown keys and history. If JSON is malformed,
   preserve its bytes and report the problem; do not reset it to empty.
3. Before replacing confirmed stage outputs, retain timestamped revisions.
   Save outputs, read them back and validate required sections/JSON.
4. Lead merges decisions, assumptions, preferences and reviews as needed.
   For arrays append records; for existing object containers preserve the shape
   and extend the existing list. Never append raw JSON text or replace history
   with one new record. Resolve ambiguous legacy formats before writing.
5. Append session summary, then write current-stage.json last as the transition
   marker. Use atomic replacement when supported, otherwise write/read back
   each file. On partial failure keep the stage pending, say what succeeded and
   what needs retrying; do not claim an all-or-nothing transaction.
6. Report actual save results. Future recovery depends on durable storage,
   not merely a file existing in scratch now.

## New state formats
Preserve extra keys in existing files. Example current-stage.json:
```json
{
  "numbering_version": 2,
  "stage": "05-mvp-design",
  "status": "completed",
  "next_stage": "06-conversion-loop",
  "summary": "Design confirmed; experiment not run",
  "completed_at": "2026-10-26T15:30:00+07:00",
  "skipped_stages": [],
  "open_questions": [],
  "stale_outputs": []
}
```
Use actual ISO timestamps with the user's timezone, not this example timestamp.
If status is completed, resume next_stage; if draft/in_progress, resume stage.
next_stage execution means operating work, not an unknown skill. On rollback set
the real destination ID and mark affected downstream outputs stale pending review.
Record skips with stage, reason, user authorization and missing evidence.
There are eight numbered stages, 01 through 08, with no gaps.

New decisions.json and reviews/dashboard.json are arrays of records with id,
recorded_at, stage, decision/review and evidence. Use unique IDs; check them on
retries to avoid duplicates after partial saves. New assumptions.json is an array
with id, statement, status, evidence and updated_at. New statuses are unverified,
supported, rejected and inconclusive. Preserve legacy statuses when reading;
map explicitly if migrating. Plan confirmation is a decision, not validation.

## Compatibility with projects from versions 1.1.2 and earlier

Use numbering_version 2 for new current-stage.json checkpoints. Old projects may
omit the field. Resolve by the full semantic stage ID, never the number alone.

| Historical ID / output folder | Current canonical ID / output folder |
| --- | --- |
| 06-mvp-design (or older 06-mvp) | 05-mvp-design |
| 07-conversion-loop | 06-conversion-loop |
| 08-asset-ops | 07-asset-ops |
| 09-dashboard-review | 08-dashboard-review |

01-resource-audit, 02-niche-positioning, 03-value-proposition, 04-business-model
and execution retain their meaning. Use the table to interpret stage, next_stage,
skipped_stages and stale_outputs in memory. A bare numeric stage such as "06"
without an identifying skill/name/version is ambiguous; inspect accessible outputs
or ask one clarification, never guess whether it means old MVP or new conversion.

Read canonical outputs first, then the corresponding historical folder when the
canonical output is absent. If both contain conflicting confirmed results, surface
the conflict; do not choose by folder number or silently overwrite either.
Write new outputs to canonical folders. On the next authorized save, the lead
writes canonical IDs in the active checkpoint with numbering_version 2, preserving
unrelated keys, prior state revision and old decision/review history. Do not rewrite
historical records or mark any extra stage complete merely due to renumbering.
Display current step numbers to the user, even when resuming a legacy checkpoint.

Read existing date-only 07/08 and historical 08/09 review/asset files as legacy.
Name new current 07/08 files YYYYMMDD-HHmmss in the user's timezone; add a counter
on collision. Do not rename/delete old project files to enforce the new convention.
