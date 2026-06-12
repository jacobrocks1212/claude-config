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
- [x] Step 0 wired: `--run-start` marker write after preflight passes; EVERY terminal path per the 1c.6 PushNotification enumeration gets `--run-end` (marker deletion). Terminal checklist: all-features-complete, cloud/device-queue-exhausted, queue-missing, max-cycles, meta-cap, operator-chosen halt, script-error exits — all must call `--run-end` before their terminal action.
- [x] Cycle dispatch prose updated: consume the hook-injected `LAZY-ROUTE (hook-injected, turn N):` banner when present (the probe JSON + `cycle_prompt`/`cycle_model` arrive with the turn via inject hook); on guard denial, canonical recovery wired (re-probe → dispatch emitted prompt verbatim; no-route → `--emit-dispatch hardening`); hardening triggers 1–3 wired in SKILL prose.
- [x] All resolution/audit/investigation/recovery/coherence-recovery/needs-runtime dispatches switched from orchestrator-bound component prose to consuming `--emit-dispatch <class>` output verbatim (the dispatch prompt is the registered prompt — no hand-composition).
- [x] Counters: SKILLs stop hand-passing `--forward-cycles`/`--meta-cycles` flags in probe invocations (flags remain in CLI for compat); post-compaction re-entry prose updated to note counters arrive via marker/inject hook (the compaction cliff is closed by construction).
- [x] State Machine Summary and "Differences from /lazy-batch" blocks updated in all three skills; coupled-pair diff performed and recorded in the Implementation Notes comment at bottom of each SKILL.md. *(Wording note: the three batch skills carry no literal "State Machine Summary" section — that section lives in the single-step `/lazy` family, which writes no marker and was correctly untouched; the equivalents updated were the Notes sections, the cloud Differences table, and the coupled-pair comments.)*
- [x] Gates green: `lint-skills.py` (full flags), both state-script `--test` suites, `test_lazy_core.py`, `test_hooks.py`.

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

#### Implementation Notes (Phase 5 — 2026-06-11)

**Review verdict:** PASS-WITH-FIXES — reviewer ground-truthed every `--emit-dispatch` site key-by-key against the templates' @requires lines (perfect fidelity after fixes), verified terminal `--run-end` coverage against each skill's own enumeration, and confirmed denial-recovery prose matches `lazy_guard.py` source. Fixes applied by a fix subagent and re-verified (all five gates green): (1) the one real contract bug — `resolution_kind` values diverged three ways from the template's `needs-input|blocked` contract — fixed in all three skills; (2) **SPEC trigger-1 restored per locked decision 4**: every validate-deny now dispatches the hardening stage inline (`trigger_kind=validate-deny`) IN ADDITION to the re-probe recovery — the Phase 2 guard recipe had quietly narrowed hardening to refusal/no-route only; `_CORRECTIVE_RECIPE` extended to say so (test substrings preserved); (3) investigation-dispatch.md's hand-fill Agent dispatch demoted to subagent-contract reference (operative path is `--emit-dispatch investigation`); (4) banner examples corrected to lazy_inject.py's real output; (5) cloud variant gained the --run-start failure clause, script-error path, and accurate counter wording. **Documented decision (not a defect):** the denial re-probe advances persisted streak/counters a second time for one logical cycle — accepted; a denial IS evidence of a stuck cycle, so streak inflation on denials strengthens loop detection rather than corrupting it. Orphan note: `input-audit-prompt.md` is now referenced only by dispatch-input-audit.md's derivation comment — candidate for a future hardening round, not removed here.

---

### Phase 6: Registration, setup.ps1 check, live end-to-end validation

**Scope:** Arm the system on this machine (laptop, A9); prove all four success criteria live. This phase is the validation pass — it does NOT implement; it integrates, registers, and records evidence. All prior phases must be complete (and A6 resolved go) before this phase begins.

