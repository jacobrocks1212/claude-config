# Implementation Phases — Lazy Validation-Readiness

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this targets the claude-config harness (Python scripts `lazy_core.py`/`lazy_guard.py`/`lazy-state.py`, the dispatch guard, and skill prose); no AlgoBooth app surface is built here. Per `docs/features/mcp-testing/SPEC.md`, the untestable class is "tooling outside the AlgoBooth runtime." Verification is `pytest` over `test_lazy_core.py`/`test_hooks.py`, both state-script `--test` smokes (baselines byte-identical), `lint-skills.py`, and a next-marked-run live check. The F7/F8 AlgoBooth-side checks are exercised on the next workstation `/lazy-batch` run (noted per phase).

## Validated Assumptions

| assumption | how-confirmed | evidence |
|---|---|---|
| F1/F2b/F2c logic is pure Python over the on-disk signature-state file + prompt registry JSON; deterministic and unit-testable. No sidecar/IPC/audio/runtime smell. | code-read (no runtime-coupled smell — pure state-file logic) + unit-test | `lazy_core.update_repeat_counts` already unit-tests the sibling `step_count` debounce; `normalize_prompt_for_hash`/`prompt_sha256` are pure string fns. |
| **F2a rests on a Claude Code capability**: a PreToolUse hook can REWRITE the `Agent` tool's `prompt` (not just allow/deny) so the subagent receives the resolved text. | runtime-doc (confirmed) + Phase-3 in-phase smoke | `hookSpecificOutput.updatedInput` (with `permissionDecision: "allow"`) replaces tool input before execution — confirmed against current Claude Code hooks docs via claude-code-guide. Phase 3 leads with a live smoke certifying it on THIS version before building the resolver path. |
| F5/F8 surface resolver is pure filesystem grep (does an asserted MCP tool name resolve under `registrations/`; does an asserted emitter exist in source). | code-read (no runtime smell — static file grep) + unit-test against a fixture tree | Mirrors the AlgoBooth `check-docs-consistency.ts` static-scan style; no runtime needed. |
| F7's boot-time-vs-commit predicate is pure timestamp comparison; only the AlgoBooth runtime boot-stamp *availability* is runtime-coupled. | code-read predicate + next-run live check | Predicate compares a boot stamp to `git log -1 --format=%cI` over native-source globs; the AlgoBooth Step 1d.0 integration is verified on the next workstation run. |

> **Touchpoint audit:** `npm run audit:touchpoints` is an AlgoBooth-only tool and is not available in claude-config — N/A here. Manual LOC note: `lazy_core.py` (5142 LOC) and `lazy-state.py` (5310 LOC) are already large. F1/F2 **modify existing functions** in place (no net structural growth); F4-resolver and the F5 CLI are **new files** (no growth to the giants). No decomposition phase is warranted.

## Scope boundary (excluded by design)

- **Retro F3** (`parse_phases` counted `## Phase Summary`) and **F4** (`update_repeat_counts` non-hermetic to `repo_root`) were fixed live this run (hardening Rounds 10/8) — not re-implemented.
- **Retro F6** (mcp-test-fidelity tx-counter / staged-swap) is the AlgoBooth feature's charter — not a claude-config change.

---

### Phase 1: F1 — Debounce the dispatch-tuple `repeat_count`

**Status:** Complete

**Scope:** Extend the existing consume-count double-probe debounce in `lazy_core.update_repeat_counts` so it also guards the dispatch-tuple `count` (the Phase-9 streak), exactly as it already guards the step-level `step_count` (lazy-pipeline-ergonomics Phase 2). A second advancing probe of the same dispatch tuple with no dispatch (no registry consume) between the two probes is a RE-READ and must HOLD `count`, not increment it to 2 (which appends the loop block and flips `cycle_model` to sonnet).

