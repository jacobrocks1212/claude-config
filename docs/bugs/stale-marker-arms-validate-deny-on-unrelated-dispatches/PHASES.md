# Implementation Phases — Stale/same-repo marker arms validate-deny on unrelated dispatches (over-fire)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a harness defect fix in `user/hooks/` + `user/scripts/` (bash hook + Python state-machine / guard). There is NO app surface, store, audio path, or UI state to drive through the live Tauri + MCP runtime. Validation is fully covered by the hermetic in-file `--test` smoke harnesses (`test_hooks.py` end-to-end bash-hook fixtures, `test_lazy_core.py`, `lazy-state.py --test`) per the mcp-testing SPEC's "structurally outside MCP reach (build/dev tooling, no app integration)" class.

## Scope (locked by SPEC Resolved Decisions — DO NOT re-litigate)

This PHASES.md addresses the **over-fire only** (D1 + D2). The under-fire single-slot marker-ownership race (Symptom 2/3, Theory 2, Proven Finding #2) is **split out** per **D3=A** to a dedicated follow-up bug — see Cross-feature Integration Notes below.

- **D1 — Owning-session scoping at the gate (A).** `lazy-dispatch-guard.sh` must pass `--session-id` into `lazy-state.py --marker-present`; the handler treats the marker as "present" ONLY when the caller's session is the marker's bound owner. A dispatch from the OWNING orchestrator session runs the full guard exactly as today; a dispatch from any OTHER session sees "no marker for me" → fast-path allow, never policed, never ledgered.
- **D2 — Allow-through (A) + pre-bind no-debt deny.** Under D1 a non-owning-session dispatch never reaches the guard's deny logic (gate fast-path-allows). For the narrow unbound-marker pre-bind residual window (`session_id: None` → path B can't fire), PAIR a `_deny_no_ledger`-style no-debt deny so even a pre-bind deny carries no hardening debt.

**Sacred invariants (all phases MUST preserve):** fail-OPEN on any error; NEVER DESTROY the owning run's marker from a non-owner read (Phase 8 WU-8.1 — `read_run_marker` path B is non-destructive); NEVER weaken the depth-1 hardening cap; the two reads (the gate's `--marker-present` and the guard's own `read_run_marker(session_id=…)`) MUST agree.

## Validated Assumptions (ground truth from the Touchpoint Audit — code-provable, no runtime spike needed)

These are code-provable facts confirmed by reading the actual source during planning — not runtime-coupled. No runtime spike is required (the whole feature is hermetically testable):

- **The `--marker-present` handler ALREADY honors `--session-id`.** `lazy-state.py` line 5953 defines `--session-id`; lines 6210-6212 call `lazy_core.read_run_marker(session_id=args.session_id)`. The D1 handler half is DONE. The ONLY gap is that `lazy-dispatch-guard.sh` (lines 81-90) calls `--marker-present --repo-root "$CWD"` with **no `--session-id`**. So D1 reduces to: extract `session_id` in the hook and pass it through.
- **The guard's OWN read is ALREADY session-aware.** `lazy_guard.py::guard()` line 563 calls `read_run_marker(session_id=session_id)` (session from hook-input, line 528); a non-owner session gets `marker=None` → fast-path allow (lines 564-572). After D1, the gate read and the guard read AGREE — both keyed on session. The over-fire today is purely that the *gate* lets the guard run for non-owner sessions; once the gate is session-scoped, non-owner dispatches never invoke the guard at all.
- **`_deny_no_ledger` already exists** (`lazy_guard.py` lines 252-267) as the in-codebase precedent for "deny but charge no hardening debt" (the transcription-slip path). D2's pre-bind no-debt deny reuses it — no new ledger schema field is needed under D2-A.
- **`read_run_marker` staleness path B is non-destructive** (`lazy_core.py` lines 6195-6206) and fires ONLY when BOTH caller and marker carry non-None `session_id`. An unbound marker (`session_id: None`) cannot trip path B — this is exactly the D2 pre-bind residual window.
- **End-to-end bash-hook test infrastructure exists** (`test_hooks.py`: `_run_bash(_GUARD_SH, …)`, `_base_env(state_dir)`, `_write_marker_in_dir(state_dir, session_id=…)`, `_e1_preToolUse_json(prompt, tool_use_id=, session_id=)`, hermetic `LAZY_STATE_DIR`). Over-fire fixtures extend these helpers; no new harness scaffolding is needed.