**Deliverables:**
- [x] Repair `~/.claude/hooks` symlink on this laptop per setup.ps1 manifest.psd1 definition (A9 finding); `setup.ps1` updated to check for this symlink's presence as part of its verification pass.
- [x] Per-machine registration snippet documented in `docs/specs/turn-routing-enforcement/REGISTRATION.md`: UserPromptSubmit (≥30s timeout per spec), SessionStart matcher `compact`, PreToolUse matcher `Agent|Task` — exact JSON fragment ready to paste into `~/.claude/settings.json`. Applied to THIS laptop's live `~/.claude/settings.json`.
- [x] `setup.ps1 check` extension: parse live `~/.claude/settings.json`, warn (not fail) when the two hook script filenames (`lazy-route-inject.sh`, `lazy-dispatch-guard.sh`) are absent from the registered hooks list.
- [x] Cross-platform pipe-test run records: both Windows (git-bash) and WSL platforms — results appended to `E2E_VALIDATION.md` (or referenced artifact).
- [x] Live E2E via scripted `claude -p` marked-run harness (or a 1-cycle real `/lazy-batch` run in AlgoBooth): five assertions recorded in `docs/specs/turn-routing-enforcement/E2E_VALIDATION.md` mapping each spec Success Criterion 1–4 to observed evidence:
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
- [x] `~/.claude/hooks` symlink resolves on this laptop. *(E2E_VALIDATION.md + orchestrator Get-Item verification, 2026-06-12)*
- [x] Both hook filenames appear in live `~/.claude/settings.json` hooks registrations. *(verified post-WU-6a)*
- [x] LAZY-ROUTE banner observed in `claude -p` harness session log. *(E2E assertion 1)*
- [x] Hand-composed Agent dispatch: deny JSON observed with corrective reason. *(E2E assertion 2 — all four recipe substrings)*
- [x] Registered emitted-prompt dispatch: allow JSON observed; registry entry `consumed: true` after. *(E2E assertion 3, consumed_by recorded)*
- [x] Marker absent from `~/.claude/state/` at run end. *(E2E assertion 4 + final orchestrator ls)*
- [x] Interactive `claude` session (no marker): no hook output injected, no denials. *(E2E assertion 5)*
- [x] Deliberate-deny follow-through observed: hardening dispatch emitted + allowed, HARDENING.md round (or triaged NEEDS_INPUT.md) present in `hardening-log/` (SC2). *(E2E assertion 6 — live Opus /harden-harness run, commit 3109343)*
- [x] Harness transcript: cycle heading byte-matches injected `cycle_header`; every executed dispatch resolves to a registry lookup hit (SC4). *(E2E assertions 1+7 — sha cross-artifact match)*

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

#### Implementation Notes (Phase 6 — 2026-06-12)

**Review verdict:** PASS — live E2E ran against the ACTUALLY REGISTERED hooks on this laptop; all seven assertions PASS with raw captures in E2E_VALIDATION.md (558 lines). Highlights: the deny path returned the full corrective recipe including the locked-decision-4 trigger-1 clause; the allow path consumed the nonce with `consumed_by` recorded; the deliberate deny was followed through with a real `--emit-dispatch hardening` → live Opus `/harden-harness` run that appended Round 1 to `hardening-log/2026-06.md` and committed it (`3109343 harden(docs): ...`) — the self-improvement loop executed end-to-end on its first real trigger. WU-6a incidents: `setup.ps1 repair -Target User` briefly symlinked the live settings.json to the tracked (desktop-path) file — restored from `.bak` immediately; per-machine settings stay an untracked real file per SPEC §Settings placement (the check now reports it as the known A9 `REAL` condition). Cleanup: scoped state dirs/fixture deleted; a stale `hook-error.json` (fail-open breadcrumb from an E2E first-attempt empty-stdin firing) was found in the real state dir and removed — **design wrinkle for a future hardening round: a breadcrumb left after marker deletion is never surfaced (inject fast-path exits first)**. Phase 2's carried risk (nested-dispatch structural isolation under registered hooks) was probed live and recorded in E2E_VALIDATION.md §Carried risks resolved. Hook timeouts registered: inject 90s (> 60s probe subprocess ceiling), guard 30s.

**Completion (gate-owned):** SPEC Status flip to Complete is the pipeline gate's action, not a checkbox here. All six phases implemented, reviewed (3× PASS-WITH-FIXES applied + re-verified, 3× clean), and live-validated; standing gates at close: test_lazy_core.py 277/277, test_hooks.py 21/21, both --test smokes (baselines byte-identical throughout), lint-skills.py full flags clean.

---

### Phase 7: Post-first-run hardening — deny ledger, depth-cap retry branch, transcription-surface reduction, checkpoint contract, meta cycle_header

**Scope:** Harden the harness against the five failure modes observed in the first enforced production run (AlgoBooth session `2f6f27dc`, 2026-06-12, graded in AlgoBooth `docs/features/_index/LAZY_BATCH_REVIEW_2026-06-12_overview.md`): 3 validate-denies with 0 executed hardening rounds; the depth-cap halt protocol declined as too blunt for a transcription-slip denial; 3 self-inflicted prompt mutations; a self-elected early stop with no contract shape; and 0/8 meta cycles carrying canonical headings. Unifying principle: move each prose contract into the state script / guard where the orchestrator cannot drift from it under context pressure.

**Validated Assumptions (Phase 7 additions):**

