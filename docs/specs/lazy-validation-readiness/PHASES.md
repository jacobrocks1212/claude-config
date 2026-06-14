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

**Status:** Not started

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

**Status:** Not started

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

**Status:** Not started

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

**Status:** Not started

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

**Status:** Not started

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

**Status:** Not started

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

**Integration Notes for Next Phase:** Terminal phase.