## Cross-feature Integration Notes

No upstream `**Depends on:**` block (harness-internal bug, not a queue feature). The relevant prior art is documented in the SPEC's `**Related:**`:

- **`multi-repo-concurrent-runs` (COMPLETE 2026-06-16):** introduced per-repo keyed state via `claude_state_dir()` and rewired the three enforcement hooks to the `--marker-present` gate. It closed the cross-REPO leak. This bug fixes the residual SAME-repo / cross-session dimension — it ADDS a `--session-id` argument to the SAME `--marker-present` gate that feature established. Do NOT regress the repo-keying: `--session-id` is passed ALONGSIDE the existing `--repo-root`, never in place of it.

**SPLIT-OUT FOLLOW-UP (D3=A — under-fire ownership race):** the residual single-slot marker-ownership race (a marker overwrite / wrong-session bind makes the true owner read "owned by someone else → allow", silently disarming enforcement mid-run) is OUT OF SCOPE here and is spun off to a dedicated bug:

- **Spin-off bug:** `docs/bugs/single-slot-marker-ownership-race-disarms-owning-run/`
- **Reverse-reference contract (both directions):** this PHASES.md (the origin) names the spin-off here; the spin-off's SPEC names this origin (`stale-marker-arms-validate-deny-on-unrelated-dispatches`) as its origin. The spin-off carries Theory 2, Proven Finding #2, the under-fire Reproduction Steps, and the marker-ownership-model Affected-Area row — all documented in THIS SPEC as the origin record but deferred from THIS PHASES.md.

---

### Phase 1: Session-scope the dispatch-guard gate (D1)

**Scope:** Make `lazy-dispatch-guard.sh` pass the hook-input `session_id` into `lazy-state.py --marker-present`, so the gate that decides "run the guard at all" treats the marker as present ONLY for the marker's bound owning session. A dispatch from any other session in the same repo fast-path-allows at the gate — never reaching the guard's deny logic. This is the core over-fire fix.

