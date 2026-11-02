# G9 focused security review

Date: 2026-11-01. Reviewer: Software Workshop Security Officer.

Scope: the working-tree Google OIDC, browser session/internal validation, workspace administration, resource-server boundary, G9 migration/RLS and frontend credential handling. This is a focused integration review, not a complete repository security audit. No production data or browser actions were used. No posture score is assigned.

## Result

Two medium-severity recovery-login regressions were reproduced in the isolated PostgreSQL verification environment, reported to the implementing agent, fixed in source and rechecked successfully. No unresolved high-confidence security finding was identified in the reviewed scope. This does not establish production or real Google acceptance.

## Confirmed and resolved findings

### G9-S01 — Subsequent Google login overwrote a linked legacy owner's recovery email

- Severity: Medium, confidence 10/10; availability/identity integrity.
- Original location: `packages/core/goodmcp/google_oidc.py`, final source line 94.
- Before correction, explicit linking preserved the legacy email, but the next ordinary Google login unconditionally updated `users.email` to the Google email. A different Google address therefore changed the configured recovery account lookup and password-login address after an apparently safe link.
- Reproduction: create a password-enabled fixture user, explicitly link a Google subject using a different email, then call ordinary subject provisioning. The first operation kept the legacy email; the second changed it. All inserts and changes were rolled back.
- Correction: profile/email update now applies only to Google-only accounts (`password_hash='!'`).
- Current-source regression check: explicit link followed by ordinary Google login retained the original recovery address. PASS.

### G9-S02 — Duplicate Google email made Cloudflare recovery lookup ambiguous

- Severity: Medium, confidence 10/10; availability.
- Location: `packages/core/goodmcp/cloudflare_sso.py:109-110`.
- G9 deliberately permits different identities with the same email. The pre-existing Cloudflare lookup selected every active account matching the configured owner email, then used `one_or_none()`. A separate Google identity sharing that email caused `MultipleResultsFound`, preventing recovery login. It did not select or impersonate the other account.
- Reproduction: create a password-enabled fixture account and a separate Google identity with the same email, then execute the original recovery selection. `MultipleResultsFound` was observed. The entire transaction was rolled back.
- Correction: the Cloudflare recovery query now restricts selection to password-enabled accounts (`password_hash<>'!'`), whose normalized emails retain a unique index.
- Current-source regression check: duplicate Google email remained a separate identity and the exact current Cloudflare query selected only the recovery account. PASS.

## Evidence and boundary checks

The focused checks used only `goodmcp-g9-verify-20261101t013659z-80388b-auth-1`. The first run confirmed both original defects; the second loaded current host module source in that container, executed provisioning plus the exact current Cloudflare SQL and rolled back. Output contained only PASS/CONFIRMED descriptions, no credentials or tokens.

Source inspection found:

- Google identity ownership uses `(provider, subject)`; email alone does not merge accounts. Explicit linking requires a logged-in session and checks subject/user uniqueness.
- Callback state is signed, expires, is bound to the browser cookie and is persisted as a one-use flow. Consumption commits before token exchange. Nonce, issuer, audience, signature, expiry and verified-email checks precede provisioning.
- Browser sessions use HttpOnly cookies; mutations require same Origin and a session-derived CSRF value. The internal validator requires a separate shared credential. MCP does not accept the browser session cookie.
- Management routes use the issuer database role and current user/membership checks. Workspace owners do not become platform administrators. SQL values use bound parameters.
- Workspace changes serialize on the workspace row; invitation acceptance rechecks the inviter's current authority; owner transfer is atomic with a deferred exactly-one-owner constraint. Revocation triggers revoke token families and request cancellation of queued/running jobs.
- Runtime RLS membership visibility also checks current account activity. Resource verification rejects archived workspaces. Frontend credentials are session-derived CSRF values, without bearer-token persistence in the reviewed auth files.
- The implementing agent added explicit `Jobs.run_permission()` in dispatcher start/heartbeat/publication paths plus a cancellation/state check before start. This was source-reviewed; a real container running during downgrade was not exercised by this reviewer. No exploitable bypass is claimed for the earlier missing explicit calls because revocation triggers already supplied compensating cancellation.

## Limits and remaining release evidence

Actual Google consent/callback using the configured Google project, SMTP delivery, production deployment and downgrade during a running Python container are outside these focused checks. Google project Testing configuration and credentials still require their own acceptance evidence; mocked signatures and local provisioning do not count as real Google success. Full verification results belong in the main G9 report.

## Addendum — shared-project authorization delta

Reviewed the later G9 delta in `packages/core/goodmcp/workflows.py`, the replacement INSERT policies at `infra/migrations/versions/0007_g9.py:119-124`, and `test_member_updates_shared_project_without_becoming_its_lead` in `tests/test_g9_workspaces.py:241`. No actionable role/RLS regression was found in this delta.

Removing the old lead-only check matches `Docs/PLAN-phase-2.md:11`, which defines workspace-shared projects without per-project permissions. `Workflows.project(write=True)` still checks `projects:write`, calls `require_write()` (current owner/admin/member plus `hub:write`), selects by authenticated workspace and project, and locks the row. Save/stage commits retain expected-revision conflict checks. Viewer writes remain forbidden even when the supplied credential contains write scopes. The historical lead remains coordination metadata and is not silently reassigned.

The two replacement INSERT policies still require the transaction workspace, current active membership, authenticated user and writer role. They remove only the per-project lead condition. The retained composite foreign keys bind files to the same workspace/project/plugin version/artifact and operations to the same workspace/project. UPDATE/DELETE grants and immutable-history triggers are unchanged. Runtime membership RLS continues to filter inactive accounts. The delta therefore does not grant a viewer write access, permit cross-workspace links, or allow immutable file/operation history to be rewritten.

Evidence inspected, not rerun by this addendum: `Docs/reports/evidence/G9/local-final-r3/verify.json` records 240 passing core tests, 23 G9 tests, passing G4/G5 wire sections and passing browser-session API HTTP checks; the relevant command exit codes are zero. The new regression test demonstrates a non-lead member saving a shared project while preserving its lead, then verifies viewer rejection. This addendum makes no additional production or browser acceptance claim. Root separately reports three real Google accounts verified by the delegated browser specialist; that is outside this reviewer's direct observations and supersedes the earlier pending-account status only where the main report provides that evidence.
