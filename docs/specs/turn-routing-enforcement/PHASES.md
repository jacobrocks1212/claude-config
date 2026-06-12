# Implementation Phases — Hook-Enforced Turn Routing (+ Harness-Hardening Stage)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this feature targets the claude-config harness itself (hooks, state scripts, skills); there is no AlgoBooth app surface. Verification is via `test_lazy_core.py`, hook pipe-tests, and a live `claude -p` hook harness — the class of standalone tooling with no app integration per docs/features/mcp-testing/SPEC.md.

---

## Touchpoint Summary

The AlgoBooth `npm run audit:touchpoints` gate was **SKIPPED** because this feature's touchpoints live in claude-config, which has no package.json or audit tooling.

**Existing files to be modified:**

- `user/scripts/lazy_core.py` (~163KB — additions must be additive, well-factored functions)
- `user/scripts/lazy-state.py`
- `user/scripts/bug-state.py`
- `user/scripts/test_lazy_core.py`
- `user/skills/lazy-batch/SKILL.md`
- `user/skills/lazy-bug-batch/SKILL.md`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`
- `setup.ps1`
- live `~/.claude/settings.json` (per-machine, untracked)

**New files to be created:**

- `user/hooks/lazy-route-inject.sh` (inject hook)
- `user/hooks/lazy-dispatch-guard.sh` (validate hook)
- `user/skills/harden-harness/SKILL.md` (new skill)
- `user/skills/_components/hardening-dispatch.md` (dispatch template)
- `_components/lazy-batch-prompts/dispatch-<class>.md` files (per dispatch class)
- `docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md` (spike artifacts)
- `docs/specs/turn-routing-enforcement/REGISTRATION.md` (per-machine registration snippet)
- `docs/specs/turn-routing-enforcement/E2E_VALIDATION.md` (live validation results)
- `docs/specs/turn-routing-enforcement/hardening-log/` directory + monthly log files

This repo has no LOC-gate, so no Phase 0 decomposition is required.

---

## Validated Assumptions

The following assumptions were confirmed during the planning session on 2026-06-11. All phases below depend on this ledger — any assumption marked UNRESOLVED is a go/no-go gate for the phase that depends on it.

| # | assumption | how-confirmed | evidence |
|---|---|---|---|
| A1 | `PostCompact` hook event exists; full event list includes UserPromptSubmit, SessionStart, PreToolUse | runtime (docs probe via claude-code-guide agent, 2026-06-11) | docs.claude.com hooks guide — 32 events enumerated incl. PreCompact/PostCompact |
| A2 | `additionalContext` injection supported on UserPromptSubmit, SessionStart, PreToolUse, PostToolUse | runtime (docs probe) | hooks guide "Events Supporting additionalContext"; **PostCompact NOT in that list** — compaction re-injection therefore primarily targets `SessionStart` matcher `compact` (proven pattern: existing `load-branch-docs-context.sh` registration), with PostCompact as a supplementary registration verified in the Phase 2 spike |
| A3 | PreToolUse deny schema is `hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason`, reason is fed back to the model | runtime (docs probe) | hooks guide PreToolUse decision schema; valid values allow/deny/ask/defer |
| A4 | Subagent-dispatch tool matcher: both `Agent` and `Task` are valid matcher names; hooks should match `Agent|Task` | runtime (docs probe) | hooks guide matcher table + example `"matcher": "Agent|Task|Skill"`; actual `tool_name` arriving in hook input captured by Phase 2 spike |
| A5 | UserPromptSubmit fires for programmatic prompts too (not only operator-typed); default timeout 30s, per-hook `timeout` override | runtime (docs probe) | hooks guide firing behavior + timeout defaults |
| A6 | **UNRESOLVED — gates the deny design:** whether PreToolUse fires for tool calls made by NESTED subagents, and what field discriminates an orchestrator-level `Agent` call from a cycle subagent's own legitimate nested dispatch (`session_id`? `transcript_path`?). Docs are explicitly ambiguous. | spike (Phase 2, mandatory go/no-go) | If no discriminator exists, the guard would deny every nested implementer dispatch and brick runs → Phase 2 halts with NEEDS_INPUT.md instead of arming the hook |
| A7 | No registry/nonce/marker mechanism exists today anywhere in lazy_core.py / state scripts (greenfield); streak persistence lives in OS tempdir `lazy-state-last-<sha1[:16]>.json` via `update_repeat_counts` (lazy_core.py:2520) with `_atomic_write` (lazy_core.py:92) | grep | explorer sweep 2026-06-11; `~/.claude/state/` does not exist on this machine |
| A8 | `forward_cycles`/`meta_cycles` are flag-passed (`--forward-cycles N --meta-cycles M`), never persisted — the compaction counter-loss class is real | grep | lazy-state.py argparse ~4764; CLAUDE.md CLI surface |
| A9 | Live laptop `~/.claude/settings.json` registers ZERO hooks and is NOT a symlink; `~/.claude/hooks` symlink is MISSING despite manifest.psd1 defining it; tracked `user/settings.json` carries the DESKTOP machine's hook paths (`C:/Users/JacobMadsen/...`) | runtime (Test-Path probes 2026-06-11) | Phase 6 must repair the hooks symlink and add per-machine registration |
| A10 | `--test` smoke outputs are byte-pinned to committed baselines (`tests/baselines/*-test-baseline.txt`); default (flag-less) output must remain byte-identical — all new behavior must be flag- or marker-gated | grep | user/scripts/CLAUDE.md Testing section |
| A11 | `claude -p` (headless) fires hooks, enabling a scriptable live harness | spike (Phase 2) | docs indicate hooks fire in non-interactive mode; spike records actual behavior |

---

## Cross-feature Integration Notes

Formal dep block: **(none)**

Substantive upstream facts from lazy-hardening Phases 8–11 (Complete) that these phases consume:

- `emit_cycle_prompt()` (lazy_core.py:3316) is the single prompt assembler: probe JSON carries `cycle_prompt`, `cycle_model` ("opus"/"sonnet"), optional `cycle_prompt_refused`; pseudo-skill/terminal probes emit nulls. The registry write (Phase 1) hooks into exactly this path in BOTH lazy-state.py (~line 4961) and bug-state.py (~line 3644).
- The full probe form is `lazy-state.py [--cloud] --repeat-count --probe --emit-prompt [--forward-cycles N] [--meta-cycles N] [--max-cycles K]` (bug-state.py identical). `--repeat-count-peek` is the read-only variant — registry/counter writes must follow the same advance-vs-peek discipline.
- Template machinery: `_components/lazy-batch-prompts/cycle-base-prompt.md`, `<!-- @section name pipelines=... modes=... skills=... -->` markers, `{lower_snake}` tokens, residue guard refuses unbound tokens (`cycle_prompt_refused`). `--emit-dispatch` (Phase 3) MUST reuse `_parse_cycle_template`/`_parse_section_attrs`/binding/residue machinery, not reimplement it.
- Streak persistence pattern to mirror: `update_repeat_counts` peek discipline + `_atomic_write` temp-file `os.replace`.
- Both state scripts `import lazy_core` (same dir; bug-state.py prepends `sys.path`). Test conventions: `test_lazy_core.py` is a CUSTOM harness (not pytest), 186 `test_*` functions calling `_guard()`, run `python3 user/scripts/test_lazy_core.py`; add tests there. Smoke baselines: never regenerate by hand.
- The 1c.6 PushNotification policy in `/lazy-batch` enumerates every terminal/halt point — that enumeration IS the marker-deletion checklist for Phase 5 (terminals: all-features-complete, cloud/device-queue-exhausted, queue-missing, max-cycles, meta-cap, operator-chosen halt, script-error).

---

## Phases

### Phase 1: Run-state core — marker, prompt registry, persisted run counters (lazy_core.py + both state scripts)

**Scope:** Pure-Python foundations, marker-gated so default behavior is byte-identical (A10). Establishes the `~/.claude/state/` directory, the run-marker API, the prompt-registry API, and wires both state scripts to emit registry entries when (and only when) a marker is present. Also moves `forward_cycles`/`meta_cycles` into script-persisted run state (resolving the compaction counter-loss class — A8). All new behavior is unreachable without an explicit `--run-start` call, ensuring zero observable change to existing flows.

**Deliverables:**
- [x] `lazy_core.py`: `claude_state_dir()` — resolves `~/.claude/state/` (created on demand), overridable via env var (e.g. `LAZY_STATE_DIR`) for hermetic tests.
- [x] Run-marker API: `write_run_marker(pipeline, cloud, repo_root, session_id=None, max_cycles, nonce_seed)`, `read_run_marker()` (returns None AND deletes when stale: `started_at` > 24h; session-id binding is bind-on-first-hook-firing — marker may carry `session_id: null` until the inject hook stamps it, per the spec's stale-marker guard), `delete_run_marker()`. All writes via `_atomic_write`.
- [x] Prompt-registry API: `register_emission(prompt, cls, item_id)` → appends `{nonce, prompt_sha256, emitted_at, class, item_id, consumed: false}` to `lazy-prompt-registry.json` (ring, cap ~64 entries); `lookup_emission(prompt_hash)`; `consume_nonce(nonce)`. Hashing: sha256 AFTER newline normalization (CRLF→LF) — the spec's explicit requirement so Windows/WSL round-trips can't defeat the match. Nonce: derived from `nonce_seed` + counter or uuid4 — single-use is the primary control; freshness window is secondary. **Deviation from SPEC §Validate-deny step 2 (recorded):** the spec's "emitted_at within the current turn window" is not mechanically computable from a hook (hooks have no reliable turn counter), so the chosen approximation is single-use nonce + a short TTL on registry entries (default 30 minutes, constant in lazy_core.py) + `emitted_at` newer than marker `started_at`. An unconsumed-but-stale emission is therefore NOT dispatchable, preserving the spec's intent (a re-dispatch requires a re-probe).
- [x] `--emit-prompt` integration in BOTH scripts: when (and only when) the marker is present, every successful emission is registered with class `cycle`. No marker → zero writes, byte-identical output.
- [x] Script-persisted run counters: `forward_cycles`/`meta_cycles` move into the marker file; new CLI `--run-start` (writes marker; takes `--cloud`, `--max-cycles`) and `--run-end` (deletes marker) on both scripts; the probe folds counters FROM the marker when marker present and the legacy flags are absent (explicit flags still win — backward compat); counters advance at dispatch-bound probe time (`--repeat-count`, not `--repeat-count-peek`), classified forward vs meta by the probe's own routing (real sub_skill cycle → forward; resolution/pseudo routing → meta). Document the chosen advance policy in code comments.
- [x] Tests (TDD, in test_lazy_core.py following its harness conventions): marker lifecycle incl. staleness (BOTH conditions: `started_at` > 24h AND bound-session-id mismatch each trigger delete-and-return-None); registry register/lookup/consume/ring-cap; registry-entry TTL expiry (stale unconsumed entry not dispatchable); newline-normalization hash equality (CRLF vs LF prompt → same hash); marker-gated no-op (no marker → no registry file); counter fold + advance + peek discipline; `--test` baselines byte-identical.

**Minimum Verifiable Behavior:** With a marker written into a temp state dir (via `LAZY_STATE_DIR` env override), a real subprocess invocation of `lazy-state.py --repeat-count --probe --emit-prompt` against a fixture repo writes a registry entry whose `prompt_sha256` equals sha256(normalized `cycle_prompt` from the probe's own stdout JSON) — the real production entry point, ground-truth literal hash comparison, crossing the script↔state-dir boundary.

**Runtime Verification** *(checked by live harness or manual testing — NOT by the implementation agent):*
- [ ] Registry entry appears in state dir from a real CLI invocation of `--repeat-count --probe --emit-prompt` with marker present.
- [ ] Default (no-marker) invocation output is byte-identical to committed baseline.
- [ ] `--run-start` / `--run-end` round-trip leaves no marker file in the state dir.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core.py` (new functions: `claude_state_dir`, marker API, registry API; counter persistence)
- `user/scripts/lazy-state.py` (registry integration on `--emit-prompt`; `--run-start`/`--run-end` CLI)
- `user/scripts/bug-state.py` (same as lazy-state.py — coupled-pair mirror)
- `user/scripts/test_lazy_core.py` (new test_* functions per harness conventions)
- `tests/baselines/` (no regeneration — baselines must remain byte-identical)

**Testing Strategy:**
- Entry point: real `python3 lazy-state.py` subprocess (same as production); `python3 test_lazy_core.py` for unit coverage.
- Ground-truth assertion: literal sha256 equality between registry `prompt_sha256` field and sha256(normalized `cycle_prompt` from probe stdout).
- Boundary coverage: script→state-dir I/O boundary; CRLF/LF normalization boundary; ring-cap eviction (write 65 entries, confirm oldest evicted); staleness via BOTH paths (mock `started_at` = 25h ago; bound session_id ≠ probing session_id).
- Runtime gate: Phase 6 live E2E consumes this registry; Phase 2 hooks depend on the env-var state-dir override for hermetic pipe-tests.

**Integration Notes for Next Phase:** Registry and marker file shapes established here are the contract for Phase 2 hooks and Phase 3 `--emit-dispatch`. The `LAZY_STATE_DIR` env-var override is how Phase 2 pipe-tests achieve hermetic isolation — it must be documented in `lazy_core.py` docstring.

#### Implementation Notes (Phase 1 — 2026-06-11)

**Review verdict:** PASS-WITH-FIXES — all five review items applied by a fix subagent and re-verified (freshness leg `emitted_at >= marker.started_at` added to `lookup_emission` + `--run-end` now clears the registry via `delete_run_marker(clear_registry=True)`; `claude_state_dir(create=False)` on all read paths so no-marker probes never mkdir; deprecated `utcfromtimestamp` replaced; CLI-surface docs updated in scripts/CLAUDE.md + module docstrings; corrupt-marker and peek-no-advance tests added). Final state: 264/264 `test_lazy_core.py`, both `--test` smoke suites green, baselines byte-identical. Ground-truth note: the fix subagent's pasted `wc -l` figures did not match fresh re-runs (counting-method artifact), but every grep line number and test tail matched byte-for-byte — deliverables verified real. Carried to Phase 2: registry read-modify-write has no cross-process lock (hook consume vs script register concurrency); combined `--repeat-count --probe` renders the POST-advance counter in `cycle_header` (1-based current-cycle semantics — Phase 5 SKILL prose must pin this).

---

### Phase 2: Hook-mechanics spike (go/no-go) + inject & validate hooks (built, pipe-tested, NOT yet armed)

**Scope:** Resolve A6 and A11 with a live spike FIRST, then build both hooks fail-open. The hooks are NOT registered in any live settings.json until Phase 6 — building and arming are deliberately separated so a half-built guard can never brick a run. A6 is an explicit go/no-go: if no reliable orchestrator-vs-nested discriminator exists, this phase halts with NEEDS_INPUT.md and all downstream phases that depend on deny semantics block.

**Deliverables:**
- [x] Spike harness (scripted, re-runnable): temp settings file with logging-only hooks + `claude -p` runs that (a) capture PreToolUse hook input for an `Agent` dispatch (records actual `tool_name`), (b) dispatch a subagent that itself dispatches a nested agent and records whether/how the hook fires for the nested call and which input field discriminates depth (`session_id`, `transcript_path`, other), (c) confirm UserPromptSubmit `additionalContext` reaches the model, (d) compare `SessionStart` matcher `compact` vs `PostCompact` for post-compaction injection, (e) record whether UserPromptSubmit fires on autonomous task-notification turns (background-agent completions) — the SPEC's "Known limitation (recorded, not hidden)" — and document the observed coverage gap in RUNTIME_SPIKE.md regardless of outcome (the probe-presence guard + validate-deny still police those turns). Findings recorded in `docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md` with raw captured hook-input JSON.
- [x] **Go/no-go gate:** if NO reliable orchestrator-vs-nested discriminator exists, write `NEEDS_INPUT.md` (sentinel schema, rich body: the design fork — e.g. scope guard to depth-0 via SubagentStart bookkeeping vs registry-exempt nested classes vs abandon deny for advisory) and STOP this phase; later phases that depend on the deny semantics block on the answer.
- [x] `user/hooks/lazy-route-inject.sh` — registered (later, in Phase 6) on UserPromptSubmit + SessionStart(matcher `compact`) (+ PostCompact if the spike proves it injects): marker-absent fast path (one `test -f`, exit 0); marker present → run the full probe form with counters from the marker, inject probe JSON + `cycle_header` + `cycle_prompt`/`cycle_model` + nonce via `additionalContext`, prefixed `LAZY-ROUTE (hook-injected, turn N):`; the SessionStart(compact) firing additionally injects the post-compaction re-entry protocol (the Step 1d HARD rule) plus the marker-sourced `forward_cycles`/`meta_cycles` counters (the SPEC's inject item 3 — the compaction counter-loss class dies by construction); stale-marker cleanup to stderr only; if a `HOOK_ERROR` breadcrumb exists in the state dir, surface it in the injected context (self-announcing guard breakage); inject-hook internal error → write `HOOK_ERROR` breadcrumb to state dir (trigger-3 evidence) and exit 0.
- [x] `user/hooks/lazy-dispatch-guard.sh` — PreToolUse matcher `Agent|Task` (final matcher per spike): marker-absent fast path; marker present → delegate to `user/scripts/lazy_guard.py` (thin CLI importing lazy_core) that normalizes+hashes `tool_input.prompt`, looks up registry, consumes nonce, and prints the allow/deny `hookSpecificOutput` JSON with the spec's exact corrective recipe as `permissionDecisionReason`; hardening-class depth guard implemented HERE against synthetic `class: hardening` registry entries: a deny OF a hardening-class entry does NOT recommend another hardening dispatch — reason instructs T6 ⚠ halt + PushNotification (depth hard-cap 1); Phase 4 adds only the integration test against a real emitted hardening entry; ANY internal error → fail-OPEN (exit 0 allow) + `HOOK_ERROR` breadcrumb that the next inject turn surfaces.
- [x] Pipe-tests: synthetic hook-input JSON piped via stdin to both hook scripts on BOTH Windows (git-bash) and WSL — new test entry (e.g. `test_hooks.py` or test_lazy_core.py additions invoking bash subprocesses) asserting: fast path silent exit 0 without marker; deny JSON for unregistered prompt; allow + nonce consumption for registered prompt; second dispatch of same prompt denied (nonce consumed); fail-open on corrupted registry; `HOOK_ERROR` breadcrumb present in state dir → inject-hook output includes the breadcrumb surface.

**Minimum Verifiable Behavior:** All pipe-tests green on both Windows (git-bash) and WSL. The deny JSON output for an unregistered prompt validates against the spec's A3 schema (`hookSpecificOutput.permissionDecision: "deny"`, `permissionDecisionReason` non-empty containing the corrective recipe). The `RUNTIME_SPIKE.md` artifact exists with raw hook-input JSON capturing actual `tool_name` values.

**Runtime Verification** *(checked by live harness or manual testing — NOT by the implementation agent):*
- [ ] `RUNTIME_SPIKE.md` exists in `docs/specs/turn-routing-enforcement/` with raw captured hook-input JSON for both orchestrator and nested-agent PreToolUse events.
- [ ] Pipe-test suite exits 0 on both Windows (git-bash) and WSL platforms.
- [ ] Deny JSON for an unregistered prompt validates: `permissionDecision == "deny"`, `permissionDecisionReason` contains re-probe instruction.
- [ ] A6 resolution is recorded in `RUNTIME_SPIKE.md`: either discriminator field identified (go) or NEEDS_INPUT.md written (no-go).

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** Phase 1 (registry/marker APIs + `LAZY_STATE_DIR` env override).

**Files likely modified:**
- `user/hooks/lazy-route-inject.sh` (new)
- `user/hooks/lazy-dispatch-guard.sh` (new)
- `user/scripts/lazy_guard.py` (new thin CLI)
- `user/scripts/test_lazy_core.py` (new pipe-test entries) OR new `user/scripts/test_hooks.py`
- `docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md` (new spike artifact)
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` (conditional — written and phase halts if A6 unresolvable)

**Testing Strategy:**
- Entry point: bash pipe-test (synthetic JSON stdin → hook script stdout) for both hook scripts; `claude -p` scripted harness for spike assertions (A11).
- Ground-truth assertion: deny JSON schema equality against A3 spec; nonce consumption confirmed by second-dispatch test; fast-path confirmed by absence of stdout/state-dir writes.
- Boundary coverage: corrupted registry (fail-open); stale marker (fast-path); registered-then-consumed (second dispatch denied); hardening-class depth-1 deny (halt reason, no recursion).
- Runtime gate: Phase 6 live E2E uses the actual registered hooks; Phase 5 SKILL integration depends on the discriminator decision from A6.

**Integration Notes for Next Phase:** The discriminator decision and final matcher string from the spike feed Phase 6 registration. `lazy_guard.py` consume semantics — specifically which registry entry fields are checked and consumed — are the contract that Phase 3's `--emit-dispatch` registrations must satisfy (class tags, nonce format).

#### Implementation Notes (Phase 2 — 2026-06-11)

**Review verdict:** PASS-WITH-FIXES — all seven review items applied by a fix subagent and re-verified fresh (20/20 test_hooks.py, 264/264 test_lazy_core.py, both smoke suites, baselines untouched). Spike verdict **A6 = GO** (RUNTIME_SPIKE.md): structural isolation — the orchestrating session's PreToolUse only sees its own Agent calls; in `-p` mode subagents had no Agent tool at all, so the nested case never fired live — **carried risk: Phase 6 E2E must confirm this holds in a real cycle-subagent run.** Spike also found PreToolUse **double-fires on deny** for the same `tool_use_id` (E4) → guard is idempotent per consumer (`consumed_by`; allow-refire-same-consumer is a deliberate defensive extension beyond the spike's "consumed = deny" note). Design rulings: hardening depth-cap applies to ANY deny of a `class: hardening` entry (incl. stale unconsumed — spec letter); `tool_input` with NO `prompt` key → silent allow (nothing to launder). Incidents: (1) the impl subagent worked around a bash-resolution failure by copying git-bash's bash.exe into the Python install dir — reverted; proper fix is `_find_bash()` in test_hooks.py (never System32). (2) Hook scripts initially used `dirname`/`$(dirname $0)` — fails when git-bash runs without /usr/bin on PATH and when `$0` carries backslashes; fixed to builtin-only resolution with separator normalization. Session-id bind-on-first-hook-firing implemented (`lazy_core.bind_marker_session`); both hooks pass hook-input session_id to `read_run_marker` so staleness path B is live. `.gitattributes` added (`*.sh text eol=lf`) — repo has core.autocrlf=true and WSL executes the Windows working tree. **Gate addition: `python user/scripts/test_hooks.py` joins the standing gate set for all later phases.** Carried to Phase 6: registration timeout must exceed the inject probe's 60s subprocess timeout; registry has no cross-process lock (single-writer-per-turn assumption documented).

---

### Phase 3: `--emit-dispatch <class>` — every remaining dispatch class becomes script-emitted

**Scope:** Close the ad-hoc dispatch gap (spec: "Every legitimate dispatch class becomes script-emitted"). Classes: `apply-resolution`, `input-audit`, `investigation`, `recovery`, `coherence-recovery`, `needs-runtime-redispatch`. The `hardening` class is deferred to Phase 4 (it requires the `/harden-harness` skill contract to exist before its template can be authored). This phase MUST NOT reimplement the template/binding/residue machinery — it extends exactly `_parse_cycle_template`/`_parse_section_attrs`/token-binding/residue from lazy_core.py.

**Deliverables:**
- [x] New emit-able templates under `_components/lazy-batch-prompts/dispatch-<class>.md` for each class, using the SAME `<!-- @section name pipelines=... modes=... skills=... -->` / `{lower_snake}` token grammar — derived from existing prose components (`decision-resume.md`, `blocked-resolution.md`, `halt-resolution.md`, `investigation-dispatch.md`, etc.) WITHOUT changing those components' orchestrator-facing contracts (Phase 5 rewires the SKILLs).
- [x] `lazy_core.emit_dispatch_prompt(cls, state_ctx, pipeline, cloud)` reusing `_parse_cycle_template`/`_parse_section_attrs`/token-binding/residue machinery; refusal surfaces as `dispatch_prompt_refused` in the returned dict.
- [x] CLI `--emit-dispatch <class>` on both state scripts with a repeatable generic `--context key=value` for class-specific token bindings; output JSON `{dispatch_prompt, dispatch_model, dispatch_class, ...}`; registers in the registry (with the class tag) when marker present; peek behavior when marker absent (no registry write, output still produced — forward-only usability).
- [x] Tests in test_lazy_core.py: token binding matrix across all six classes × both pipeline modes (feature/bug); residue-guard refusal for unbound token; registry class tags present and match `cls` arg; peek/no-marker produces output without writing registry; `--test` baselines byte-identical.

**Minimum Verifiable Behavior:** Real CLI invocation `python3 lazy-state.py --emit-dispatch recovery --context feature_id=tf-B --context item_title="test"` emits a fully-bound dispatch prompt (no unbound `{token}` residue) and, with marker present, writes a registry entry with `class == "recovery"` — assertable by reading the registry JSON directly.

**Runtime Verification** *(checked by live harness or manual testing — NOT by the implementation agent):*
- [ ] `--emit-dispatch recovery` with marker present: registry entry with `class == "recovery"` appears.
- [ ] `--emit-dispatch` for each of the six classes: output JSON has no unbound `{token}` residue.
- [ ] `--test` baseline output byte-identical to committed baseline for both state scripts.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** Phase 1 (registry; `_atomic_write`; `LAZY_STATE_DIR`). Phase 2 informs nothing here directly (parallel-safe in principle) but sequencing stays linear for review sanity.

**Files likely modified:**
- `user/scripts/lazy_core.py` (`emit_dispatch_prompt` function; extends `--emit-dispatch` CLI surface)
- `user/scripts/lazy-state.py` (`--emit-dispatch` CLI plumbing)
- `user/scripts/bug-state.py` (same — coupled-pair mirror)
- `user/scripts/test_lazy_core.py` (binding matrix tests)
- `_components/lazy-batch-prompts/dispatch-apply-resolution.md` (new)
- `_components/lazy-batch-prompts/dispatch-input-audit.md` (new)
- `_components/lazy-batch-prompts/dispatch-investigation.md` (new)
- `_components/lazy-batch-prompts/dispatch-recovery.md` (new)
- `_components/lazy-batch-prompts/dispatch-coherence-recovery.md` (new)
- `_components/lazy-batch-prompts/dispatch-needs-runtime-redispatch.md` (new)

**Testing Strategy:**
- Entry point: `python3 test_lazy_core.py` for binding matrix; real subprocess `python3 lazy-state.py --emit-dispatch <cls>` for MVB/registry-write.
- Ground-truth assertion: no `{lower_snake}` residue tokens in `dispatch_prompt`; registry `class` field matches CLI arg; `dispatch_prompt_refused` emitted when required token absent.
- Boundary coverage: all six classes × feature and bug pipelines; unbound-token refusal; no-marker peek (output produced, no registry write); ring-cap (Phase 1 already tested — just confirm class-tagged entries are evicted correctly).
- Runtime gate: Phase 5 SKILLs consume the `--emit-dispatch` output verbatim; Phase 4 hardening class extends this machinery.

**Integration Notes for Next Phase:** Token names chosen per class are load-bearing for Phase 5 SKILL prose — the binding names must be finalized before Phase 5 rewires the orchestrators. The `hardening` class template is authored in Phase 4, extending this machinery identically.

#### Implementation Notes (Phase 3 — 2026-06-11)

**Review verdict:** PASS-WITH-FIXES — machinery/CLI sound at first review; the gap was template fidelity to source components. Fixes applied and re-verified (273/273 + 20/20 + smokes + lint): input-audit template restored the aggressive-bias checklist, 4-decision cap + FOLLOWUP overflow, D7-violation flagging, `audit_concurs` two-key step (`written_by: lazy-batch-input-audit`); apply-resolution now covers BOTH Step 1g (needs-input) and Step 1h (blocked) via `resolution_kind`/`chosen_path` tokens with prose branching — Defer leaves BLOCKED.md in place, FOLLOWUP promotion scoped to NEEDS_INPUT; coherence-recovery no longer contradicts the --apply-pseudo third gate (verification rows INCLUDED in refusals); investigation carries `trigger`/`inherited_hypotheses` tokens; recovery includes the plan-scoped `--verify-ledger --plan` variant. **Design rulings:** `DISPATCH_MODELS["apply-resolution"] = "opus"` (source: blocked-resolution.md's Opus apply subagent — the spec pins no per-class models; the test constant was corrected accordingly, the one sanctioned test edit); `item_id`/`cwd` declared in every template's `@requires` (uniform convention; no auto-require machinery). Final `@requires` per class are recorded in the templates' line-1 markers — **these token names are the Phase 5 contract.** Shared helpers factored: `_standard_dispatch_bindings`, `_dedup_residue`; `_PROMPT_RESIDUE_RE` widened to `[a-z0-9_]`. Carried to Phase 5: investigation-dispatch.md prose still claims the state scripts have no dispatch emission (now stale — rewire in Phase 5); needs-runtime-redispatch model is opus.

---

### Phase 4: `/harden-harness` skill + hardening dispatch class + self-recursion guard

**Scope:** The harness-hardening stage as a first-class skill, per the spec's full contract (identity, four triggers, four-step job, tiered authority, HARDENING.md log discipline, commit prefix, prohibitions, NEEDS_INPUT escalation). The `hardening` class in `--emit-dispatch` extends Phase 3 machinery. The self-recursion guard (depth hard-cap 1) is wired into `lazy_guard.py` from Phase 2.

**Deliverables:**
- [x] `user/skills/harden-harness/SKILL.md`: identity (to the HARNESS what /investigate is to the target repo); four triggers (validate-deny, no-route, inject-hook-error, manual); cadence clause verbatim from locked decision 4 — **inline, unbounded per-run dispatch count, NO dedup-by-signature cap** (unbounded refers to per-run count; recursion depth stays hard-capped at 1); four-step job (reconstruct route → root-cause against the harness → act by decision class with tiered authority [mechanical = autonomous under FULL gates: lint-skills.py + `--check-projected --check-capabilities`, test_lazy_core.py full suite no baseline regen, lazy-state.py --test, bug-state.py --test, coupled-pair mirroring, sentinel-schema lockstep] → HARDENING.md round appended to `docs/specs/turn-routing-enforcement/hardening-log/YYYY-MM.md`); commit prefix `harden(<area>):`; prohibitions verbatim from spec (never edits target repo source; never weakens a gate; never edits registry/marker to launder a denial); NEEDS_INPUT escalation for contract/policy forks per sentinel-frontmatter.md rich-body convention.
- [x] `user/skills/_components/hardening-dispatch.md` — emit-able template using the Phase 3 `@section`/`{lower_snake}` grammar; binds the denied prompt, denial reason, probe JSON, and registry state into an Opus dispatch prompt.
- [x] `hardening` class added to `lazy_core.emit_dispatch_prompt` (extends Phase 3 machinery; registers with `class: hardening` tag that Phase 2's depth guard reads).
- [x] `lint-skills.py` green with full flags (`--check-projected --check-capabilities`); skill registered in any skill-catalog surface that lint requires.
- [x] Self-recursion guard: the depth-1 logic itself already exists in `lazy_guard.py` (built and pipe-tested in Phase 2 against synthetic class-tagged entries) — this phase adds ONLY the integration pipe-test against a REAL `--emit-dispatch hardening` registry entry: hardening-class deny → reason contains halt instruction, not recursive hardening.
- [x] Tests: binding coverage for hardening class (same matrix discipline as Phase 3); registry class tag `== "hardening"`; depth-1 pipe-test (guard sees hardening-class entry + deny → halt reason, no recursion).

**Minimum Verifiable Behavior:** `python3 lazy-state.py --emit-dispatch hardening --context denied_prompt="..." --context denial_reason="..."` emits a bound dispatch prompt that, looked up in the registry via `lazy_guard.py`, is ALLOWED (registry hit + unconsumed nonce) — assertable via `lazy_guard.py` CLI without a live session.

**Runtime Verification** *(checked by live harness or manual testing — NOT by the implementation agent):*
- [ ] `--emit-dispatch hardening` with marker present: registry entry with `class == "hardening"` appears.
- [ ] `lazy_guard.py` lookup of that entry: outputs allow JSON.
- [ ] Pipe-test: hardening-class deny outputs halt instruction reason (not another hardening recommendation).
- [ ] `lint-skills.py --check-projected --check-capabilities` exits 0.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** Phases 1–3 (registry, emit_dispatch_prompt machinery, `lazy_guard.py` from Phase 2).

**Files likely modified:**
- `user/skills/harden-harness/SKILL.md` (new)
- `user/skills/_components/hardening-dispatch.md` (new)
- `user/scripts/lazy_core.py` (hardening class in `emit_dispatch_prompt`)
- `user/scripts/lazy_guard.py` (depth-1 guard logic)
- `user/scripts/test_lazy_core.py` (hardening class binding tests; depth-1 pipe-test)
- any skill-catalog index that lint-skills.py validates

**Testing Strategy:**
- Entry point: `python3 test_lazy_core.py` for binding/registry tests; bash pipe-test for depth-1 guard.
- Ground-truth assertion: `class == "hardening"` in registry; allow JSON from `lazy_guard.py` for unconsumed nonce; depth-1 deny reason contains "halt" / "PushNotification" and does NOT contain "harden-harness" as a recommended action.
- Boundary coverage: hardening class with missing required token (residue refusal); depth-1 path (deny of hardening entry); depth-0 hardening dispatch (allowed, nonce consumed).
- Runtime gate: Phase 5 skill prose wires the hardening triggers; Phase 6 live E2E demonstrates an inline hardening dispatch in a real run.

**Integration Notes for Next Phase:** The `SKILL.md` triggers (1–4) and step numbering become the authoritative prose that Phase 5 batch orchestrators reference when wiring triggers 1–3. The HARDENING.md log format (month-file, appended rounds) should be documented in the skill and matches what Phase 6 validation records.

#### Implementation Notes (Phase 4 — 2026-06-11)

**Review verdict:** PASS-WITH-FIXES — spec-contract fidelity confirmed at full force (all four triggers, gap taxonomy, tiered authority, three prohibitions, depth-1 + unbounded cadence; the reviewer verified depth-cap prose matches `lazy_guard.py` behavior exactly on both consumed-by-other and stale-unconsumed paths). Five small fixes applied inline by the orchestrator: CLI help in both state scripts now enumerates the 7th class; "(full suite, NO baseline regeneration)" restored on the test_lazy_core gate line in SKILL + template; triggers intro no longer claims trigger 4 arrives via dispatch; dispatch-hardening.md gained an explicit subagent policy (no Agent tool — registry-validated runs; Skill tool allowed) and a local-commit/no-push rule (mirrored as a no-push clause in the SKILL). Note: the impl agent made two sanctioned surgical edits to Phase 3 tests that deliberately pinned the pre-Phase-4 state (exact-set → first-6 subset; "hardening" removed from the bad-class list) — exactness is re-pinned by `test_hardening_dispatch_class_present`; no other assertion weakened (reviewer verified hunk-by-hunk). The `/harden-harness` skill projects cleanly and already appears in live skill lists. Gates: 277/277, 21/21, both smokes, full lint.

---

### Phase 5: Orchestrator SKILL integration (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud, mirrored)

**Scope:** The three batch orchestrators consume the new marker/registry/inject/dispatch machinery. Coupled-pair mirroring (`lazy-batch` ↔ `lazy-bug-batch`) is a hard gate — both skills must be updated in the same pass. `lazy-batch-cloud` is the third member of the triplet. This phase converts the SKILLs from prose-contract to hook-contract consumers.

**Deliverables:**
- [ ] Step 0 wired: `--run-start` marker write after preflight passes; EVERY terminal path per the 1c.6 PushNotification enumeration gets `--run-end` (marker deletion). Terminal checklist: all-features-complete, cloud/device-queue-exhausted, queue-missing, max-cycles, meta-cap, operator-chosen halt, script-error exits — all must call `--run-end` before their terminal action.
- [ ] Cycle dispatch prose updated: consume the hook-injected `LAZY-ROUTE (hook-injected, turn N):` banner when present (the probe JSON + `cycle_prompt`/`cycle_model` arrive with the turn via inject hook); on guard denial, canonical recovery wired (re-probe → dispatch emitted prompt verbatim; no-route → `--emit-dispatch hardening`); hardening triggers 1–3 wired in SKILL prose.
- [ ] All resolution/audit/investigation/recovery/coherence-recovery/needs-runtime dispatches switched from orchestrator-bound component prose to consuming `--emit-dispatch <class>` output verbatim (the dispatch prompt is the registered prompt — no hand-composition).
- [ ] Counters: SKILLs stop hand-passing `--forward-cycles`/`--meta-cycles` flags in probe invocations (flags remain in CLI for compat); post-compaction re-entry prose updated to note counters arrive via marker/inject hook (the compaction cliff is closed by construction).
- [ ] State Machine Summary and "Differences from /lazy-batch" blocks updated in all three skills; coupled-pair diff performed and recorded in the Implementation Notes comment at bottom of each SKILL.md.
- [ ] Gates green: `lint-skills.py` (full flags), both state-script `--test` suites, `test_lazy_core.py`, `test_hooks.py`.

**Minimum Verifiable Behavior:** Dry probe sequence on a fixture repo: `--run-start` → `--repeat-count --probe --emit-prompt` (shows marker-sourced counters, no `--forward-cycles` flag required) → `--run-end` produces zero marker file. Output matches SKILL prose for Step 0 / Step 1a. `lint-skills.py` exits 0.

**Runtime Verification** *(checked by live harness or manual testing — NOT by the implementation agent):*
- [ ] Marker absent after each terminal path walked in a scripted dry-run (one path per terminal enumerated in 1c.6 PushNotification list).
- [ ] Probe with marker present, no `--forward-cycles` flag: `forward_cycles` in output matches value from marker (not 0).
- [ ] Coupled-pair diff recorded in Implementation Notes of both `lazy-batch/SKILL.md` and `lazy-bug-batch/SKILL.md`.
- [ ] `lint-skills.py --check-projected --check-capabilities` exits 0.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** Phases 1–4 (and Phase 2's NEEDS_INPUT resolved if it fired — deny semantics must be confirmed go before wiring guard-denial recovery prose into the SKILLs).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md`
- `user/skills/lazy-bug-batch/SKILL.md`
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`

**Testing Strategy:**
- Entry point: `python3 lazy-state.py --run-start ... && python3 lazy-state.py --repeat-count --probe --emit-prompt && python3 lazy-state.py --run-end` scripted sequence against fixture repo.
- Ground-truth assertion: counter in probe output sourced from marker; marker absent after `--run-end`; `lint-skills.py` exit 0.
- Boundary coverage: each terminal path in 1c.6 enumeration (scripted dry-run confirms `--run-end` is called); post-compaction re-entry prose verified by reading SKILL prose against implementation notes.
- Runtime gate: Phase 6 live E2E runs a real (or 1-cycle scripted) marked run through these updated SKILLs.

**Integration Notes for Next Phase:** The SKILLs as updated here are what Phase 6's live `claude -p` harness executes. The `LAZY-ROUTE` banner wired in Step 1a becomes observable evidence in the Phase 6 E2E_VALIDATION.md mapping (Success Criterion 1). Coupled-pair diff recorded here is evidence for the MCP test gate audit in future lazy-batch-retro sessions.

---

### Phase 6: Registration, setup.ps1 check, live end-to-end validation

**Scope:** Arm the system on this machine (laptop, A9); prove all four success criteria live. This phase is the validation pass — it does NOT implement; it integrates, registers, and records evidence. All prior phases must be complete (and A6 resolved go) before this phase begins.

**Deliverables:**
- [ ] Repair `~/.claude/hooks` symlink on this laptop per setup.ps1 manifest.psd1 definition (A9 finding); `setup.ps1` updated to check for this symlink's presence as part of its verification pass.
- [ ] Per-machine registration snippet documented in `docs/specs/turn-routing-enforcement/REGISTRATION.md`: UserPromptSubmit (≥30s timeout per spec), SessionStart matcher `compact`, PreToolUse matcher `Agent|Task` — exact JSON fragment ready to paste into `~/.claude/settings.json`. Applied to THIS laptop's live `~/.claude/settings.json`.
- [ ] `setup.ps1 check` extension: parse live `~/.claude/settings.json`, warn (not fail) when the two hook script filenames (`lazy-route-inject.sh`, `lazy-dispatch-guard.sh`) are absent from the registered hooks list.
- [ ] Cross-platform pipe-test run records: both Windows (git-bash) and WSL platforms — results appended to `E2E_VALIDATION.md` (or referenced artifact).
- [ ] Live E2E via scripted `claude -p` marked-run harness (or a 1-cycle real `/lazy-batch` run in AlgoBooth): five assertions recorded in `docs/specs/turn-routing-enforcement/E2E_VALIDATION.md` mapping each spec Success Criterion 1–4 to observed evidence:
  1. LAZY-ROUTE banner injected (Success Criterion 1: probe-shaped turns have injected route).
  2. A deliberately hand-composed Agent dispatch is DENIED with the corrective reason (Success Criterion 1: zero hand-composed real-skill dispatches reach execution).
  3. The registered emitted prompt is ALLOWED and its nonce consumed (mechanism working correctly).
  4. Marker deleted at run end (Success Criterion 1 + 3: marker lifecycle).
  5. Interactive session with no marker shows no injected banner and no denials (Success Criterion 3: no behavioral change in non-marked sessions).
  6. The deliberate denial from assertion 2 is followed through the canonical recovery: `--emit-dispatch hardening` emits + registers a hardening dispatch, the dispatch is ALLOWED by the guard, and a HARDENING.md round (or a triaged NEEDS_INPUT.md) lands in `hardening-log/` — none vanish (Success Criterion 2; this is the inline hardening dispatch Phase 4's runtime gate promised).
  7. Retro-mechanics check on the harness transcript: printed cycle heading ↔ injected `cycle_header` byte-match, and each executed dispatch ↔ a registry lookup hit (Success Criterion 4: R-O-1/R-O-4 grading becomes mechanical).

**Completion (gate-owned):** SPEC Status flip to Complete happens via the pipeline gate, not a checkbox here.

**Minimum Verifiable Behavior:** The live `claude -p` harness run produces `E2E_VALIDATION.md` containing at least one captured deny JSON (hand-composed dispatch) and one captured allow JSON (registered emitted prompt) from the ACTUALLY REGISTERED hooks on this laptop — raw captures, not "expected behavior" placeholders.

**Runtime Verification** *(checked by live harness or manual testing — NOT by the implementation agent):*
- [ ] `~/.claude/hooks` symlink resolves on this laptop.
- [ ] Both hook filenames appear in live `~/.claude/settings.json` hooks registrations.
- [ ] LAZY-ROUTE banner observed in `claude -p` harness session log.
- [ ] Hand-composed Agent dispatch: deny JSON observed with corrective reason.
- [ ] Registered emitted-prompt dispatch: allow JSON observed; registry entry `consumed: true` after.
- [ ] Marker absent from `~/.claude/state/` at run end.
- [ ] Interactive `claude` session (no marker): no hook output injected, no denials.
- [ ] Deliberate-deny follow-through observed: hardening dispatch emitted + allowed, HARDENING.md round (or triaged NEEDS_INPUT.md) present in `hardening-log/` (SC2).
- [ ] Harness transcript: cycle heading byte-matches injected `cycle_header`; every executed dispatch resolves to a registry lookup hit (SC4).

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** ALL prior phases complete; A6 resolved go (discriminator field confirmed in Phase 2 spike).

**Files likely modified:**
- `setup.ps1` (symlink check + hook-registration warn extension)
- `docs/specs/turn-routing-enforcement/REGISTRATION.md` (new)
- `docs/specs/turn-routing-enforcement/E2E_VALIDATION.md` (new)
- live `~/.claude/settings.json` (per-machine, untracked — modified directly on this laptop)

**Testing Strategy:**
- Entry point: scripted `claude -p` harness (or 1-cycle `/lazy-batch` run); manual `setup.ps1` verification pass.
- Ground-truth assertion: E2E_VALIDATION.md contains a row per Success Criterion (1–4) with observed evidence (log excerpt or JSON capture) rather than "expected behavior" placeholders.
- Boundary coverage: interactive session (no marker) + marked run (with marker) both verified; both platforms (Windows git-bash, WSL) pipe-test records present.
- Runtime gate: this IS the runtime gate — E2E_VALIDATION.md is the deliverable evidence for the feature Complete flip.

**Integration Notes for Next Phase:** This is the final phase. Evidence in `E2E_VALIDATION.md` feeds the `/lazy-batch-retro` grading for R-O-1/R-O-4 (heading ↔ `cycle_header` byte-match, dispatch ↔ registry lookup — Success Criterion 4). The `hardening-log/` directory initialized here receives future `/harden-harness` round entries as the self-improvement loop runs.

---

## Review Notes

**2026-06-11 — /spec-phases authoring review.** Ground-truth verified: yes (git status, line count 326, phase-heading grep all matched the drafting subagent's pasted block). **Review verdict: PASS-WITH-FIXES** — full SPEC coverage confirmed (all components land in exactly one phase; all four Locked Decisions intact; deny hook genuinely unarmed until Phase 6; failure-mode containments reflected). Nine localized fixes applied by the orchestrator post-review: (1) Phase 6 MVB section added; (2) E2E assertions 6–7 added covering Success Criteria 2 and 4; (3) turn-window freshness recorded as an explicit SPEC deviation with a compensating 30-min registry-entry TTL; (4) session-id-mismatch staleness test rows added to Phase 1; (5) spike item (e) added for the UserPromptSubmit task-notification limitation; (6) SessionStart(compact) payload enumerated (re-entry protocol + counters); (7) depth-guard ownership clarified (Phase 2 implements vs Phase 4 integration-tests); (8) locked-decision-4 cadence clause made explicit in the /harden-harness SKILL deliverable; (9) HOOK_ERROR breadcrumb surfacing added to inject-hook behavior and pipe-tests.
