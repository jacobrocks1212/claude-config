---
kind: investigation-spec
bug_id: adhoc-run-end-tests-leak-real-repo-state
---

# `--run-end`/`--marker-present` hermetic subprocess tests silently reach the real repo — Investigation Spec

> The `test_p7_run_end_*` (7) and `test_marker_present_cli_absent_then_present_and_readonly` (1)
> subprocess-family tests in `user/scripts/test_lazy_core.py` isolate the **run marker / registry
> / deny-ledger / telemetry-ledger** location via `LAZY_STATE_DIR`, but never pass `--repo-root` to
> the `lazy-state.py` subprocess they shell — so `--repo-root` defaults to `os.getcwd()`, which is
> the REAL claude-config checkout whenever pytest is invoked from it. Two concrete, reproduced
> consequences: (1) the shared `_seed_efficacy_breadcrumb` test helper's `interventions_covered`
> flag was satisfied *by accident* via a REAL read of the REAL repo's `docs/interventions/*.md`
> presence (not a write) — the marker's `repo_root` field defaulted to the real, genuinely
> interventions-bearing checkout; (2) two of the eight tests (`..._checkpoint_attended_no_auth_refuses`,
> `..._terminal_nonsanctioned_reason_refuses_without_auth`) never seed the breadcrumb at all, so they
> were silently validating the WRONG gate — the earlier-positioned
> `efficacy-future-check-unenforced-orchestrator-prose` refusal (whose message hardcodes the literal
> citation strings `[efficacy-future-check-unenforced-orchestrator-prose]` /
> `[interventions-telemetry-repo-scope-split-brain]` and literal operator instructions to run
> `efficacy-eval.py --repo-root <claude-config>` / `incident-scan.py --repo-root <claude-config>`
> against the real repo) — not the checkpoint/terminal-reason stop-authorization gate their names and
> docstrings claim to exercise. This is consistent with the field report that two independent agents
> observed real intervention/feature ids in test stdout and treated the refusal's literal
> instructions as real commands to run — see `docs/bugs/_archive/adhoc-incident-hook-deny-19343d-r2/SPEC.md`
> for the resulting fallout (that investigation's own root cause is a separate, correctly-confirmed
> phenomenon — an abnormally long-lived run — but the mechanism traced here is the plausible
> proximate cause of the *test-output-driven* confusion that led to real actions being taken against
> production state during that session).

**Status:** Fixed
**Severity:** Medium
**Discovered:** 2026-07-13
**Fixed:** 2026-07-13
**Fix commit:** 5e7c8793
**Placement:** docs/bugs/adhoc-run-end-tests-leak-real-repo-state
**Related:** `docs/bugs/_archive/adhoc-incident-hook-deny-19343d-r2` (field fallout context);
`user/scripts/test_lazy_core.py` (fix site); `user/scripts/lazy_core.py` (`drop_efficacy_breadcrumb`,
`_repo_is_interventions_bearing`, `notify_event`, `_load_notify_config`) (read-only leak surfaces,
unchanged); `user/scripts/CLAUDE.md` (per-repo keyed state dir contract, `LAZY_STATE_DIR` override)

---

## Verified Symptoms

1. **[VERIFIED]** None of the 8 named tests (`test_p7_run_end_checkpoint_attended_no_auth_refuses`,
   `test_p7_run_end_checkpoint_attended_with_auth_succeeds`,
   `test_p7_run_end_checkpoint_unattended_no_auth_allowed`,
   `test_p7_run_end_terminal_sanctioned_reason_allowed`,
   `test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth`,
   `test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed`,
   `test_p7_run_end_terminal_no_terminal_reason_adds_deprecation`,
   `test_marker_present_cli_absent_then_present_and_readonly`) passed `--repo-root` to the
   `lazy-state.py` subprocess they invoke. `lazy-state.py`'s `--repo-root` argparse default is
   `os.getcwd()` (`user/scripts/lazy-state.py:11394`), so every one of these subprocesses ran bound
   to whatever directory pytest was invoked from — the real claude-config checkout in the ordinary
   case.