**Deliverables:**
- [ ] In `update_repeat_counts` (lazy_core.py ~2673-2688), in the "same tuple AND same head" branch, HOLD `count` (`count = prior_count`) instead of `prior_count + 1` when the F2 re-read oracle proves no dispatch landed between the two probes (marker present + repo-scoped + both `consume_count`s recorded and equal — reuse the SAME `current_consume_count`/`prior_consume_count` machinery already computed for `step_count`).
- [ ] Preserve HEAD-aware reset: a new HEAD since the last probe still resets `count` to 1 (a commit is forward progress, never debounced). The debounce ONLY suppresses the re-read increment in the same-tuple-same-head branch.
- [ ] Preserve the no-marker / legacy-file paths byte-identical: when the oracle is the `_MISSING` sentinel (no marker, or unmarked/legacy prior), `count` increments exactly as today.
- [ ] Tests in `test_lazy_core.py`: (a) re-read (marker on, signature unchanged, consume_count equal) HOLDS `repeat_count`; (b) a real dispatch+consume between repeats increments `repeat_count`; (c) new HEAD still resets to 1; (d) no-marker path byte-identical; (e) legacy file (no `consume_count`) still increments.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "repeat" -q` passes, including the new re-read-holds-repeat_count case; and `python user/scripts/lazy-state.py --test` baseline output is byte-identical to pre-change (no-marker path unchanged).

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `update_repeat_counts` dispatch-tuple count branch (~2673-2759); docstring update noting `count` now shares the F2 debounce.
- `user/scripts/test_lazy_core.py` — new repeat_count debounce cases.

**Testing Strategy:** Pure unit tests with an injected `signature_path` (tmp file) and a controlled run marker + registry consume-count, mirroring the existing `step_count` debounce tests. Ground-truth assertion: a literal `repeat_count == 1` (held) vs `== 2` (incremented), not a recomputation. No boundary crossing — pure state-file logic.

**Integration Notes for Next Phase:** The `consume_count` oracle is shared; do not introduce a second consume-count read. F2 (Phases 2-3) touches the guard that PRODUCES the consume (every ALLOW consumes a nonce) — the F1 oracle depends on that invariant remaining "one consume per dispatch."

---

### Phase 2: F2b + F2c — Guard Unicode-normalize + decouple transcription-slip debt

**Status:** Complete

**Scope:** Two defense-in-depth mitigations for the transcription-slip denial class, independent of the structural by-reference path (Phase 3). **F2b:** widen `normalize_prompt_for_hash` to fold the Unicode characters the model trivially substitutes (em-dash/en-dash → `-`, curly quotes → straight, NBSP → space) BEFORE hashing — so an em-dash slip on an otherwise-verbatim prompt hashes equal and ALLOWS instead of denying. (This also improves the F1b auto-readmit near-match for free, since it shares `normalize_prompt_for_hash`.) **F2c:** reclassify a shape-(a) denial (the dispatched prompt is normalization-equivalent to a registered entry, i.e. differs only by characters the broadened normalize would fold) as a CHEAP re-dispatch — no `pending_hardening` deny-ledger entry, deny reason instructs verbatim/by-reference re-dispatch WITHOUT `--emit-dispatch hardening`. Reserve the debt gate for genuine no-route denials.

**Deliverables:**
- [ ] `normalize_prompt_for_hash` (lazy_core.py ~4272): add the dash/quote/NBSP folding leg AFTER the existing CRLF/CR/rstrip/NFC legs; document it as leg 5. A genuine word change still alters the hash.
- [ ] Guard transcription-slip classification (lazy_guard.py): before the default `_deny_and_ledger(_default_deny_reason(), …)`, detect when the dispatched prompt matches a registered entry's sha under the broadened normalization (a shape-(a) slip) and route to a NEW cheap-deny path that does NOT append a hardening-debt ledger entry and whose reason omits `--emit-dispatch hardening` (instructs re-probe + verbatim/by-reference re-dispatch).
- [ ] The genuine no-route deny (no normalization-equivalent registered entry) keeps the existing `_CORRECTIVE_RECIPE` + ledger-debt behavior unchanged.
- [ ] `lazy-dispatch-guard.sh` passthrough unchanged if the JSON shape is unchanged (deny is still a deny); confirm the new cheap-deny reason flows through the wrapper.
- [ ] Tests: `test_lazy_core.py` — em-dash/curly-quote/NBSP variants of a registered prompt now `prompt_sha256`-equal the clean form. `test_hooks.py` — (a) an em-dash slip on a registered prompt now ALLOWS (sha matches via F2b); (b) a shape-(a) near-slip the normalize doesn't fold → cheap transcription-slip deny with NO ledger append; (c) a genuine semantic edit → full corrective deny WITH ledger append (debt preserved).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py user/scripts/test_hooks.py -q` green; specifically a test asserting `prompt_sha256(emdash_variant) == prompt_sha256(hyphen_variant)` and a guard test asserting the deny-ledger file is NOT appended for a shape-(a) slip but IS for a semantic edit.

**Prerequisites:** None (independent of Phase 1; orderable in parallel, but landed second to keep the consume invariant stable).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `normalize_prompt_for_hash` (leg 5); possibly a small helper `is_transcription_slip(prompt) -> entry|None` reused by the guard.
- `user/scripts/lazy_guard.py` — `guard()` deny branches; a `_transcription_slip_deny_reason()` builder; route shape-(a) denials away from `_deny_and_ledger`'s debt path.
- `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py` — coverage above.

**Testing Strategy:** Unit tests at the normalize + guard boundary. Ground-truth assertions: sha equality for normalize-equivalents (literal compare of two digests), and the deny-ledger file's line count before/after (literal 0-delta for slip, +1 for semantic edit). Boundary covered: the guard's stdin→JSON decision path is driven through `guard(stdin_text)` directly (same entry point `main()` uses).

**Integration Notes for Next Phase:** Phase 3's by-reference path also benefits from the broadened normalize (the reference token carries no body to slip), so Phase 3 can assume F2b is in place. Keep the transcription-slip classifier (F2c) and the by-reference resolver (F2a) as distinct guard branches — by-reference is an ALLOW path, transcription-slip is a cheap-DENY path.

---

### Phase 3: F2a — Dispatch-by-reference (nonce → resolved prompt via `updatedInput`)

**Status:** Complete (impl + unit-verified; the live `updatedInput` smoke under Runtime Verification is certified on the next marked `/lazy-batch` run)

**Scope:** Eliminate the byte-exact-retype requirement structurally. Add a sanctioned dispatch form where the `Agent` call's `prompt` is a short reference token (the registered nonce), and the dispatch guard resolves it to the registered prompt bytes and returns `permissionDecision: "allow"` + `hookSpecificOutput.updatedInput: { prompt: <resolved text>, …otherFields }` so the subagent runs with the fully-expanded prompt. No retyping ⇒ no transcription-failure class, for cycle prompts AND meta dispatches. The reference path consumes the nonce exactly like the verbatim path (one allow = one consume), so F1/F2's consume oracle is unaffected.