| assumption | how-confirmed | evidence |
|---|---|---|
| Guard process can write files into the state dir from hook context | runtime | Phase 6 E2E: `hook-error.json` breadcrumb observed written by the fail-open path; deny path runs in the same process/permissions |
| Deny reasons reach the orchestrator verbatim as Agent tool_result errors (so a ledger entry can capture what the orchestrator saw) | runtime | session `2f6f27dc` jsonl L201/L237/L503 — three live deny captures with full recipe text |
| `--emit-dispatch` output JSON is consumed as-is by the orchestrators (a new `cycle_header` field will be seen) | runtime | session `2f6f27dc`: 18 allowed dispatches all consumed emit output; forward-cycle `cycle_header` echo already proven 9/9 conforming vs 0/8 for headerless meta dispatches |
| Widening `normalize_prompt_for_hash` has no persistent-compat risk | code-provable (no runtime smell: pure script logic, registry entries are ephemeral with 30-min TTL; no cross-process shape involved) | `lazy_core.py` registry TTL + ring-cap design, Phase 1 tests |
| Marker fold counters are readable at emit time (for `[meta m/2N]` in `cycle_header`) | code-provable (no runtime smell: same-process file read; functions test-covered) | `lazy_core.py` `read_run_marker`/`fold_run_counters` + Phase 1 test section |