2. **[VERIFIED]** `claude_state_dir()` (`user/scripts/lazy_core.py:11618-11658`) IS correctly
   hermetic: `LAZY_STATE_DIR` set → returns that exact dir with NO repo-keying, so the run
   marker/registry/deny-ledger/telemetry-ledger/notify-ledger writes these tests make are already
   isolated from `~/.claude/state/<real-repo-key>/`. This is not the leak surface.
3. **[VERIFIED, reproduced]** `_seed_efficacy_breadcrumb(state_dir)` (pre-fix,
   `user/scripts/test_lazy_core.py:11647`) called `lazy_core.drop_efficacy_breadcrumb()` with NO
   `covered_repo_root` argument. `drop_efficacy_breadcrumb`'s fallback (`lazy_core.py:17580-17597`)
   reads the LIVE marker's own `repo_root` field — which, per symptom 1, was the real checkout —
   and calls `_repo_is_interventions_bearing(real_checkout)` (`lazy_core.py:17516-17537`), which
   globs the REAL `docs/interventions/*.md` and returns True (the real repo genuinely has 30+ such
   files). Reproduced by hand: seeding the breadcrumb via the unpatched helper against a
   `--run-start` invoked with no `--repo-root` writes a crumb whose `interventions_covered` is
   `True` only because the real directory was read. This is a REAL-REPO READ (not a write) inside a
   nominally hermetic test.
4. **[VERIFIED, reproduced]** Two of the eight tests never call `_seed_efficacy_breadcrumb` at all:
   `test_p7_run_end_checkpoint_attended_no_auth_refuses` (asserts a checkpoint-stop-authorization
   refusal) and `test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth` (asserts a
   terminal-reason refusal). Manually invoking their exact subprocess sequence (pre-fix) shows
   `--run-end` refuses with:
   ```
   "refused": "No efficacy-flush breadcrumb COVERING THE INTERVENTIONS-BEARING SCOPE for this
   run. ... `efficacy-eval.py --repo-root <claude-config>`, `efficacy-eval.py --canary
   --repo-root <claude-config>`, and `incident-scan.py --repo-root <claude-config>` ...
   [efficacy-future-check-unenforced-orchestrator-prose] [interventions-telemetry-repo-scope-split-brain]"
   ```
   — the `efficacy-future-check-unenforced-orchestrator-prose` gate
   (`user/scripts/lazy-state.py:12541-12581`), which runs BEFORE the checkpoint gate
   (`lazy-state.py:12605-12643`) and the terminal-reason gate (`lazy-state.py:12646-12671`) inside
   the same `--run-end` handler. Both tests' assertions (`returncode == 1`,
   `run_marker_deleted is False`, `"refused" in out`, marker file still on disk) are satisfied by
   ANY refusal, so they were passing while silently validating the WRONG gate — the
   checkpoint/terminal-reason stop-authorization logic these tests exist to pin was NOT exercised.