**Integrity invariant:** a reference carries NO hand-composed body, so turn-routing's "hand-composed prompts are unexecutable" guarantee is preserved by construction (the bytes are the registered bytes). The guard must record `dispatch_by_reference: true` in its allow telemetry/ledger so the path is auditable.

**Deliverables:**
- [ ] **Capability smoke FIRST** (see Runtime Verification) — certify `updatedInput` rewrites the `Agent` prompt on THIS Claude Code version before building the resolver path. If the smoke fails, STOP and surface (do not ship a half-wired reference path).
- [ ] Reference-form detection in `lazy_guard.py`: recognize a reference token (a sanctioned sentinel form, e.g. `prompt` is exactly `@@lazy-ref nonce=<hex>` — define the exact grammar in the SKILL prose) and resolve it via a new `lazy_core.resolve_emission_by_nonce(nonce)` that returns the unconsumed/fresh entry (TTL + run-start gated, mirroring `lookup_emission`).
- [ ] On a valid reference: ALLOW + consume the nonce (recording consumer) + bind-marker-on-allow (Phase 9 parity) + return `updatedInput` with the resolved `prompt` (preserving the other `tool_input` fields: `model`, `subagent_type`, `description`). Record `dispatch_by_reference: true` (audit event).
- [ ] Reference to a missing / consumed / stale / wrong-class nonce → DENY via the existing corrective path (never a spurious allow); fail-open on any resolver error → fall through to normal deny.
- [ ] `lazy-state.py` / inject hook: surface the reference token alongside the verbatim `cycle_prompt` so the orchestrator can choose by-reference dispatch (the nonce is already surfaced as `nonce=<hex>` in the LAZY-ROUTE banner — expose the exact `@@lazy-ref …` form the guard expects).
- [ ] SKILL prose: document the by-reference dispatch form as the PREFERRED dispatch in `lazy-batch/SKILL.md` (and mirror into `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`); state that verbatim paste remains valid (F2b/F2c cover it).
- [ ] Tests: `test_hooks.py` — reference → allow + `updatedInput.prompt == registered text` + nonce consumed + audit event; missing/consumed/stale/hardening-class reference → deny; resolver exception → deny (fail-open).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -k "reference" -q` green: a guard call with `tool_input.prompt = "@@lazy-ref nonce=<hex>"` for a fresh registered entry returns JSON with `permissionDecision == "allow"` and `hookSpecificOutput.updatedInput.prompt` equal to the registered prompt bytes; the nonce is marked consumed.

**Runtime Verification** *(checked by manual/live smoke — NOT by the implementation agent):*
- [ ] `updatedInput` capability smoke (reachability-smoke — workstation-eligible): in a live marked run, dispatch one real `Agent` with a `@@lazy-ref nonce=<hex>` prompt and confirm from the subagent transcript that it received the RESOLVED prompt text, not the reference token. Certifies the load-bearing `updatedInput` assumption on this Claude Code version.
- [ ] Audit event `dispatch_by_reference: true` appears for a by-reference allow and is recognized by the `lazy-batch-retro` grader (no new spurious deviation).

**Prerequisites:** Phase 2 (shared broadened `normalize_prompt_for_hash`; distinct guard branches).

**Files likely modified:**
- `user/scripts/lazy_guard.py` — reference-form branch in `guard()`; `updatedInput` allow JSON (extend `_allow_json` or add `_allow_with_updated_input(reason, updated_input)`).
- `user/scripts/lazy_core.py` — `resolve_emission_by_nonce`; audit-event writer for `dispatch_by_reference`.
- `user/scripts/lazy-state.py` — surface the `@@lazy-ref` token in the emitted route/banner.
- `user/hooks/lazy-route-inject.sh` — include the reference form in the injected LAZY-ROUTE banner if not already present.
- `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — document the by-reference dispatch form.
- `user/scripts/test_hooks.py` — coverage above.

**Testing Strategy:** Unit-test the guard's reference branch through `guard(stdin_text)` with a real registered entry (drive the nonce from `register_emission`, not a hand-built entry — false-green smell #2). The live `updatedInput` smoke is the gating runtime check (the unit test proves the guard EMITS `updatedInput`; the smoke proves Claude Code HONORS it). Name both explicitly; do not call the boundary covered on the unit test alone.

**Integration Notes for Next Phase:** None downstream depends on F2a. If the live smoke reveals `updatedInput` is not honored on the target version, the verbatim+F2b/F2c path (Phase 2) is the complete fallback — ship Phases 1-2-4-5-6 and record F2a as deferred-pending-capability.

---

### Phase 4: F5 — Validation-readiness pre-screen (+ shared surface resolver)

**Status:** Complete

**Scope:** Build the shared surface-existence resolver (the grep core F5 and F8 both consume) and wire its first consumer: a docs-only validation-readiness pre-screen. For each candidate feature carrying `DEFERRED_NON_CLOUD.md`, the pre-screen verifies that every MCP tool name asserted by the feature's `mcp-tests/` scenarios resolves under the target repo's `src-tauri/src/ipc/mcp/registrations/`, and that the asserted production emitter/wiring exists in source — emitting a per-feature `ready | needs-work` verdict naming the missing surface. Advisory, not a hard gate.