**Interface contract (fixed here so script-side and prose-side land coherently):**
- Deny ledger file: `lazy-deny-ledger.jsonl` in the state dir (`claude_state_dir()`), one JSON object per line: `{ts, tool_use_id, denied_sha12, reason_head, prompt_head, acked: false}`. Written best-effort by `lazy_guard.py` on EVERY deny (fail-open preserved — a ledger write failure never blocks the deny response).
- Probe enrichment (marker-gated — fields appear ONLY when a run marker is present, keeping `--test` baselines byte-identical): `pending_hardening: <int>` + `pending_denials: [<summaries>]` in `--probe` output.
- Ack semantics: `--emit-dispatch hardening` acks the OLDEST unacked ledger entry (FIFO, one per emission — preserves locked decision 4's one-dispatch-per-deny cadence).
- `--run-end` gains `--reason <terminal|checkpoint>` (default `terminal`) and refuses (exit 1, explanatory message) when unacked denials exist unless `--ack-unhardened` is passed (the override is recorded in the run-end message so retros can grade it).
- `--run-end --reason checkpoint` additionally requires `--next-route "<text>"` and writes `lazy-run-checkpoint.json` (`{reason, next_route, counters, ts}`) to the state dir; the next `--run-start` consumes the file (deletes it) and echoes its content in the run-start output as resume context.
- `emit_dispatch_prompt` output JSON gains `cycle_header`: `### {Step} — {work summary} [meta {m}/{2*max_cycles}]` where Step comes from a per-class map (investigation→`Investigate`, apply-resolution→`Resolve`, recovery/coherence-recovery→`Recover`, hardening→`Harden`, input-audit→`Audit`, needs-runtime-redispatch→`Validate`), work summary from `item_name` context (fallback `item_id`), and `m` from the marker's persisted meta counter.

**Deliverables:**
- [x] **WU-7.1 Deny ledger + routed hardening debt (scripts):** `lazy_guard.py` appends a ledger entry on every deny; `lazy_core.py` gains `read_deny_ledger()` / `pending_hardening()` / `ack_oldest_deny()`; probe output marker-gated enrichment per the interface contract; `--emit-dispatch hardening` performs the FIFO ack; `--run-end` refuses on unacked denials without `--ack-unhardened`. Mirrored in `bug-state.py`.
- [x] **WU-7.2 Depth-cap retry branch (skill prose, ×3 mirrored):** §1d.1's depth-cap paragraph distinguishes the guard's two deny shapes: corrective-recipe denial of a hardening dispatch (hash mismatch — transcription slip) → re-emit + exactly ONE verbatim re-dispatch attempt; the full halt protocol (run-end → ⚠ → PushNotification → STOP) fires only on the guard's halt reason (registered hardening-class entry) or a SECOND recipe denial.
- [x] **WU-7.3 Transcription-surface reduction:** (a) single-slot rule — every `@requires` token appears exactly ONCE in each dispatch template body; templates fixed where they violate; enforced by a new test over all dispatch templates; (b) `normalize_prompt_for_hash` widened: per-line trailing-whitespace strip + Unicode NFC (pure copy artifacts pass; semantic edits still deny); (c) skill rule (×3 mirrored): never dispatch an emission from an earlier turn — re-emit fresh in the dispatching turn.
- [x] **WU-7.4 Checkpoint contract:** script-side per the interface contract; skill-side (×3 mirrored): the budget-and-queue guard gains a sanctioned unattended-checkpoint arm — allowed only when a reliability trigger holds (≥2 guard denials this run, or an operator message requesting pause), and requires the checkpoint `--run-end` + a PushNotification carrying the probed next route; `AskUserQuestion` remains the attended path.
- [x] **WU-7.5 Meta `cycle_header` + reporting templates:** `emit_dispatch_prompt` emits `cycle_header` per the interface contract; `orchestrator-voice.md` T7 template gains the `### Completeness-policy applications (D7)` digest-table skeleton; the bug-doc spin-off path in the cycle prompt template gains the missing legs (PushNotification `"spun off {id} — {reason}"` + reverse-reference from the origin feature doc).
- [x] Tests: new `test_lazy_core.py` sections (ledger lifecycle + FIFO ack, run-end refusal/override, checkpoint write→consume round-trip, widened normalization, single-slot template assertion, `cycle_header` emission); `test_hooks.py` pipe-test for the guard's deny-ledger write; ALL standing gates green with `--test` baselines byte-identical (NO regeneration).

**Minimum Verifiable Behavior:** Scripted sequence on a fixture state dir: simulate a deny (invoke `lazy_guard.py` with a marked run + unregistered prompt) → ledger entry exists → `--probe` shows `pending_hardening: 1` → `--run-end` REFUSES → `--emit-dispatch hardening` acks → `--run-end --reason checkpoint --next-route "write-plan Phase 14"` writes the checkpoint file → next `--run-start` echoes and consumes it.

**Runtime Verification** *(checked by live harness or the next marked run — NOT by the implementation agent):*
- [x] Next real marked run: a (natural or deliberate) guard deny produces a ledger entry and the next probe surfaces `pending_hardening ≥ 1`. *(2026-06-12 live: denies 14:37Z + 19:43Z both ledgered; probe withheld route per Phase 8 — hardening-log Round 4)*
- [ ] Next real marked run ends through `--run-end` cleanly with the ledger empty (all denials hardened or explicitly `--ack-unhardened`-overridden).
- [x] A meta dispatch in the next run prints the emitted `cycle_header` verbatim (retro R-V-2 grades it conforming). *(2026-06-12 live: session e076ed30 L124 `### Resolve — Stem Management (incl. .stem.mp4) [meta 1/100]` — emitted header echoed)*

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in (per the header's MCP-runtime line).

**Prerequisites:** Phases 1–6 (complete). Consumes the audit evidence from AlgoBooth session `2f6f27dc` (the LAZY_BATCH_REVIEW_2026-06-12 artifacts).

**Files likely modified:**
- `user/scripts/lazy_guard.py`, `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py`
- `user/skills/_components/lazy-batch-prompts/dispatch-*.md` (single-slot fixes), `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (spin-off legs)
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `user/skills/_components/orchestrator-voice.md`

**Testing Strategy:**
- Entry point: `python user/scripts/test_lazy_core.py` (new Phase 7 section) + `python user/scripts/test_hooks.py` + both `--test` smokes + `lint-skills.py --check-projected --check-capabilities`.
- Ground-truth assertion: the MVB scripted sequence passes against a `LAZY_STATE_DIR`-scoped fixture; default (no-marker) probe output remains byte-identical to baselines.
- Boundary coverage: deny-ledger write failure (fail-open preserved); checkpoint file absent on plain `--run-end`; ack with empty ledger (no-op, not an error); NFC/trailing-whitespace normalization equivalence pairs + a semantic-mutation pair that still denies.
- Runtime gate: the next real marked `/lazy-batch` run (Runtime Verification rows above).

**Integration Notes for Next Phase:** The deny ledger is the new ground truth for retro R-O-9 grading (denials ↔ hardening rounds become mechanically auditable). The checkpoint file gives `/lazy-batch-retro` a sanctioned-vs-improvised signal for early stops. If a future phase adds park-event telemetry, follow the same marker-gated-enrichment pattern to keep baselines stable.

**Context from prior phases:**
- Marker-gated output enrichment (Phase 1 pattern) is the baseline-safety mechanism — reuse it for every new probe field.
- The guard's two deny shapes (corrective recipe vs depth-cap halt reason) were established in Phase 2/4; WU-7.2 keys the skill branch off that existing discriminator rather than inventing a new one.
- All `--test` baselines are byte-pinned and must NEVER be regenerated (standing rule since Phase 1).
- Coupled-pair mirroring (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud) is a hard gate (Phase 5 discipline).

---

#### Implementation Notes (Phase 7 — 2026-06-12)

**Review/verification verdict:** PASS — implemented by two file-disjoint subagents (scripts+templates / skill-prose), then ground-truth re-verified by the orchestrator with fresh gate runs: `test_lazy_core.py` **291/291** (+14 Phase 7 tests), `test_hooks.py` **22/22** (+1 deny-ledger pipe-test through the real `lazy-dispatch-guard.sh`), both `--test` smokes byte-identical (baselines untouched), `lint-skills.py --check-projected --check-capabilities` clean, projection 78 skills / 88 components, errors none. Implementation commit: `511b0b8`.

**Interface-contract deviations (documented, accepted):** (1) run-end's reason rides the EXISTING `--reason` flag (validated in-handler to `terminal|checkpoint`) rather than a new dedicated flag — `--reason` was already a general-purpose flag consumed by `__write_deferred_non_cloud__`; (2) `lazy-run-checkpoint.json` deliberately survives `delete_run_marker(clear_registry=True)` — consume-once lives in the NEXT `--run-start`, not in run-end teardown.

**Notable restructures:** `dispatch-needs-runtime-redispatch.md` had its two parallel mode sections collapsed into one always-selected header section to satisfy the single-slot rule; other templates converted duplicate `{token}` slots to prose references ("the denial reason quoted above"). `cycle-base-prompt.md`'s new spin-off legs use `<id>`-style placeholders (not braces) to respect the emitter's residue guard. `orchestrator-voice.md` and `cycle-base-prompt.md` are runtime-referenced-by-path (not `!cat`-embedded), so the source edits are the single authoritative copy.

**Runtime Verification rows remain open by design** — they are checked by the NEXT real marked `/lazy-batch` run (a live deny → ledger entry → `pending_hardening` probe surfacing; clean run-end with empty ledger; a meta dispatch printing its emitted `cycle_header`). Origin evidence: AlgoBooth session `2f6f27dc` retro artifacts (`LAZY_BATCH_REVIEW_2026-06-12*`).

---

### Phase 8: Concurrent-session safety — non-destructive marker staleness, routed (not surfaced) hardening debt, full-probe consumption

**Scope:** Close the three gaps exposed live on 2026-06-12 when an interactive session ran concurrently with a marked `/lazy-batch 50` run (AlgoBooth session `e076ed30`): (1) `read_run_marker` staleness path B is delete-on-read, so the interactive session's inject hook DELETED the live run's marker at ~14:53Z, silently disarming enforcement mid-run; (2) Phase 7's `pending_hardening` probe field was surfaced but the orchestrator piped probe JSON through a field-extractor and dispatched a forward route over live debt — surfacing is not routing; (3) Phase 7's emission-time ledger ack would let repeated emissions drain debt without any hardening dispatch occurring. Phase-count note: ratio (9−6)/6 = 0.50, exactly at the circuit-breaker boundary (≤ 0.50 proceeds); Phases 7–8 are operator-directed hardening rounds consuming live-run audit evidence, not corrective drift.

**Validated Assumptions (Phase 8 additions):**

| assumption | how-confirmed | evidence |
|---|---|---|
| Path B (session mismatch) deletes a LIVE run's marker when a concurrent session's hook fires | runtime | 2026-06-12 ~14:53Z: marker bound to `e076ed30` absent from state dir after interactive-session inject firings; `read_run_marker` docstring "both cause delete-on-read" |
| Orchestrators filter probe JSON through extractors (so a surfaced field can be invisible) | runtime | session `e076ed30` L158: probe piped to `python3 -c "...print(d['cycle_model'])..."` while `pending_hardening: 1` was live |
| Registry entries carry `class` + `item_id` (guard can identify a hardening-class allow for ack-on-consume) | runtime | live registry inspection 2026-06-12: entry keys `['class','consumed','emitted_at','item_id','nonce','prompt_sha256']` |
| Mid-run script edits are safe for the degraded in-flight run | code-provable (no runtime smell: all new behavior is marker-gated and that run's marker is already gone; scripts are re-exec'd per call) | `lazy_core.py` marker-gating pattern (Phases 1/7) |

**Interface contract:**
- `read_run_marker` path B (caller session_id ≠ bound marker session_id): return `None` WITHOUT deleting — the marker stays on disk for the owning session. Path A (age > 24h) and corrupt-file handling keep delete-on-read. Inject/guard inherit: a non-owner session sees no marker (no banner, fast-path allow) but never destroys the owner's run state.
- Probe debt routing (marker-gated AND debt-gated): when `pending_hardening > 0`, the probe WITHHOLDS the forward route — no `cycle_prompt` emission/registration — and emits `route_overridden_by: "pending-hardening-debt"` plus `hardening_emit_command`: a pre-composed `--emit-dispatch hardening` command string with `--context` bindings auto-derived from the OLDEST unacked ledger entry (`trigger_kind=validate-deny`, `denied_prompt_summary`=prompt_head, `denial_reason`=reason_head, `item_id`=current feature, `probe_json`=compact summary, `registry_state`=summary or `empty`, `cwd`). A `⚠ pending_hardening: N — forward route withheld` line goes to STDERR (stdout JSON stays parseable for the inject hook and any extractor — which now fails loudly on the missing `cycle_prompt` key instead of silently proceeding).
- Ack moves from emission-time to **guard-allow-time**: `--emit-dispatch hardening` no longer acks; instead `lazy_guard.py`, on ALLOWING a dispatch whose matched registry entry has `class == "hardening"`, acks the oldest unacked ledger entry (best-effort, fail-open). Debt clears only when a hardening dispatch actually reaches execution.
- Prose (×3 mirrored): Step 1a consumes the FULL probe JSON — piping probe output through field-extractors is banned; `route_overridden_by`, when present, MUST be honored before any forward dispatch.

**Deliverables:**
- [x] **WU-8.1 Non-destructive session-mismatch:** `read_run_marker` path B returns None without deletion; Phase 1 tests pinning delete-on-read-B revised; new tests: non-owner read leaves file intact + owner still reads it afterward; age-stale and corrupt-file deletion unchanged; inject/guard comments updated.
- [x] **WU-8.2 Routed hardening debt + guard-allow ack:** probe withholds forward route per the interface contract; emission-time ack removed (Phase 7 revision); guard acks on hardening-class allow; `bug-state.py` mirrored.
- [x] **WU-8.3 Full-probe consumption:** stderr `⚠` debt line; skill prose (×3): no field-extractor piping, honor `route_overridden_by`.
- [x] Tests: path-B non-destruction, debt-withheld probe shape (`route_overridden_by` + `hardening_emit_command` bindings + absent `cycle_prompt`), guard-allow ack (hardening-class allow acks oldest; cycle-class allow does not; ack fail-open), emission no longer acks, stderr line debt-gated; ALL standing gates green, `--test` baselines byte-identical (NO regeneration).

**Minimum Verifiable Behavior:** Scripted sequence on a fixture state dir: marked run + 1 unacked deny → `--probe --emit-prompt` returns `route_overridden_by: pending-hardening-debt` with NO `cycle_prompt` and a bound `hardening_emit_command`; running that command registers a hardening-class entry WITHOUT acking; a simulated guard ALLOW of that entry acks the ledger; the next probe returns a normal forward route. Separately: `read_run_marker(session_id="other")` returns None while the marker file remains on disk and `read_run_marker(session_id="owner")` still succeeds.

**Runtime Verification** *(checked by live runs — NOT by the implementation agent):*
- [x] An interactive session message during the next live marked run does NOT delete the marker (run ends with its own `--run-end`). *(2026-06-12 19:33Z incident: marker survived bystander injects — mis-BOUND (fixed by Phase 9) but never deleted)*
- [x] The next live deny → following probe withholds the forward route and the orchestrator dispatches hardening first (debt acked by the guard allow, visible in the ledger). *(2026-06-12 19:23:37Z: withheld route → hardening dispatch → guard-allow FIFO ack — hardening-log Round 4; repeated autonomously for the 19:43Z deny, acked_ts confirms)*

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification rows above stand in.

**Prerequisites:** Phase 7 (revises its ack semantics). Origin evidence: live incident 2026-06-12 (~14:53Z) + session `e076ed30`.

**Files likely modified:**
- `user/scripts/lazy_core.py`, `user/scripts/lazy_guard.py`, `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py`, `user/scripts/lazy_inject.py` (comment accuracy only)
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`

**Testing Strategy:**
- Entry point: `test_lazy_core.py` Phase 8 section (hermetic `LAZY_STATE_DIR`) + `test_hooks.py` pipe-test (inject with a marker bound to a different session → no banner AND marker file survives) + both `--test` smokes + `lint-skills.py --check-projected --check-capabilities`.
- Ground-truth assertion: the MVB chain passes; no-marker and no-debt probe outputs byte-identical to current behavior.
- Boundary coverage: bind-pending marker (session_id None) never session-stale (unchanged); debt present but marker absent → no withholding (debt is marked-run scoped); guard ack when ledger empty (no-op); corrupt ledger lines skipped.
- Runtime gate: next live marked run (Runtime Verification rows above).

**Integration Notes for Next Phase:** With path B non-destructive, a genuinely crashed run's marker now persists until age-staleness (24h) — acceptable: the guard's enforcement surface in non-owner sessions is fast-path-allow either way, and the next `--run-start` overwrites the marker. If that window proves troublesome, a future phase can add an owner-liveness probe (PID or transcript mtime) rather than reverting to delete-on-read.

**Context from prior phases:**
- Phase 7's deny ledger/ack helpers and marker-gated probe enrichment are the substrate; this phase REVISES Phase 7's emission-time ack (documented there as the original semantics).
- Marker-gated + debt-gated output additions keep the byte-pinned `--test` baselines safe (Phase 1/7 pattern).
- Coupled-pair mirroring across the three batch skills is a hard gate (Phase 5 discipline).

---

#### Implementation Notes (Phase 8 — 2026-06-12)

**Review/verification verdict:** PASS — script side by one Opus subagent, prose side by the orchestrator (3 skills mirrored + coupled-pair comment notes); orchestrator re-ran all gates fresh: `test_lazy_core.py` **297/297** (+6 net: 7 added, 3 revised per the contract — the path-B delete pin, the run-end-refusal middle leg now simulating guard-allow ack, and the guard-stale-marker pipe-test flipped to marker-survives), `test_hooks.py` **23/23** (+1: inject with a non-owner-bound marker → no banner AND marker intact), both `--test` smokes byte-identical, `lint-skills.py` full flags clean, projection errors none. Implementation commit: `ee2289e`.

**Key implementation decisions:** (1) `shlex.quote` escaping for `hardening_emit_command` context values (command targets bash on paste); (2) guard acks ONLY on the fresh first-time-consumption allow path, never on the idempotent re-fire path (avoids double-ack of one logical dispatch); (3) `oldest_unacked_deny()` / `build_hardening_emit_command()` / `registry_summary()` added as public `lazy_core` helpers for coupled-pair reuse; (4) stderr warning confirmed safe for `lazy_inject._run_probe` (`capture_output=True` separates streams).

**Phase 7 revision recorded:** emission-time ack removed — debt now clears only when the guard ALLOWS a hardening-class dispatch. Runtime Verification rows remain open for the next live marked run (non-owner-session marker survival; live debt → withheld route → hardening-first dispatch).

---

### Phase 9: Bind-at-guard — eliminate the bind-on-first-inject race

> ⚠ Phase-count circuit breaker acknowledged: (10−6)/6 = 67% > +50%. Overridden by operator direction 2026-06-12 ("Rebind and fix this issue") — Phases 7–9 are operator-directed hardening rounds consuming live incident evidence, not corrective decomposition drift.

**Scope:** Close the marker bind race observed live 2026-06-12 ~19:33Z: run-start writes a bind-pending marker, the inject hook fires BEFORE a turn's work, so the orchestrator's own invocation turn cannot bind — the first hook firing anywhere wins. A concurrent interactive session's message bound the live run's marker to the WRONG session (incident: marker `started_at 19:22:43Z` bound to the interactive session at 19:33), silently disarming the batch run's guard (non-owner fast-path) while spraying banners, spurious registry emissions, and repeat-counter inflation (3→4, 10→11 across two bystander messages) into the interactive session. Operator hand-rebind applied 19:38Z as immediate remediation (authorized; marker is otherwise a script-owned surface).

**Validated Assumptions (Phase 9 additions):**

| assumption | how-confirmed | evidence |
|---|---|---|
| Inject fires before the turn's work, so the invocation turn cannot bind | runtime | live marker `session_id: 2899da98…` (interactive session) on a run started from `e076ed30` at 19:22:43Z |
| Bystander injects advance the run's persisted repeat counters and register emissions | runtime | `repeat_count` 3→4, `step_repeat_count` 10→11, `turn` 3→4 across two interactive-session messages with the batch session idle-in-cycle |
| Only the orchestrator session can produce a guard ALLOW of a registered prompt (binding anchor is unforgeable by bystanders) | code-provable (no runtime smell: allow requires a registry hit; only the orchestrator dispatches emitted prompts — the property enforcement itself guarantees) | `lazy_guard.py` lookup path; Phase 6 E2E assertions 2–3 |

**Interface contract:**
- `lazy_inject.py` NEVER binds. Unbound marker (`session_id: null`) → silent exit: no banner, no probe, no emission registration, no counter advance. Bound non-owner → silent (Phase 8, unchanged). Bound owner → full banner (unchanged).
- `lazy_guard.py` binds on ALLOW: when the marker is unbound and validation produces an ALLOW (registered-prompt hit — fresh consumption or idempotent re-fire), stamp the marker with the caller's `session_id` (best-effort/fail-open: a bind failure never changes the allow) then allow. A DENY never binds. Bound-owner and bound-non-owner guard behavior unchanged (Phase 8).
- Accepted edge (documented, not fixed): during the unbound window (run-start → orchestrator's first dispatch, typically seconds), a bystander session's Agent dispatch is still validated and denied on lookup-miss, writing ledger debt. Rare; preserves enforcement of the run's own FIRST dispatch, which is the priority.

**Deliverables:**
- [x] **WU-9.1 Inject never binds:** remove the bind-on-first-hook-firing stamp from `lazy_inject.py`; unbound → silent exit before any probe/registration side effect; comments updated.
- [x] **WU-9.2 Guard binds on allow:** `lazy_guard.py` stamps the unbound marker on ALLOW (both allow paths), fail-open; deny paths never bind.
- [x] Tests: inject unbound → no output AND no registry/counter/marker mutation; guard unbound+hit → allow AND marker bound to caller; guard unbound+miss → deny AND marker stays unbound; bound-owner/non-owner behavior unchanged; revise the Phase 1/2 pins of bind-on-first-inject to the new contract; pipe-test: inject with unbound marker → exit 0, no stdout, marker file unchanged. ALL standing gates green, baselines byte-identical.

**Minimum Verifiable Behavior:** Fixture sequence: `--run-start` (unbound) → simulated inject firing from session A → no banner, marker still unbound → guard ALLOW of a registered prompt from session B → marker bound to B → inject from session B → banner; inject from session A → silent, marker intact.

**Runtime Verification** *(next live marked run):*
- [ ] Marker binds to the batch session at its first dispatch (inspect `session_id` mid-run) even when interactive messages arrive first.
- [ ] Interactive-session messages during the run produce no banner, no registry growth, and no counter movement.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config.

**Prerequisites:** Phase 8 (non-destructive non-owner semantics are the substrate). Origin evidence: live incident 2026-06-12 19:33Z (this session's hook-context captures).

**Files likely modified:** `user/scripts/lazy_inject.py`, `user/scripts/lazy_guard.py`, `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py` (+ `lazy_core.py` only if `bind_marker_session` needs a caller tweak).

**Testing Strategy:** `test_lazy_core.py` Phase 9 section (hermetic `LAZY_STATE_DIR`) + one `test_hooks.py` pipe-test; both `--test` smokes; `lint-skills.py` full flags. Boundary coverage: bind failure during allow (fail-open), unbound guard deny leaves marker unbound, owner-bound inject unchanged.

**Integration Notes for Next Phase:** With bind-at-guard, the marker's `session_id` is proof the bound session dispatched a registered prompt — retros can treat it as the orchestrator-session identifier. The accepted unbound-window edge is the remaining theoretical gap if a future round wants it.

**Context from prior phases:** Phase 8's non-owner semantics (invisible-not-deleted) make wrong-binds recoverable; this phase prevents them. Live-run safety: bound-owner code paths are untouched, so landing mid-run is safe (same rationale as Phase 8's mid-run-edit assumption row).

---

#### Implementation Notes (Phase 9 — 2026-06-12)

**Review/verification verdict:** PASS — one Opus subagent (scripts+tests), orchestrator re-ran all gates fresh: `test_lazy_core.py` **304/304** (+7), `test_hooks.py` **23/23** (1 pipe-test revised into the new unbound-silent contract; 6 preexisting tests re-pinned — 3 inject tests now use bound-owner markers, 3 multi-call guard tests thread one owner session id since bind-on-first-allow reclassifies later mismatched calls), both `--test` smokes byte-identical, lint + projection clean. Implementation commit: see git log (`feat(...): Phase 9 — bind-at-guard`). Live-run integrity verified post-implementation: real marker still bound to `e076ed30…`, untouched by the test suite (hermetic `LAZY_STATE_DIR` throughout).

**Key decisions:** (1) guard binds on BOTH allow paths (fresh consumption + idempotent re-fire), fail-open via `_bind_marker_on_allow`; (2) `bind_marker_session` needed no change; (3) a bound-non-owner guard call can never overwrite a bind — Phase 8's non-owner read returns None and exits via fast-path before any bind code; (4) the unbound-window bystander-deny edge is accepted and documented in the interface contract.

**Incident remediation record:** the 19:33Z wrong-bind was hand-repaired at 19:38Z by the operator-authorized rebind (marker `session_id` → `e076ed30…`) before this phase landed; bystander-inject counter inflation observed during the incident (repeat 3→4, step-repeat 10→11) stopped at rebind. Runtime Verification rows remain open for the next live marked run.

---

## Review Notes

**2026-06-11 — /spec-phases authoring review.** Ground-truth verified: yes (git status, line count 326, phase-heading grep all matched the drafting subagent's pasted block). **Review verdict: PASS-WITH-FIXES** — full SPEC coverage confirmed (all components land in exactly one phase; all four Locked Decisions intact; deny hook genuinely unarmed until Phase 6; failure-mode containments reflected). Nine localized fixes applied by the orchestrator post-review: (1) Phase 6 MVB section added; (2) E2E assertions 6–7 added covering Success Criteria 2 and 4; (3) turn-window freshness recorded as an explicit SPEC deviation with a compensating 30-min registry-entry TTL; (4) session-id-mismatch staleness test rows added to Phase 1; (5) spike item (e) added for the UserPromptSubmit task-notification limitation; (6) SessionStart(compact) payload enumerated (re-entry protocol + counters); (7) depth-guard ownership clarified (Phase 2 implements vs Phase 4 integration-tests); (8) locked-decision-4 cadence clause made explicit in the /harden-harness SKILL deliverable; (9) HOOK_ERROR breadcrumb surfacing added to inject-hook behavior and pipe-tests.