**Deliverables:**
- [x] In `user/hooks/lazy-dispatch-guard.sh`, extend the existing single python payload-parse (currently extracts only `cwd`, lines 69-74) to ALSO extract `session_id` from the hook-input JSON in the SAME invocation (do NOT add a second python process). Emit both values parseably (e.g. two lines, or a delimiter) and assign to `CWD` and `SID`.
- [x] Pass `--session-id "$SID"` into the existing `--marker-present --repo-root "$CWD"` call (lines 81-90), ONLY when `$SID` is non-empty (omit the flag on an empty parse so the behavior degrades to today's session-blind gate — fail-OPEN: a parse miss must never silently disable enforcement).
- [x] Preserve fail-OPEN: any payload-parse failure leaves `SID` (and/or `CWD`) empty → the existing fall-through-to-guard path is unchanged. The `--repo-root` argument and per-repo keying are untouched.
- [x] Tests: end-to-end bash-hook fixtures in `test_hooks.py` (see Runtime Verification) proving an OWNING-session dispatch still runs the guard (deny/allow exactly as today) and a NON-OWNING-session dispatch fast-path-allows at the gate with NO deny-ledger entry.

**Implementation Notes (2026-06-19):**
- **Work landed:** Extended the single python payload-parse in `lazy-dispatch-guard.sh` to print BOTH `cwd` and `session_id` (two newline-separated lines), split via the bash builtin `read`/parameter-expansion (NOT `sed`/`head` — those coreutils binaries are not guaranteed on a non-login git-bash PATH, the same hazard the file already documents for `dirname`). Pass `--session-id "$SID"` into the existing `--marker-present --repo-root "$CWD"` query only when `$SID` is non-empty; empty SID omits the flag (fail-OPEN to the session-blind gate). `--repo-root` / per-repo keying untouched.
- **CRLF hardening (load-bearing pitfall):** the python text-mode stdout on Windows git-bash carries a trailing `\r` on each line, which `read -r` / the `${PARSED#*$'\n'}` expansion preserve. A stray `\r` on `$CWD` mangles the repo key → a DIFFERENT keyed subdir → marker "absent" → spurious fast-path allow (this surfaced as a same-repo two-repo-isolation regression mid-implementation). Both `CWD` and `SID` now strip ALL `\r` via the builtin `${var//$'\r'/}` expansion before reaching the gate. (Likely also closed a latent CRLF risk in the pre-existing single-value cwd path.)
- **Honest test-first scope finding (⚖ recorded in plan/summary):** for a BOUND marker the guard's OWN session-aware read (`lazy_guard.py::guard()` line 563, `read_run_marker(session_id=…)`) ALREADY self-allows a non-owner BEFORE the registry read — so the WU-1 gate scoping produces NO deny/ledger/breadcrumb observable that differs from the session-blind gate end-to-end (both yield empty stdout). WU-1 is therefore a defense-in-depth + D1 "two reads must AGREE" change. The falsifiable failing-first contract is at the gate seam, not the deny seam: `test_marker_present_non_owner_session_reports_absent` (handler honors `--session-id`: owner exit 0, non-owner exit 1) + `test_guard_hook_wires_session_id_into_marker_present` (source lock that the hook passes the flag, preserving `--repo-root`). The plan's WU-2 expectation that the non-owner deny+ledgers pre-fix holds ONLY for the UNBOUND marker (Phase 2's target), not the bound case.
- **Files:** `user/hooks/lazy-dispatch-guard.sh` (extended parse + session-scoped gate + CRLF strip); `user/scripts/test_hooks.py` (4 new fixtures: gate-unit, hook-source-lock, end-to-end non-owner-gate-does-not-invoke-guard, owner-still-denies-and-ledgers). `user/scripts/lazy-state.py` VERIFIED unchanged — line 5953 `--session-id` arg + lines 6210-6212 `read_run_marker(session_id=args.session_id)` already honor it (no edit needed, as the plan predicted).
- **Integration note for Phase 2:** the gate+guard now agree for BOUND markers (non-owner never policed). The sole residual same-repo deny surface is the UNBOUND (`session_id: None`) pre-bind window — verified above that an unbound marker + non-owner STILL denies + ledgers through the real bash guard (path B needs BOTH non-None). That is exactly Phase 2's (D2) target.

**Minimum Verifiable Behavior:** Run `python user/scripts/test_hooks.py` — the new over-fire fixtures pass: with a marker bound to `session_A`, an unregistered-prompt dispatch carrying `session_B` exits 0 with NO output (gate fast-path allow) and writes NO `lazy-deny-ledger.jsonl` entry; the same dispatch carrying `session_A` produces the deny JSON (guard ran) exactly as the pre-fix baseline.

**Runtime Verification** *(checked by the hermetic test harness — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python user/scripts/test_hooks.py` passes, including the new owning-vs-non-owning gate fixtures (non-owner: no deny, no ledger row; owner: guard runs identically to baseline).
- [ ] <!-- verification-only --> `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` stay green (the `--marker-present` handler is unchanged; confirm no regression in the byte-pinned baselines).

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior in this phase (harness hook + state-script wiring; validated via the hermetic bash-hook + `--test` harnesses, not MCP).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/lazy-dispatch-guard.sh` — extend the existing payload-parse to also yield `session_id`; pass `--session-id "$SID"` into the existing `--marker-present` call (verified: lines 69-74 parse cwd; lines 81-90 call the gate). REUSE the single existing python invocation; do NOT add a second.
- `user/scripts/lazy-state.py` — **VERIFY ONLY, no edit expected.** The `--session-id` arg (line 5953) and the handler's `read_run_marker(session_id=args.session_id)` (lines 6210-6212) already honor it. Confirm during implementation; edit only if a defect is found.
- `user/scripts/test_hooks.py` — add owning-vs-non-owning gate fixtures (REUSE `_run_bash`, `_GUARD_SH`, `_base_env`, `_write_marker_in_dir(session_id=)`, `_e1_preToolUse_json(session_id=)`).

**Testing Strategy:**
Hermetic end-to-end through the REAL bash hook with a temp `LAZY_STATE_DIR`. Bind the marker to `owner_session`; assert (a) owner dispatch → guard runs (deny for an unregistered prompt, with a ledger row — baseline behavior); (b) non-owner dispatch → exit 0, empty stdout, no ledger file/row created. The non-owner assertion is the over-fire regression lock.

**Integration Notes for Next Phase:**
- After this phase the gate and the guard's own `read_run_marker` agree (both session-keyed). The ONLY residual deny surface for a same-repo dispatch is when the marker is live but UNBOUND (`session_id: None`) — path B cannot fire, the gate cannot scope by owner yet, so the guard runs and an unregistered prompt is denied. That residual window is Phase 2's target (D2 pre-bind no-debt deny).
- Do NOT change the deny REASON text or the depth-1 hardening cap — Phase 2 only changes whether a pre-bind deny is LEDGERED, never the allow/deny verdict shape.

---

### Phase 2: No-debt deny for the unbound-marker pre-bind window (D2)

**Scope:** Close the narrow residual window Phase 1 leaves: when a live marker exists but is still UNBOUND (`session_id: None`, bind-pending — no orchestrator ALLOW has bound it yet), the gate cannot scope by owner and the guard runs. An unrelated dispatch in that window is denied. Per D2-A, route that pre-bind deny through `_deny_no_ledger` so it carries NO hardening debt (mirroring the existing transcription-slip precedent) — the deny verdict is preserved, only the ledger append is suppressed.

**Deliverables:**
- [ ] In `user/scripts/lazy_guard.py::guard()`, at the default-deny tail (the genuine no-route path, currently `_deny_and_ledger(_default_deny_reason(), …)` near line 780) AND/OR the consumed-by-other / stale-entry default-deny branches: when the live marker is UNBOUND (`marker.get("session_id") is None`), route the deny through `_deny_no_ledger(_default_deny_reason())` instead of `_deny_and_ledger(...)` — no ledger append, no hardening debt. The deny JSON shape is byte-identical (the bash wrapper is unaffected — a deny is a deny).
- [ ] Scope the no-debt routing PRECISELY: it applies ONLY when the marker is unbound. A deny under a BOUND marker (the owning session dispatching an unregistered/mangled prompt — a genuine validate-deny / harness gap) MUST still `_deny_and_ledger` and accrue debt exactly as today. Do NOT broaden the no-debt path to bound-marker denies.
- [ ] Preserve the hardening-cap and ref-token deny paths unchanged — only the GENERIC default-deny under an unbound marker becomes no-debt. (The bare-`@@lazy-ref` unresolved deny and the depth-1 hardening-cap deny keep their existing ledger semantics.)
- [ ] Preserve fail-OPEN: any error reading `marker.get("session_id")` falls back to the existing `_deny_and_ledger` behavior (debt-preserving is the safe default — never silently drop a genuine gap).
- [ ] Tests: unit/end-to-end fixtures proving a pre-bind (unbound-marker) unrelated deny writes NO ledger entry and does NOT raise `pending_hardening()`, while a bound-marker unregistered-prompt deny still ledgers and DOES raise `pending_hardening()`.

**Minimum Verifiable Behavior:** Run `python user/scripts/test_hooks.py` — with an UNBOUND marker (`session_id: None`) and an unregistered prompt, the guard returns deny JSON but `lazy-deny-ledger.jsonl` gains NO row and `lazy_core.pending_hardening()` stays 0; with a BOUND marker (owner session) and the same unregistered prompt, the deny DOES append a ledger row and `pending_hardening()` becomes 1.

**Runtime Verification** *(checked by the hermetic test harness — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python user/scripts/test_hooks.py` passes, including the unbound-marker no-debt deny fixture and the bound-marker debt-accrual contrast fixture.
- [ ] <!-- verification-only --> `python user/scripts/test_lazy_core.py` stays green (no regression in `append_deny_ledger_entry` / `pending_hardening` / path-B characterization).
- [ ] <!-- verification-only --> `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` stay green (shared `lazy_core` unaffected behaviorally).

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior (guard deny-ledger semantics; validated via the hermetic harnesses, not MCP).

**Prerequisites:**
- Phase 1: the gate is session-scoped, so the ONLY remaining same-repo deny surface is the unbound-marker pre-bind window this phase targets. (Phase 2 is independent in code but ordered second because it only matters for the window Phase 1 narrows the problem down to.)

**Files likely modified:**
- `user/scripts/lazy_guard.py` — branch the default-deny tail on `marker.get("session_id") is None` to `_deny_no_ledger` (verified: `_deny_no_ledger` exists at lines 252-267; `_deny_and_ledger` at 486; the default-deny tail at ~780; the consumed-by-other / stale branches at ~725/745). REUSE `_deny_no_ledger`; do NOT author a new no-debt helper.
- `user/scripts/test_hooks.py` — add the unbound-marker no-debt fixture + the bound-marker debt-accrual contrast fixture (REUSE `_write_marker_in_dir` WITHOUT a `session_id` to write an unbound marker; assert ledger emptiness via the existing ledger-read pattern).
- `user/scripts/test_lazy_core.py` — add a direct unit assertion on `pending_hardening()` for the no-debt path if the guard-level fixture does not cover it cleanly.

**Testing Strategy:**
Two contrasting hermetic fixtures: (1) UNBOUND marker + unregistered prompt → deny JSON returned, ledger file empty/absent, `pending_hardening()==0`; (2) BOUND marker (owner session) + unregistered prompt → deny JSON returned, exactly one ledger row, `pending_hardening()==1`. The contrast pins that the no-debt routing is scoped to the unbound window and does NOT erode the genuine validate-deny debt path.

**Integration Notes for Next Phase:**
- Last phase. When this phase's work lands, set the top-level `**Status:**` of PHASES (this file's frontmatter is per-phase; the SPEC top-level flip is gate-owned) to `In-progress` — implementation done, validation pending — and let the state machine route to the validation tail. Do NOT write FIXED.md or flip SPEC `**Status:**` to Fixed (gate-owned by `__mark_fixed__`).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed` and writes `FIXED.md` once both phases' work lands and the validation tail (the hermetic `--test` / `test_hooks.py` / `test_lazy_core.py` suites, then the coverage audit) passes. This PHASES.md never authors that flip or receipt.

---

## Decomposition Rationale

- **Two phases, not one:** D1 (gate session-scoping in the bash hook) and D2 (pre-bind no-debt deny in the Python guard) touch different files and different layers and have independent failing-test contracts, so they decompose cleanly. They are NOT circular: Phase 2's relevance is NARROWED by Phase 1 but its code does not depend on Phase 1's edit.
- **No terminal-MCP-stacking risk:** both phases declare MCP `N/A` legitimately — there is genuinely no app/MCP surface (harness scripts + hook). The mcp-testing SPEC's "structurally outside MCP reach" class applies; verification is the hermetic `--test` + bash-hook harnesses, which ARE the runtime observation for this defect class.
- **No new API surface** → no reachability-smoke row required.
- **No platform/variant expansion** → no gate-phase deferral required.