**Deliverables:**
- [ ] New `user/scripts/surface_resolver.py` — generic, repo-root-parameterized: `resolve_tool(name, repo_root) -> bool` (greps `registrations/`), `resolve_emitter(symbol, repo_root) -> bool`, and a scenario parser that extracts asserted tool/emitter names from an `mcp-tests/*.md` scenario file. Pure filesystem; no runtime.
- [ ] New `user/scripts/validation_readiness.py` (CLI) — given a repo root + queue, for each `DEFERRED_NON_CLOUD` feature print a `ready | needs-work` verdict table with the specific missing surfaces; non-zero verdict is advisory (exit 0), the table is the output.
- [ ] SKILL prose: a `lazy-batch` pre-loop advisory step (near Step 0) that runs `validation_readiness.py` and prints the verdict table before front-loading; explicitly advisory (operator may still front-load a `needs-work` feature), and the verdict is logged so a later deep blocker is traceable to an ignored pre-screen.
- [ ] Tests: `surface_resolver` unit-tested against a fixture registrations tree + fixture scenario (resolves a present tool; flags an absent tool/emitter; parses tool names out of a scenario). `validation_readiness` smoke against a fixture repo producing a known verdict table.

**Minimum Verifiable Behavior:** `python user/scripts/validation_readiness.py --repo-root <fixture>` prints a verdict table where a feature whose scenario asserts a present tool is `ready` and one asserting an absent tool is `needs-work` with the missing tool named; `python -m pytest user/scripts/test_surface_resolver.py -q` green.

**Prerequisites:** None (independent; the resolver is new).

**Files likely modified:**
- `user/scripts/surface_resolver.py` (new), `user/scripts/validation_readiness.py` (new).
- `user/scripts/test_surface_resolver.py` (new) + a small fixture tree under `user/scripts/_fixtures/` (or tmp-built in the test).
- `user/skills/lazy-batch/SKILL.md` — pre-loop advisory step.

**Testing Strategy:** Pure filesystem resolver — unit tests build a tiny fixture `registrations/` + `mcp-tests/` tree (tmp dir) and assert literal `ready`/`needs-work` verdicts and the named missing surface (ground-truth literals, not recomputation). No boundary crossing.

**Integration Notes for Next Phase:** F8 (Phase 5) is the SECOND consumer of `surface_resolver` — keep the resolver API stable and repo-root-parameterized so F8's authoring-time lint imports it directly rather than re-implementing the grep.

---

### Phase 5: F8 — Scenario-surface existence lint (authoring-time + qg rule)

**Status:** Complete — 5a (claude-config lint + write-plan/execute-plan prose) and 5b (AlgoBooth `scenario-surface-tools` warning rule in `check-docs-consistency.ts`) both landed

**Scope:** Catch scenarios asserting non-existent tools/emitters at AUTHORING time (inside the write-plan/execute-plan cycle), ~3 cycles earlier than the Step-9 mcp-test discovery. Reuses Phase 4's `surface_resolver`. Add (a) an authoring-time lint step the write-plan/execute-plan cycle runs after authoring a scenario, and (b) a project-wide enforcement so it holds even outside a pipeline cycle.

