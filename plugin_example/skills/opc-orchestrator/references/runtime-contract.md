# Shared runtime contract

Apply this contract to every OPC skill. Follow the host's higher-priority rules.
Read once per working context; load stage methods only when needed.

## Conversation and decisions
Respond concisely in the user's language. Explain unfamiliar terms as needed.
Infer teaching, guided or direct mode; avoid mandatory onboarding questionnaires.
Ask one useful question, or up to three closely related lightweight questions.
Reuse confirmed answers and existing authorization; do not ask the same question again.
Present one to three meaningful alternatives with suitability, benefits and costs.
Always allow the user's own version, combination or revision. Three is a maximum
default, never a quota or a completion requirement. Recommend a preferred option
with reasons when useful; only the user adopts business decisions. Stage 01 inventories
resources without ranking business directions. Do not mark incomplete work complete
because of a turn limit; offer a draft checkpoint with open questions instead.

## Delegation and models
When orchestration is used, delegate to real specialists if the host supports it.
Keep the lead in the main conversation; never spawn a second lead. Run dependent
stages sequentially. Supply the matching skill/role profile, confirmed upstream
outputs, preferences, authorization and open questions. Specialists return drafts,
evidence, assumptions and blockers; only the lead asks the user and commits shared state.
A specialist may save stage output only with delegated write scope and confirmation.
Read the single model policy linked from SKILL.md; inspect supported model choices.
When selection is supported, use actual host model/effort selectors with
`fork_turns="none"` and pass context explicitly. Use that policy's fallback.
Record requested and actual model separately; do not claim the main model changed.
Without subagents, disclose single-assistant mode once and continue sequentially.
A directly invoked specialist's current assistant also acts as lead for user
communication and state writes; do not spawn another lead just to save files.

## Files and single-writer state
Treat opc-doc/ as the logical project folder, never a directory inside the plugin.
Follow host storage rules. Read only attached, workspace or explicitly authorized
sources; do not search private storage for other projects. Confirmed conversation
context may replace missing files. Missing file access limits saving/resume, not drafting.
Read the file contract linked from SKILL.md before saving. Only the lead writes
opc-doc/state/*, reviews/dashboard.json and the shared session summary.
Specialists propose changes, never replace shared state themselves.
After confirmation already given or newly obtained, save stage outputs, read back
and validate them, then merge shared state/history. Preserve unrelated keys, old
records and legacy formats. Do not advance after failed writes or validation.
Report partial success accurately; an output saved alone is not a completed transition.
Do not guarantee future-session recovery from a transient workspace.
Use the user's timezone. Use timestamps and collision counters for repeated 07/08 work.
Preserve prior confirmed output revisions before replacement. Read historical stage
IDs and folders using the compatibility table in file-contract.md; write canonical
new IDs without renaming or overwriting legacy project folders.

## Evidence and transitions
Use 01 → 02 → 03 → 04 → 05 → 06 → execution. Scoring is inside 02; 05 is MVP design.
A stage may finish with explicitly accepted unknowns; record their consequences.
For a clearly authorized skip, record skipped stages, assumptions and uncertainty,
then proceed. Ask only if the intended destination or authorization is ambiguous.
Allow requested minimum execution materials in 05/06 and execution: first posts,
message drafts, forms, interview questions, offer pages and delivery checklists.
Do not require 07 or repeated assets before a first experiment can run.
07 organizes reusable operating outputs; 08 reviews observed operations.
Neither is an automatic next step. Drafting does not authorize sending, publishing,
spending or collecting money; external actions require actual user authorization
and compliance with host rules.
Use live sources and cite evidence for market changes, competitor facts, prices
and platform rules; otherwise label unverified hypotheses. Separate observed facts,
user statements, assumptions and unknowns. Scores are qualitative judgments, not
probabilities or revenue promises. A confirmed experiment plan remains unverified;
only observed results may support a proposed hypothesis-status change.