5. **[VERIFIED]** The refusal message in symptom 4 literally instructs the reader to run
   `efficacy-eval.py --repo-root <claude-config>` and `incident-scan.py --repo-root <claude-config>`
   against the real, interventions-bearing repo. `efficacy-eval.py --repo-root <repo>` (non-`--dry-run`)
   evaluates real hypothesis records under `docs/interventions/*.md` and, on a REFUTED verdict,
   auto-enqueues a `reconsider-<id>` bug via the sanctioned `--enqueue-adhoc --type bug` path
   (`user/scripts/CLAUDE.md` § `efficacy-eval.py` row) — i.e. a REAL production side effect. An
   agent debugging a test failure by literally following the refusal's instructions (rather than
   recognizing it as a fixture-isolation defect) would run the real trio against the real repo,
   producing exactly the field-observed symptom ("real intervention ids in test output", "attempts
   real reconsider-enqueues").
6. **[VERIFIED — latent, not fired this session]** `notify_event("flush", ...,
   str(args.repo_root), ...)` (`lazy-state.py:12712-12721`, inside the same `--run-end` handler,
   called unconditionally whenever a marker existed pre-delete) calls
   `lazy_core._load_notify_config()` (`lazy_core.py:19724-19752`), which reads
   `Path.home() / ".claude" / "notify.json"` — a REAL, machine-global, untracked operator config
   file, NOT scoped by `LAZY_STATE_DIR` — merged with the inherited `LAZY_NOTIFY_URL` env var. When
   configured (the documented `operator-halt-notifications` feature), every successful `--run-end`
   in this family would derive `link = _github_remote_url(repo_root)` (shells `git remote get-url`
   against `args.repo_root` — the real repo in the unpatched tests) and send a REAL ntfy push
   notification. Confirmed `~/.claude/notify.json` is currently absent on this machine (so no send
   fired during THIS investigation's reproductions), but this is a live hazard the moment the
   operator configures it — an independent latent leak surface via the same `--repo-root` default,
   fixed by the same isolation (never fires with a fixture path pointed at a temp dir; and even if
   it did, `notify.json`'s absence/`LAZY_NOTIFY_DISABLE` remain the config-level kill switch — this
   fix does not touch that surface, it just stops feeding it a real repo path).
7. **[VERIFIED — latent, gated off in practice]** `flush_cloud_telemetry_segment(Path(args.repo_root))`
   (`lazy-state.py:12703-12705`) would write into `<repo_root>/docs/telemetry/cloud/` (a
   git-tracked path INSIDE the repo, not the state dir) had any of these fixtures passed `--cloud`
   at `--run-start`. `flush_cloud_telemetry_segment` (`lazy_core.py:17902-17942`) gates on
   `marker.get("cloud")`, and none of the 8 target tests pass `--cloud`, so this specific class did
   not fire this session — noted as defense-in-depth scope for the same `--repo-root` isolation fix
   (any future `--cloud` variant of this fixture family inherits the fix automatically).

## Reproduction Steps

1. `cd claude-config` (a checkout with `docs/interventions/*.md` present — true of every real
   checkout).
2. Run, e.g., `test_p7_run_end_checkpoint_attended_no_auth_refuses`'s subprocess sequence by hand
   with `LAZY_STATE_DIR` pointed at a temp dir and NO `--repo-root` passed to either `--run-start`
   or `--run-end`.
3. Observe: (a) the marker written by `--run-start` records `"repo_root": "<cwd>"` — the real
   checkout; (b) `--run-end --reason checkpoint` (no auth) refuses with the
   `efficacy-future-check-unenforced-orchestrator-prose` message (symptom 4), not a
   checkpoint-specific one, even though the test's docstring and assertions are about the
   checkpoint stop-authorization gate.

**Expected:** each test in this family exercises exactly the gate its name/docstring describes,
using state (`LAZY_STATE_DIR`) AND repo (`--repo-root`) fixtures that are both fully hermetic — no
subprocess in this family should ever read or write anything under the real checkout or the real
`~/.claude/state/<real-repo-key>/`.
**Actual (pre-fix):** `--repo-root` silently defaults to the real checkout in all 8 tests; 2 of the
8 silently validate the wrong gate as a result; the refusal message they trip literally instructs
running two production-mutating scripts against the real repo.
**Consistency:** deterministic given the trigger — this is a static code-path fact
(`argparse` default + fallback-read order), not a flaky/ambient-state race, in THIS specific
subprocess family. (Ambient-state sensitivity in the broader pipeline — e.g. a concurrently-live
`LAZY_ORCHESTRATOR`/`LAZY_CYCLE_SUBAGENT` env var inherited from the invoking shell — is a
documented, separate, and correctly-designed concern of `refuse_if_cycle_active`; it is not what
this bug fixes and is unaffected by this fix.)

## Evidence Collected

### Source Code

- `user/scripts/lazy-state.py:11394` — `parser.add_argument("--repo-root", default=os.getcwd(), ...)`.
- `user/scripts/lazy-state.py:12541-12581` — the `efficacy-future-check-unenforced-orchestrator-prose`
  gate, positioned BEFORE the checkpoint gate (`:12605-12643`) and terminal-reason gate
  (`:12646-12671`) inside the `--run-end` handler.
- `user/scripts/lazy-state.py:12703-12705`, `:12712-12721` — `flush_cloud_telemetry_segment` /
  `notify_event`, both called with `args.repo_root` verbatim.
- `user/scripts/lazy_core.py:17540-17625` (`drop_efficacy_breadcrumb`),
  `:17516-17537` (`_repo_is_interventions_bearing`) — the real-repo-read mechanism (symptom 3).
- `user/scripts/lazy_core.py:19724-19752` (`_load_notify_config`) — reads
  `~/.claude/notify.json` unconditionally on any successful `--run-end` reaching `notify_event`
  (symptom 6); NOT scoped by `LAZY_STATE_DIR`.
- `user/scripts/lazy_core.py:11618-11658` (`claude_state_dir`) — confirms the marker/ledger/registry
  isolation IS correct (symptom 2) — the bug is entirely in the untouched `--repo-root` default,
  not in the state-dir chokepoint.
- `user/scripts/test_lazy_core.py:11647` (pre-fix `_seed_efficacy_breadcrumb`) and the 8 target
  test bodies (`:19257` `test_p7_run_end_checkpoint_attended_no_auth_refuses`, `:19298`
  `..._with_auth_succeeds`, `:19340` `..._unattended_no_auth_allowed`, `:19388`
  `test_p7_run_end_terminal_sanctioned_reason_allowed`, `:19452`
  `..._nonsanctioned_reason_refuses_without_auth`, `:19496` `..._with_auth_allowed`, `:19540`
  `test_p7_run_end_terminal_no_terminal_reason_adds_deprecation`, `:20088`
  `test_marker_present_cli_absent_then_present_and_readonly`) — line numbers as of the pre-fix
  revision; none pass `--repo-root`.

### Runtime Evidence

- Manual reproduction (this investigation) of `test_p7_run_end_checkpoint_attended_no_auth_refuses`'s
  exact subprocess sequence, pre-fix: `--run-end` returns the efficacy-gate refusal text quoted in
  symptom 4, confirming the gate-masking.
- Manual reproduction of the fixed sequence (`--repo-root <temp>` + the extended
  `_seed_efficacy_breadcrumb` seeding an explicit disposable `docs/interventions/*.md` fixture under
  a temp dir, never the real repo): `--run-end` reaches and refuses via the checkpoint
  stop-authorization gate specifically (`"Stop-authorization gate: this is an ATTENDED run..."`,
  `"attended": true`), proving the fix restores the intended coverage.
- `python -m pytest user/scripts/test_lazy_core.py -k "test_p7_run_end or test_marker_present" -q`
  — 8 passed, pre- and post-fix (the pre-fix pass was for the wrong reason on 2 of the 8; see
  Proven Findings).

### Git History

No prior commit touches `--repo-root` handling in this test family; the `efficacy-future-check-
unenforced-orchestrator-prose` gate (which pre-empts the checkpoint/terminal-reason gates) was
added after this test family, explaining why the 2 masked tests were originally green for the
right reason and silently drifted to green-for-the-wrong-reason once the new gate landed ahead of
them in the handler — a **fixture-vs-production-drift** class, not a one-time authoring mistake.

## Theories

### Theory 1: Missing `--repo-root` isolation causes real-repo reads + fixture masking (CONFIRMED)
- **Hypothesis:** the test family's `LAZY_STATE_DIR`-only isolation is incomplete — `--repo-root`
  defaults to the real checkout, and a later-added gate (the efficacy breadcrumb check) that reads
  real repo-derived state pre-empts 2 of the 8 tests' intended gates.
- **Supporting evidence:** symptoms 1-5, reproduced by hand both pre- and post-fix.
- **Status:** Confirmed.

### Theory 2: The state dir itself (`LAZY_STATE_DIR`) is not properly isolated (RULED OUT)
- **Hypothesis:** marker/ledger/registry writes reach the real keyed state dir
  `~/.claude/state/853ac81ed4c78fc48ca40112a1426e224f3475bb/`.
- **Supporting evidence:** none — `claude_state_dir()`'s `LAZY_STATE_DIR` override check runs
  BEFORE any repo-keying and returns the override dir exactly (symptom 2). Verified empirically:
  zero-byte-diff hash/mtime snapshot of `~/.claude/state/` across a full `test_lazy_core.py` run
  (see Verification below).
- **Status:** Ruled Out.

## Proven Findings

1. **The real-repo leak is entirely a `--repo-root` default gap**, not a state-dir isolation gap.
   `LAZY_STATE_DIR` correctly isolates every marker/ledger/registry write in this family; the only
   consumer of the un-isolated `args.repo_root` in the code paths these 8 tests reach is a
   READ (`_repo_is_interventions_bearing`'s glob, `_github_remote_url`'s `git remote get-url`) —
   confirmed no write into the real repo's tracked files occurred in this session.
2. **2 of the 8 tests were fixture-masked** — silently validating an unrelated, earlier-positioned
   gate instead of their own named gate, because their loose assertions (exit code + generic
   `"refused"` key + marker-still-on-disk) are satisfied by ANY `--run-end` refusal.
3. **The refusal message an agent would see while debugging this class of masking literally
   instructs running two production-mutating scripts against the real repo** — the most plausible
   proximate mechanism for the field-observed "real intervention ids in test output" / "attempts
   real reconsider-enqueues" symptoms, though the specific `adhoc-incident-hook-deny-19343d-r2`
   fallout this bug was asked to cite was independently investigated and attributed to an
   unrelated, confirmed root cause (an abnormally long-lived run) — the two are not shown to be the
   same causal chain, but both are consistent with real production side effects following from
   confusing test-harness output.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Hermetic test fixtures | `user/scripts/test_lazy_core.py` (8 test bodies + `_seed_efficacy_breadcrumb`) | Fixture-only fix: add `--repo-root <temp fixture>` to every subprocess leg; extend `_seed_efficacy_breadcrumb` to seed its own disposable interventions-bearing fixture and pass it explicitly as `covered_repo_root`; strengthen the 2 masked tests' assertions to pin the specific gate. |
| Production code | `user/scripts/lazy-state.py`, `user/scripts/lazy_core.py` | UNCHANGED. The `--repo-root` default (`os.getcwd()`), the gate ordering, `drop_efficacy_breadcrumb`'s fallback, and `notify_event`/`_load_notify_config` all behave exactly as designed for a real orchestrator invocation (which legitimately wants the real repo as its default). The defect is fixture hermeticity, not production behavior. |

## Open Questions

None outstanding. The fix is fixture-only per the traced root cause; no production seam needed an
env-override capability it didn't already have (`--repo-root` was always available as an explicit
flag — the tests simply never passed it).

## Disposition

**Concluded → ready for `/plan-bug` / direct fix.** Fix is TDD-shaped and test-only: isolate
`--repo-root` in all 8 named tests, extend `_seed_efficacy_breadcrumb` to stop depending on the
real repo's `docs/interventions/`, and strengthen the 2 masked tests to assert on the specific gate
they claim to cover. See `PHASES.md` for the executed plan and `FIXED.md` for the closing receipt.