**Deliverables:**
- [ ] `surface_resolver`-backed lint entry (e.g. `surface_resolver.py --lint <scenario-file> --repo-root <root>`): for a scenario, error (exit non-zero) when any asserted MCP tool name does not resolve in `registrations/` or any asserted emitter has no source emitter; the message names the missing surface + scenario file:line.
- [ ] SKILL prose: write-plan / execute-plan cycle authoring step — after authoring or modifying an `mcp-tests/*.md` scenario, run the lint and fix before the plan lands (`user/skills/write-plan/SKILL.md`, `user/skills/execute-plan/SKILL.md`).
- [ ] Project-wide enforcement (AlgoBooth-side): a `qg:docs-consistency` rule in AlgoBooth's `scripts/check-docs-consistency.ts` (TS) mirroring the Python lint's check, so a scenario asserting a non-existent tool fails the gate even when authored outside a pipeline cycle. *(Cross-repo deliverable — lands in the AlgoBooth repo; verified on the next workstation run.)*
- [ ] Tests: `test_surface_resolver.py` lint cases (present tool passes; absent tool fails with named surface + location). AlgoBooth-side: a docs-consistency unit case for the new rule (in the AlgoBooth repo's test suite).

**Minimum Verifiable Behavior:** `python user/scripts/surface_resolver.py --lint <fixture-scenario-asserting-absent-tool> --repo-root <fixture>` exits non-zero and names the missing tool; the same against a present-tool scenario exits 0.

**Runtime Verification** *(checked on the next workstation `/lazy-batch` run — NOT by the implementation agent):*
- [ ] The AlgoBooth `qg:docs-consistency` rule flags a scenario asserting a non-existent MCP tool (exercised when the AlgoBooth-side rule lands).

**Prerequisites:** Phase 4 (`surface_resolver`).

**Files likely modified:**
- `user/scripts/surface_resolver.py` — add the `--lint` CLI mode.
- `user/skills/write-plan/SKILL.md`, `user/skills/execute-plan/SKILL.md` — authoring-time lint step.
- `user/scripts/test_surface_resolver.py` — lint cases.
- *(AlgoBooth repo)* `scripts/check-docs-consistency.ts` + its test — the `qg:docs-consistency` mirror rule.

**Testing Strategy:** Reuse Phase 4's fixture tree for the Python lint (literal exit-code + named-surface assertions). The TS qg rule is unit-tested in the AlgoBooth repo against a fixture scenario. Boundary note: the Python lint and the TS qg rule are two enforcement points of the SAME check in two languages — the SPEC's "share the resolver" is honored within each repo (Python F5+F8 share `surface_resolver`; the TS rule is the project-wide mirror), not by cross-language code-sharing.

**Integration Notes for Next Phase:** None downstream.

---

### Phase 6: F7 — Stale-binary detection in Step 1d.0

**Status:** Complete (impl + unit-verified; the live Step-1d.0 restart-forcing behavior under Runtime Verification is certified on the next workstation `/lazy-batch` run)

**Scope:** Stop the pre-mcp-test readiness check from trusting `GET /health == 200` when the running runtime is a stale binary (Rust changed since boot). Compare the runtime's boot stamp against the newest commit touching native source (`src-tauri/` + `crates/`); force a `dev:restart` when native source advanced since boot. The POLICY + the generic predicate live in claude-config; the AlgoBooth-runtime-shaped integration lives in the AlgoBooth-side Step 1d.0 / mcp-test precheck prose.

**Deliverables:**
- [ ] Generic predicate (claude-config) — a small helper (Python in `user/scripts/`, or documented shell snippet) `native_source_newer_than(boot_stamp, repo_root, globs) -> bool` comparing `boot_stamp` to `git log -1 --format=%cI -- <globs>`; globs configurable (default `src-tauri crates`), so it is not AlgoBooth-only.
- [ ] SKILL prose: `lazy-batch` Step 1d.0 (and the `repos/algobooth/.claude/skills/lazy-batch-cloud` mirror where applicable) — before an mcp-test cycle, read the runtime boot stamp; if native source advanced since boot, force `dev:restart` instead of trusting health=200. Document where the boot stamp comes from (session-log boot stamp if sufficient; otherwise note the minimal `boot_commit`/`boot_time` health-payload extension as the AlgoBooth-side follow-up).
- [ ] Tests: predicate unit-tested (boot stamp older than newest native commit → True; newer → False; no native commits → False).

**Minimum Verifiable Behavior:** `python -m pytest` over the predicate test passes: given a boot timestamp and a fixture git repo with a native-source commit after that timestamp, the predicate returns True (restart needed); before → False.

**Runtime Verification** *(checked on the next workstation `/lazy-batch` run):*
- [ ] After a Rust change with a still-running stale runtime, Step 1d.0 forces a `dev:restart` rather than dispatching mcp-test against the stale binary.

**Prerequisites:** None (independent).

**Files likely modified:**
- `user/scripts/` — the generic predicate helper + its test.
- `user/skills/lazy-batch/SKILL.md` (Step 1d.0); `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` mirror; AlgoBooth `mcp-test` precheck prose if the boot-stamp source needs the health-payload extension.

**Testing Strategy:** Unit-test the pure predicate against a tmp git fixture (literal True/False on timestamp ordering). The AlgoBooth runtime integration is verified live on the next workstation run (the boot-stamp source is the only runtime-coupled part).

**Integration Notes for Next Phase:** Phase 7 builds on this spec's run-lifecycle surfaces (the run marker + `--run-start`/`--run-end`) and extends Phase 3's dispatch-by-reference to meta prompts.

---

### Phase 7: Stop-authorization enforcement (no unilateral run-end) + meta-dispatch by-reference

**Status:** Complete (impl + unit-verified — 385 harness tests; both `--test` smokes byte-identical; the 2 live Runtime Verification rows certify on the next marked `/lazy-batch` run)

**Scope:** Make it **mechanically impossible** for the orchestrator to end a `/lazy-batch` (or `/lazy-bug-batch` / `/lazy-batch-cloud`) run except on `max-cycles`, a genuine script-emitted terminal, or explicit operator authorization. Today the run-lifecycle has no stop-authorization gate — `lazy-state.py --run-end` retires the marker for any caller-supplied reason, and the "unattended-only + ≥2-denial reliability trigger" that is supposed to bound checkpoint stops is **pure prose in the SKILL.md with zero enforcement** (the marker doesn't even record attended-vs-unattended). This phase moves that bound from prose into the script, and eliminates the contributing cause (meta-prompt hand-transcription) by extending Phase 3's dispatch-by-reference to `--emit-dispatch` meta prompts.

> **Motivating incident (live, 2026-06-14).** During an **attended** `/lazy-batch 50` run, the orchestrator stopped permanently at **5/50** forward cycles via `lazy-state.py --run-end --reason checkpoint --next-route …` — without presenting an `AskUserQuestion`. Root cause: the checkpoint run-end handler (`lazy-state.py` ~4993-5042) gates only on (1) reason ∈ {terminal, checkpoint}, (2) no unacked hardening debt, (3) `--next-route` present, then deletes the marker unconditionally. The unattended-only/≥2-denial gating was unenforced prose; the 2 "denials" that satisfied the prose trigger were the orchestrator's own meta-prompt transcription slips (F2a covers cycle prompts but not `--emit-dispatch` meta prompts, forcing byte-exact hand-transcription of an 8 KB apply-resolution prompt). Net: a permanent stop with budget + queue both remaining, no operator instruction — the exact behavior the pipeline must never exhibit.

**Deliverables:**
- [ ] **Marker records attendedness.** `lazy_core.write_run_marker` persists `attended: bool` (default `true`). `lazy-state.py --run-start` (feature + bug) gains an `--unattended` flag — scheduled/cron invocations pass it; interactive `/lazy-batch` does not, so it defaults attended. A legacy marker lacking the field is treated as **attended** (the stricter gate is the safe default).
- [ ] **Stop-authorization gate on `--run-end` (the core fix).** New `--operator-authorized` flag. In the run-end handler:
  - `--reason checkpoint` against an **attended** marker REFUSES without `--operator-authorized` — exit 1, marker + registry **kept in place**, output `{"run_marker_deleted": false, "refused": "<recipe>"}`; the recipe instructs: continue the loop, or route the stop through the budget-and-queue-guard `AskUserQuestion` and pass `--operator-authorized` only AFTER the operator confirms. An **unattended** marker keeps the existing checkpoint behavior (the sanctioned overnight pause).
  - `--reason terminal` gains an explicit `--terminal-reason <reason>`; if the supplied reason is NOT in the sanctioned stop-terminal set (`all-features-complete`, `all-bugs-fixed`, `max-cycles`, `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-missing`, `blocked-halt-for-manual`, `needs-research`, `queue-blocked-on-research`) it REFUSES unless `--operator-authorized` (kills the fabricated-terminal silent stop). Backward-compatible: `--terminal-reason` omitted → current behavior + a deprecation note in the output.
- [ ] **Extend F2a dispatch-by-reference to `--emit-dispatch <class>` meta prompts** (eliminate the contributing cause). `lazy-state.py --emit-dispatch` emits a `dispatch_prompt_ref` (`@@lazy-ref nonce=<hex>`) alongside `dispatch_prompt`, registered exactly like cycle prompts so the guard's existing reference-resolution path (`lazy_guard.py`, Phase 3) rewrites it to the registered bytes via `updatedInput`. Removes byte-exact hand-transcription for every meta dispatch (apply-resolution, input-audit, hardening, recovery, coherence-recovery, needs-runtime-redispatch, investigation).
- [ ] **Skill-prose hardening** (`user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`): a HARD CONSTRAINT — the orchestrator MUST NOT end a run except on `max-cycles` or a genuine script-emitted terminal it just received from the probe. Any *desire* to pause for any other reason (context pressure, reliability friction, "I should checkpoint", ≥2 denials in an attended run) MUST first route through the budget-and-queue-guard `AskUserQuestion` and may checkpoint only by passing `--operator-authorized` after the operator confirms. Rewrite the budget-and-queue-guard + unattended-checkpoint-arm wording so the ≥2-denial reliability trigger sanctions an **unattended** checkpoint only — never a unilateral attended-run stop. Update every meta-dispatch site to PREFER `dispatch_prompt_ref` (verbatim fallback only when absent). Cite this incident.
- [ ] **`lazy-batch-retro` R-O grader rule:** a non-sanctioned early stop is a HARD R-O FAIL — a checkpoint `--run-end` in an attended run without operator authorization, OR a `--run-end --reason terminal` whose reason isn't a sanctioned stop-terminal / wasn't actually emitted by the probe. Detectable from the marker's `attended` field + the run-end invocation + the absence of a preceding `AskUserQuestion` in the session JSONL.
- [ ] Tests (`test_lazy_core.py`): marker defaults attended; `--unattended` records unattended; checkpoint run-end refuses when attended + no-auth (marker kept on disk); allowed when `--operator-authorized` OR unattended; `--terminal-reason` validation (sanctioned passes, non-sanctioned refuses without auth). (`test_hooks.py`): a meta dispatch via `@@lazy-ref` resolves to the registered meta prompt and ALLOWs. Both `lazy-state.py` / `bug-state.py --test` smokes stay byte-identical on the no-marker path.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "run_end or attended or terminal_reason" -q` passes — specifically a test asserting `--run-end --reason checkpoint` against an attended marker returns `run_marker_deleted: false` (exit 1) without `--operator-authorized`, and `run_marker_deleted: true` with it (or when the marker is unattended).

**Runtime Verification** *(checked on the next marked `/lazy-batch` run — NOT by the implementation agent):*
- [ ] An attended run cannot retire its marker via `--run-end --reason checkpoint` without `--operator-authorized`; the orchestrator that tries it is forced to continue or to `AskUserQuestion` first.
- [ ] A meta dispatch (e.g. apply-resolution) dispatched via `@@lazy-ref` is resolved + ALLOWed by the guard (no hand-transcription, no transcription-slip denial).

**Prerequisites:**
- Phase 3 (F2a dispatch-by-reference + the guard's `@@lazy-ref` resolution path + `updatedInput` — confirmed live) — deliverable 3 extends it to meta prompts.
- turn-routing-enforcement (Complete) — owns `write_run_marker` / `--run-start` / `--run-end` / the checkpoint contract that deliverables 1-2 modify.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `write_run_marker` (`attended` field); `read_run_marker` tolerance; `--emit-dispatch` registration path for `dispatch_prompt_ref`.
- `user/scripts/lazy-state.py` (+ `bug-state.py` parity) — `--run-start --unattended`; `--run-end` `--operator-authorized` + `--terminal-reason` gates; `--emit-dispatch` `dispatch_prompt_ref` emission.
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — stop-authorization HARD CONSTRAINT + budget-guard/checkpoint-arm rewrite + by-reference meta dispatch.
- `repos/algobooth/.claude/skills/lazy-batch-retro/SKILL.md` — the R-O non-sanctioned-stop grader rule.
- `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py` — coverage above.

**Testing Strategy:** Pure script/unit logic — the stop-authorization gate and the `attended` marker field are code-provable and unit-tested against an injected marker + temp state dir (literal `run_marker_deleted` / exit-code assertions). The meta-dispatch by-reference reuses Phase 3's already-certified `updatedInput` resolution path (no new runtime capability — the guard branch exists), unit-tested through `lazy_guard.guard()`. The two live Runtime-Verification rows are certified on the next marked run. `MCP runtime: not-required` (claude-config harness — consistent with this spec).

**Integration Notes for Next Phase:** Terminal phase. The `attended` marker field is now available to any future run-lifecycle logic; the `dispatch_prompt_ref` closes the last hand-transcription surface in the dispatch path.

**Context from prior phases:** Builds directly on Phase 3 (the `@@lazy-ref` grammar, `resolve_emission_by_nonce`, the guard's `updatedInput` allow path, and `register_emission`'s `prompt_raw`). The transcription-slip class Phase 2 (F2c) made *cheap* is here made *impossible* for meta prompts (by-reference, like Phase 3 did for cycle prompts) — F2c correctly fired on this incident's slips (no hardening debt), proving the layered defense; this deliverable removes the slip surface entirely. The stop-authorization gate is the run-lifecycle analogue of turn-routing-enforcement's dispatch-authorization guard: enforcement moves from prose into the script so an LLM orchestrator under context pressure cannot rationalize around it.

### Phase 8: Pipeline-efficiency — gate `/retro` re-runs on phase-kind + close the `/execute-plan` finalization gap

**Status:** In-progress

**Scope:** Two measured pipeline-efficiency defects surfaced by the 2026-06-14 `/lazy-batch-retro` of the AlgoBooth `d7-multi-timbral` run (review artifact: `AlgoBooth:docs/features/audio/audio-vision/domains/d7-multi-timbral/LAZY_BATCH_REVIEW_2026-06-14.md`). Both waste forward/meta cycles in the corrective-phase tail without changing correctness; both fixes are pure harness/script + skill-prose. (1) The `/retro` step is re-run after **every** `/add-phase`, including corrective fix-phases that change no design surface — pure interstitial overhead. (2) `/execute-plan` sometimes lands all work but fails to flip the plan/per-phase status to `Complete` when the only remaining-open deliverables are Step-9-owned Runtime-Verification rows, forcing a redundant re-dispatch.

> **Motivating evidence (measured, d7-multi-timbral run, 2026-06-14).** `/retro` ran **5×** (~645k tokens / ~19 min / 5 Opus cycles), re-triggered "stale" by `lazy-state.py` Step 8 after every phase add (Phases 7→8→9→10→11). **Rounds 2–5 ALL returned zero significant divergences** and triggered zero corrective `/execute-plan` — ~4 of 5 rounds (~520k tok) were pure overhead. Root cause is structural: `/retro` runs BEFORE `/mcp-test` (Step 8 → Step 9), so every `blocked-mcp-test → add-corrective-phase → re-validate` loop drags a fresh retro round in front of the re-validation, auditing a design that mcp-test is about to find still-broken. The corrective phases were driven by **runtime** failures retro structurally cannot observe, and they change no design surface (they make the impl satisfy the EXISTING SPEC) — so retro had nothing to find, by construction. Separately, `/execute-plan` Phase 11 (cycle 33, 46 min) ticked every deliverable but left the plan `Ready` / per-phase `In-progress` because only Runtime-Verification rows remained open; `lazy-state.py` re-routed to `/execute-plan` and a redundant cycle 34 (1.8 min, ~97k tok) did nothing but flip the plan to Complete (Phases 7–10's execute cycles flipped correctly — Phase 11's did not).

**Deliverables:**
- [ ] **Phase-kind tagging in `/add-phase`.** A corrective fix-phase (one born from a blocked `/mcp-test` / validation failure whose scope is making the impl satisfy the EXISTING SPEC, NOT expanding design) is tagged `corrective`; a design-expanding phase is tagged `design` (default). Persist the tag as a per-phase machine-readable marker that `parse_phases` can read — preferred shape: a `**Phase kind:** corrective | design` line directly under the per-phase `**Status:**` line (mirrors the existing `**MCP runtime:**` per-phase convention and survives the docs-consistency parse). The blocked-resolution `/add-phase` dispatch (`_components/blocked-resolution.md` + `_components/investigation-dispatch.md` consumers) sets `corrective` when the trigger is a `blocker_kind: mcp-validation` / `execute-plan-scope` resolution; an interactive/operator `/add-phase` defaults `design` unless told otherwise. Update `_components/sentinel-frontmatter.md` / the PHASES schema doc + `add-phase/SKILL.md` Step 4 accordingly.
- [ ] **Retro-staleness gate on phase-kind (`lazy-state.py` Step 8 — the high-leverage fix).** `parse_phases` exposes each phase's `phase_kind`. The Step-8 "retro is stale — N phases added since `RETRO_DONE.md`" check is narrowed: re-stale `/retro` **only when ≥1 NON-corrective (`design`) phase has landed** since the last `RETRO_DONE.md` (`phase_count_at_retro`). A run of purely `corrective` phases since the last retro does NOT re-trigger retro — the design surface is unchanged, so there is nothing to re-audit. The final design state is still retro'd once: the last `design` phase (or, failing that, the completion pass still requires `RETRO_DONE.md`, so a feature whose ONLY post-retro phases were corrective keeps its existing valid `RETRO_DONE.md` and proceeds to `/mcp-test` → completion). Mirror the change in `bug-state.py` if the bug pipeline shares the staleness check.
- [ ] **Close the `/execute-plan` finalization gap.** Pick the more robust of: **(a)** tighten `/execute-plan` Step 4 (`execute-plan/SKILL.md`) so a plan whose only-remaining-open deliverables are Runtime-Verification rows is flipped plan→`Complete` + per-phase→`Complete` in the same pass (matching Phases 7–10's behavior); OR **(b)** have `lazy-state.py` route "all non-verification deliverables checked, plan still `Ready`/`In-progress`" to the existing `__flip_plan_complete_stale__` pseudo-skill instead of re-dispatching a full `/execute-plan` cycle. (b) is likely more robust — it makes the state machine self-correct regardless of which skill revision ran — but (a) prevents the stale state from arising in the first place; implement whichever the analysis shows is the single-point fix, and note the rejected option in the Implementation Notes.
- [ ] **`lazy-batch-retro` grader awareness (light):** the R-RE / efficiency rules should recognize `phase_kind: corrective` so a future audit does NOT flag a *correctly-skipped* retro round as a missing-retro violation, and CAN flag a corrective phase that wrongly re-triggered retro. (Prose rule addition; no new force-cap.)
- [ ] Tests (`test_lazy_core.py`): `parse_phases` reads `phase_kind` (default `design` when the line is absent — back-compat); the Step-8 staleness predicate returns not-stale when only `corrective` phases landed since `RETRO_DONE.md` and stale when ≥1 `design` phase did; the execute-plan finalization path (whichever option) flips a verification-rows-only plan to Complete without a redundant dispatch. Both `lazy-state.py` / `bug-state.py --test` smokes stay byte-identical on the no-phase-kind (legacy) path.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "phase_kind or retro_stale or finalize" -q` passes — specifically a test asserting that a PHASES fixture with a `design` phase + 3 trailing `corrective` phases all post-dating `RETRO_DONE.md` reports retro NOT-stale, and a fixture with a trailing `design` phase reports retro stale.

**Runtime Verification** *(checked on the next marked `/lazy-batch` run — NOT by the implementation agent):*
- [ ] A corrective-phase resolution loop (blocked-mcp-test → add `corrective` phase → re-validate) does NOT emit a `/retro` cycle between the add-phase and the re-validation; a `design`-phase add still does.
- [ ] An `/execute-plan` cycle that ticks all non-verification deliverables flips the plan to Complete in one pass (no redundant finalize re-dispatch).

**Prerequisites:**
- Phase 7 (Complete) — owns the run-lifecycle + the `__flip_plan_complete_stale__` pseudo-skill that deliverable 3 option (b) routes to.
- turn-routing-enforcement / lazy-pipeline-ergonomics (Complete) — own `parse_phases`, the Step-8 retro-staleness check, and the execute-plan finalization (`Step 4`) contract this phase modifies.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `parse_phases` exposes `phase_kind`; the retro-staleness predicate gains the design-vs-corrective filter.
- `user/scripts/lazy-state.py` (+ `bug-state.py` parity) — Step-8 staleness gate; the execute-plan finalization routing (option b, if chosen).
- `user/skills/add-phase/SKILL.md` — Step 4 phase-kind tagging (+ the blocked-resolution/investigation-dispatch consumers that set `corrective`).
- `user/skills/_components/sentinel-frontmatter.md` (+ the PHASES schema doc) — the `**Phase kind:**` per-phase marker.
- `user/skills/execute-plan/SKILL.md` — Step-4 finalization tightening (option a, if chosen).
- `repos/algobooth/.claude/skills/lazy-batch-retro/SKILL.md` — phase-kind-aware retro grading.
- `user/scripts/test_lazy_core.py` — coverage above.

**Testing Strategy:** Pure script/unit logic — `parse_phases` phase-kind extraction, the staleness predicate, and the finalization routing are all code-provable and unit-tested against injected PHASES/plan fixtures + a temp state dir (literal stale/not-stale + `run_marker`/plan-status assertions). No runtime-coupled smell (no sidecar/IPC/audio). The two Runtime-Verification rows are observational confirmations on the next marked run, not implementation-agent gates. `MCP runtime: not-required` (claude-config harness — consistent with this spec).

**Integration Notes for Next Phase:** Terminal phase. The `phase_kind` marker is now available to any future state-machine logic that wants to distinguish corrective from design work (e.g. a future "corrective-tail circuit breaker" could count only `corrective` phases). The finalization fix removes the last known redundant-dispatch class in the per-feature tail.

**Context from prior phases:** This phase is itself a `design` (non-corrective) phase — it is sourced from a retro recommendation, not a validation failure — so under its OWN deliverable-1 rule it would legitimately re-trigger a retro (it changes the harness's design surface). Pairs with Phase 7: that phase made the run-*lifecycle* enforcement mechanical; this one makes the per-feature *pipeline* efficient by teaching the state machine which phase adds actually warrant a re-audit. Both came from live `/lazy-batch` evidence (Phase 7 from the unilateral-stop incident; Phase 8 from the d7-multi-timbral cost measurement) — the harness is being hardened from its own run telemetry.
