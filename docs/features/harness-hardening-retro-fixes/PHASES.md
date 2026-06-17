# Implementation Phases — Harness-Hardening Retro Fixes + Anti-Overfit

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no MCP server and no Tauri runtime (`.claude/skill-config/capabilities.txt` declares NO `mcp`; per `docs/features/mcp-testing/SPEC.md` taxonomy this is the structurally-outside-MCP-reach class — pure Python/skill-prose harness work). Validation is the repo's own pytest + lint-skills + project-skills + parity-audit suite (see `.claude/skill-config/quality-gates.md`); the lazy Step 9 MCP gate is operator-exempt (`SKIP_MCP_TEST.md`, `granted_by: operator`).

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features, extracted from each upstream's PHASES.md during /spec-phases Step 1.5. Phase plans below MUST honor these; deviations require /realign-spec before implementation.

- **unified-pipeline-orchestrator (kind=hard, Complete):** Phase 1 here consumes three things this upstream shipped: (a) the **toolify framework** — `user/scripts/toolify-miner.py` (read-only, OFFLINE session-log miner — NOT an in-run hook), the deterministic-only bar (3-predicate AND-gate: deterministic AND repeated ≥2 runs AND token-heavy), and the candidate schema — all documented in `docs/features/unified-pipeline-orchestrator/toolify-bar.md`; (b) `toolify-bar.md` promotion-checklist **step 7**, which names `harness-hardening-retro-fixes` as the consumer that "may auto-initiate steps 1-4 as a `/spec-bug` when it detects a dance in-run" — harden-harness performs its OWN in-run dance-recurrence detection and spins off the same `/spec-bug` the offline miner's checklist describes; it does NOT invoke the offline miner mid-cycle; (c) the `--type bug` front-enqueue path in `_components/adhoc-enqueue.md` (routes to `bug-state.py --enqueue-adhoc` → `docs/bugs/queue.json` + `docs/bugs/<id>/`), which the spin-off action (Phase 1) uses. The deterministic-only bar boundary is respected: judgment steps (`--verify-ledger`, recovery dispatch) are explicitly below-bar — the over-fit "repeated deterministic dance" signal does not classify judgment steps as toolifiable. (The `-followups` queue-trim + `mcp-tests` symlink fixes are upstream-owned and correctly NOT duplicated here — SPEC Executive Summary cross-references them.)

---

### Phase 1: Anti-overfit engine in `/harden-harness`

**Scope:** Extend `/harden-harness` Step 3 ("Act by decision class") so the mechanical fix ALWAYS lands first (run never blocked), then an over-fit detector decides whether to ALSO spin off a generalized `/spec` (structural redesign / new capability) or `/spec-bug` (defect/regression / toolify-this-dance) via the `adhoc-enqueue` protocol, front-enqueued. Surface both the patch and the spin-off in the HARDENING.md round + a `PushNotification`. This is skill-prose + component work (no state-machine code change); the spin-off mechanism reuses the already-shipped `adhoc-enqueue.md --type bug` path.

**Deliverables:**
- [ ] Add an "over-fit detector" subsection to `user/skills/harden-harness/SKILL.md` Step 3, enumerating the four smell signals (any one trips a spin-off): (1) the fix adds a literal phrase/string to a matcher (regex / header list / keyword set) — fitting to observed data, not structure; (2) the root-cause class has recurred ≥2 times in the hardening log (signature match against prior rounds); (3) the agent self-flags the fix as narrow ("this will gap again on the next variant"); (4) the friction is a repeated deterministic dance (toolify candidate per the framework's promotion checklist — in-run detection, NOT an offline-miner call).
- [ ] Document the **recurrence threshold** resolved in this cycle (Open Question 1): phrase-match patches spin off on FIRST occurrence; non-phrase recurrence needs ≥2. Make the threshold explicit in the over-fit detector prose.
- [ ] Document the **generalization bound** discipline ("most general within reason"): the spun-off spec targets the smallest class that subsumes the observed instance + near neighbors — NOT a speculative rewrite; the problem statement MUST cite the concrete instance(s) as evidence and name the class boundary explicitly.
- [ ] Add the **spin-off action** prose: compose a generalized problem statement (the class, not the instance), then invoke `/spec` or `/spec-bug` via `adhoc-enqueue` front-enqueued. Choice rule: structural redesigns + new capabilities → `/spec`; defects/regressions + toolify-this-dance → `/spec-bug`. Reference `_components/adhoc-enqueue.md`'s `--type bug` path for the bug-pipeline route.
- [ ] Add the **no-double-blocking** + **self-recursion-guard-preserved** notes: the instance is already fixed so the spin-off never blocks the current run (queued work, surfaced via HARDENING.md + `PushNotification`); a spin-off is a `/spec`/`/spec-bug` enqueue (NOT a recursive hardening dispatch) so it does not trip the existing depth-1 hardening guard.
- [ ] Extend the Step 4 HARDENING.md round template to record BOTH the patch AND the spin-off (a `harden(spinoff):` note line + the front-enqueued item id) when the smell trips; extend the Step "Return format" with a `spinoff` field (id + reason, or `none`).
- [ ] Wire the toolify-candidate trigger to the upstream framework's deterministic-only bar + promotion checklist (cite `docs/features/unified-pipeline-orchestrator/toolify-bar.md` step 7); state explicitly that harden-harness does its own in-run dance-recurrence detection and spins off a `/spec-bug` per the checklist — it does NOT shell `toolify-miner.py` mid-cycle.
- [ ] Tests: in `user/scripts/test_lazy_core.py`, add a deterministic over-fit-detector fixture suite (registered in `_TESTS` — see Phase 5 guard) asserting: (a) a phrase-match fix yields a spin-off decision on first occurrence; (b) a structural (non-phrase) fix with no prior recurrence yields NO spin-off; (c) a non-phrase fix whose class recurred ≥2 in a synthetic hardening-log fixture yields a spin-off; (d) a toolify-dance signal yields a `/spec-bug` spin-off. (If the detector logic is purely prose with no extractable helper, instead add a `lint-skills.py`-checkable assertion that the four signals + threshold + generalization-bound + spin-off-choice-rule strings are present in the SKILL.md — a presence gate, since this repo's MCP gate is operator-exempt and the behavior is LLM-executed prose.)

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py --check-projected --check-capabilities` passes AND `grep -c` confirms the four over-fit smell signals, the recurrence threshold, the generalization bound, and the spin-off `/spec` vs `/spec-bug` choice rule are all present in `harden-harness/SKILL.md` Step 3. If a Python over-fit-decision helper is extracted, `python user/scripts/test_lazy_core.py` shows the new fixtures green; otherwise the presence gate is the verifiable proof.

**Prerequisites:** None (first phase). Consumes the already-Complete `unified-pipeline-orchestrator` toolify framework + `adhoc-enqueue.md --type bug` path (read-only dependency — both already on disk).

**Files likely modified:**
- `user/skills/harden-harness/SKILL.md` — Step 3 over-fit detector + spin-off action; Step 4 round template; Return-format `spinoff` field.
- `user/scripts/test_lazy_core.py` — over-fit-detector fixtures (or presence assertions), registered in `_TESTS`.
- (read-only references — NOT modified) `user/skills/_components/adhoc-enqueue.md`, `docs/features/unified-pipeline-orchestrator/toolify-bar.md`.

**Testing Strategy:**
Verified in isolation by the repo's Python suite: `python user/scripts/test_lazy_core.py` (new over-fit fixtures) + `python user/scripts/lint-skills.py --check-projected --check-capabilities` (skill prose well-formed, no broken injections) + `python user/scripts/project-skills.py` (re-expansion clean). No runtime — the behavior is LLM-executed prose gated by the presence/decision tests.

**Integration Notes for Next Phase:**
- The HARDENING.md round template extension (patch + spin-off) and the `spinoff` Return field are the surfacing contract — later observability work (if any) keys off them.
- The spin-off mechanism is the consumer of `adhoc-enqueue.md --type bug`; do NOT re-implement enqueue logic — that path is upstream-owned and shipped.
- This phase is the engine that auto-identifies toolification candidates, completing the loop `unified-pipeline-orchestrator` left open at `toolify-bar.md` step 7.

---

### Phase 2: Verification-section detector — structural canonical marker

**Scope:** Replace the growing free-text-matching `_VERIFICATION_SECTION_RE` (in `user/scripts/lazy_core.py`) with a structural canonical marker. Producers (`/spec-phases` via `_components/phases-runtime-verification.md`, and `/blocked-resolution` via `_components/blocked-resolution.md`) emit ONE canonical verification-only marker; the detector keys off the marker, with the legacy regex reduced to a deprecation shim that warns when it WOULD have matched but the marker is absent (surfacing un-migrated producers). The canonical marker string lives in ONE source of truth (a single Python constant in `lazy_core.py`, referenced by the component prose), with a lockstep test asserting producers and detector agree.

**Deliverables:**
- [ ] Define the canonical marker as a single Python constant in `user/scripts/lazy_core.py` (e.g. `_VERIFICATION_ONLY_MARKER = "<!-- verification-only -->"`) — the SSOT. Resolve Open Question 2 (per-row HTML-comment marker vs single canonical subsection header) toward the per-row `<!-- verification-only -->` comment form, since it is the most robustly machine-detectable in `remaining_unchecked_are_verification_only` (a row carries its own exemption marker — no heading-scope bookkeeping) and survives novel subsection phrasing by construction. ⚖ if `check-docs-consistency.ts` (AlgoBooth) cannot validate the comment form cleanly, fall back to the canonical subsection-header form — document which was chosen and why in the constant's docstring.
- [ ] Rekey `remaining_unchecked_are_verification_only(phases_text)` to treat a `- [ ]` row as verification-exempt when the row (or its enclosing subsection) carries the canonical marker, INDEPENDENT of the bold-header/heading free-text. Preserve the existing fence-awareness and Superseded-phase handling.
- [ ] Reduce `_VERIFICATION_SECTION_RE` to a **deprecation shim**: keep the regex but, when it matches a header while the canonical marker is ABSENT from that subsection's rows, surface a diagnostic (append to the `_DIAGNOSTICS` list / emit a warning string) naming the un-migrated producer — do NOT silently pass. The shim still exempts the rows (no regression for un-migrated PHASES.md) but makes the gap visible.
- [ ] Update `_components/phases-runtime-verification.md` so `/spec-phases`-authored verification rows emit the canonical marker (reference the SSOT constant by value, with a note pointing at `lazy_core.py`).
- [ ] Update `_components/blocked-resolution.md` so `/blocked-resolution`-authored verification / full-chain-seam-audit rows emit the canonical marker.
- [ ] Tests (registered in `_TESTS`): (a) a verification subsection with a NEVER-BEFORE-SEEN header text + the marker present → gate passes via marker, no regex growth needed; (b) a verification subsection WITHOUT the marker (un-migrated) → deprecation shim warns (diagnostic emitted), does NOT silently pass clean; (c) lockstep test asserting the marker string referenced in the component prose equals the `lazy_core.py` SSOT constant.

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` shows the novel-header-with-marker fixture passing and the un-migrated-no-marker fixture emitting the deprecation diagnostic; the lockstep test confirms producer prose and detector constant agree.

**Prerequisites:** None (independent of Phase 1). Touches `lazy_core.py` — run BOTH `lazy-state.py --test` and `bug-state.py --test` after (shared import surface, per quality-gates.md "Lazy skill-family changes").

**Files likely modified:**
- `user/scripts/lazy_core.py` — `_VERIFICATION_ONLY_MARKER` SSOT constant; rekey `remaining_unchecked_are_verification_only`; demote `_VERIFICATION_SECTION_RE` to a warning shim.
- `user/skills/_components/phases-runtime-verification.md` — emit the canonical marker on verification rows.
- `user/skills/_components/blocked-resolution.md` — emit the canonical marker on verification / seam-audit rows.
- `user/scripts/test_lazy_core.py` — novel-header, un-migrated-warning, and lockstep fixtures (registered in `_TESTS`).

**Testing Strategy:**
Hermetic Python characterization tests over `remaining_unchecked_are_verification_only` with synthetic PHASES.md fixtures (novel header + marker; novel header + no marker; mixed). The lockstep test reads the component prose + the `lazy_core.py` constant and asserts string equality. Full lazy-family gate (`test_lazy_core.py` + `lazy-state.py --test` + `bug-state.py --test` + `lazy_parity_audit.py --report`) because `lazy_core.py` is shared.

**Integration Notes for Next Phase:**
- The SSOT constant is the contract — never re-hardcode the marker string in a producer; always reference the `lazy_core.py` value.
- If AlgoBooth's `check-docs-consistency.ts` `SENTINEL_SCHEMAS` needs to recognize the marker, that lockstep is the responsibility of whoever next edits that file (flag in the round if so) — but the marker is a row annotation, not a sentinel, so it likely does not enter `SENTINEL_SCHEMAS`.
- The deprecation shim's diagnostic is the migration tracker; a future cycle that retires the regex entirely waits until the shim has stopped firing across all live PHASES.md.

---

### Phase 3: `plan_complete` ledger fix (plan-less / realign-only features)

**Scope:** Fix `verify_ledger` in `user/scripts/lazy_core.py` so the feature-level (no `plan_path`) `plan_complete` check distinguishes *absent-by-design* (a plan-less / realign-plan-only feature has no implementation plan and never needed one) from *incomplete* (an implementation plan exists but is not Complete). Today `plan_complete = any_complete AND no_incomplete` returns False for a feature with NO implementation plan at all, producing a false-alarm `plan_complete:false` and a benign-but-noisy recovery chase.

**Deliverables:**
- [ ] In `verify_ledger`'s feature-level branch (`scoped is False`), treat "no implementation plan present (and none required)" as NOT-a-failure: when `find_implementation_plans(spec_path)` returns zero incomplete plans AND `_has_any_complete_plan` is False AND there is genuinely no implementation plan on disk (only `realign-*.md` / `retro-*.md` / no plans at all), set `plan_complete = True` (absent-by-design) rather than False. Preserve the existing True/False behavior for features that DO have implementation plans (≥1 complete + zero incomplete → True; any incomplete → False).
- [ ] Verify the plan-SCOPED branch (`scoped is True`, `--plan <part>`) is unaffected — it reads the named plan's own frontmatter status and is correct as-is; the fix is feature-level only.
- [ ] Add a diagnostic so the operator can see the absent-by-design path fired (e.g. a `_DIAGNOSTICS` note "plan_complete: no implementation plan required (absent-by-design)" — additive, never gates).
- [ ] Tests (registered in `_TESTS`): (a) a plan-less feature (PHASES.md present, all deliverables checked, NO `plans/*.md` implementation plan) → `verify_ledger(...)` returns `plan_complete:true` and `ok:true` (given clean tree / head match stubbed); (b) a realign-only feature (only `plans/realign-*.md` present, no implementation plan) → `plan_complete:true`; (c) regression guard: a feature WITH an incomplete implementation plan still returns `plan_complete:false` (the fix must not vacuously pass real incomplete plans).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` shows the plan-less and realign-only fixtures returning `plan_complete:true` while the incomplete-plan regression fixture still returns `plan_complete:false`.

**Prerequisites:** None (independent). Touches `lazy_core.py` — run the full lazy-family gate after.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `verify_ledger` feature-level `plan_complete` branch + diagnostic.
- `user/scripts/test_lazy_core.py` — plan-less, realign-only, and incomplete-plan-regression fixtures (registered in `_TESTS`).

**Testing Strategy:**
Hermetic `verify_ledger` characterization tests with temp-dir feature fixtures (PHASES.md + varying plans/ contents), stubbing the git checks (`clean_tree` / `head_matches_origin`) where the existing test harness already does so. Full lazy-family gate because `lazy_core.py` is shared.

**Integration Notes for Next Phase:**
- `verify_ledger` is the SSOT for the completion-ledger gate (`--verify-ledger`); the four-check ordering (`clean_tree → head_matches_origin → plan_complete → deliverables_done`) and the return shape are unchanged — only the `plan_complete` truth value for the absent-by-design case changes.
- Do NOT conflate this with `deliverables_done` (Phase 2's territory) — `plan_complete` is about plan-file existence/status, `deliverables_done` is about unchecked rows.

---

### Phase 4: mcp-test haiku-tier re-scope with script-derived routing signal

**Scope:** Re-scope the mcp-test haiku tier so haiku handles only ready-to-run YAML happy paths, and scenario-authoring / first-run `.md`→YAML conversion / diagnosis cycles route to Sonnet **by default** — driven by a SCRIPT-derived signal, not a per-run orchestrator override. Add a script-observable routing helper (the natural home is `user/scripts/surface_resolver.py`, which already lints scenarios and is part of the repo's pytest suite) that, given a scenario reference + optional prior verdict, returns the tier the cycle should use. Update `mcp-test/SKILL.md` (AlgoBooth-scoped) prose to consult the signal instead of relying on an orchestrator override.

**Deliverables:**
- [ ] Enumerate (Open Question 3) the exact script-observable conditions that force Sonnet: (1) the resolved scenario is a legacy `.md` and has NO converted `corpus/live/*.yaml` counterpart (first-run conversion needed); (2) the prior verdict was non-definitive (`uncertain` / unrepaired `harness` / `genuine`-after-heal) per a recorded prior `verdict.json` / `MCP_TEST_RESULTS.md`; (3) no scenario exists at all (scenario-authoring needed). Ready-to-run converted YAML with no adverse prior verdict → haiku.
- [ ] Add a routing helper to `user/scripts/surface_resolver.py` (e.g. `route_mcp_test_tier(scenario_path, prior_verdict=None, yaml_exists=None) -> "haiku" | "sonnet"`) implementing those conditions deterministically — pure function, no I/O beyond an optional existence check, so it is hermetically testable.
- [ ] Update `repos/algobooth/.claude/skills/mcp-test/SKILL.md` "Model tier" section so the tier is chosen by the script signal (cite the helper), and the conditions are documented in prose; remove/retire the reliance on an orchestrator override for the diagnosis/authoring case. Note explicitly that a `.md`-unconverted or prior-non-definitive scenario routes to Sonnet WITHOUT a human/orchestrator call.
- [ ] Tests in `user/scripts/test_surface_resolver.py` (its own runner) covering each routing condition: ready YAML + clean prior → haiku; `.md` unconverted → sonnet; prior `uncertain` verdict → sonnet; no scenario → sonnet.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_surface_resolver.py -q` (or its in-file runner) shows `route_mcp_test_tier` returning `sonnet` for the unconverted-`.md`, prior-non-definitive, and no-scenario cases and `haiku` for the ready-YAML-clean-prior case.

**Prerequisites:** None (independent). The `mcp-test/SKILL.md` edit is AlgoBooth-scoped prose; the helper + tests are in `user/scripts/`.

**Files likely modified:**
- `user/scripts/surface_resolver.py` — `route_mcp_test_tier` deterministic routing helper.
- `user/scripts/test_surface_resolver.py` — routing-condition fixtures.
- `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — Model-tier section consults the script signal; document the conditions; retire the orchestrator-override reliance.

**Testing Strategy:**
Hermetic pure-function tests of `route_mcp_test_tier` over each enumerated condition (no live MCP — the routing decision is computed from scenario shape + prior verdict, both script-observable). `python -m pytest user/scripts/ -q` covers the surface_resolver suite; `lint-skills.py` + `project-skills.py` confirm the SKILL.md prose is well-formed.

**Integration Notes for Next Phase:**
- The routing helper is script-derived state — the orchestrator/skill READS it, never overrides it per-run; that is the whole point of the re-scope (eliminating the wasted-cycle + sonnet-override-finds-real-bug pattern from `98d00c1`).
- `mcp-test/SKILL.md` is repo-scoped (AlgoBooth) and not part of a coupled pair, so no mirroring is required — but it IS picked up by `project-skills.py` per-repo projection; re-run it after editing.

---

### Phase 5: Dead-coverage guard in the gate suite

**Scope:** Add a guard that fails (or warns loudly in gates) when a `def test_*` function exists in `user/scripts/test_lazy_core.py` (the manually-registered suite) but is NOT collected by the runner's `_TESTS` registry — so a hardening round cannot land "tests" that never execute (the Round 24 dead-coverage incident: regression tests authored but never appended to `_TESTS`, caught only by luck in Round 25). This is itself an anti-overfit safeguard — it makes the *evidence* for a fix real. Generalize minimally to any manually-registered test module in `user/scripts/` that uses the `_TESTS`-style registry.

**Deliverables:**
- [ ] Add a dead-coverage guard: a function (in `test_lazy_core.py`'s own suite, OR a small standalone `user/scripts/test_coverage_guard.py`) that AST-parses (or reliably greps) `test_lazy_core.py` for every top-level `def test_*` name, compares against the set of names registered in `_TESTS`, and FAILS naming any orphaned (defined-but-unregistered) test function. Choose the AST approach (`ast.parse` over the module source) for robustness over a regex.
- [ ] Wire the guard so it runs as part of the standard gate: register it in `_TESTS` itself (self-checking — the guard is collected and run by the same harness it guards) so `python user/scripts/test_lazy_core.py` fails on an orphan. ⚖ policy: guard scope (this-module vs all script test modules) → cover `test_lazy_core.py` (the incident's module + the suite Phases 1-3 extend) as the load-bearing case; note the generalization seam to other `_TESTS`-style modules in a docstring rather than speculatively scanning every file.
- [ ] Surface the guard in `.claude/skill-config/quality-gates.md` (and/or `harden-harness/SKILL.md` Step 3 gate list) so a hardening round's gate run includes it — making "tests that never execute" impossible to land silently.
- [ ] Tests: (a) a positive test confirming the guard PASSES on the current (correctly-registered) suite; (b) a negative fixture (a synthetic module text with a `def test_orphan` not in its `_TESTS`) confirming the guard DETECTS and reports the orphan by name.

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` runs the dead-coverage guard as one of its `_TESTS` entries and passes (all `def test_*` registered); a hand-constructed negative fixture proves the guard reports an orphan by name. Bonus reachability proof: this phase's OWN Phases 1-4 fixtures are confirmed registered (the guard would catch them if they were orphaned).

**Prerequisites:** Best run LAST (it validates that Phases 1-4 actually registered their new tests in `_TESTS` — a built-in cross-check). Functionally independent, but ordering it last makes it close the loop on the preceding phases' test registration.

**Files likely modified:**
- `user/scripts/test_lazy_core.py` — dead-coverage guard function + its `_TESTS` registration (self-checking).
- (optionally) `user/scripts/test_coverage_guard.py` — standalone guard if kept separate.
- `.claude/skill-config/quality-gates.md` — document the guard in the gate-determination list.
- (optionally) `user/skills/harden-harness/SKILL.md` — add the guard to Step 3's mandatory gate commands.

**Testing Strategy:**
The guard IS a test — it AST-parses the suite module and asserts every `test_*` def is in `_TESTS`. Verified by (a) running the full suite green (guard passes on the real, fully-registered suite) and (b) a negative-fixture unit test feeding synthetic module source with an unregistered `def test_orphan` and asserting the guard flags it by name. No runtime, no MCP.

**Integration Notes for Next Phase:**
- (Terminal phase.) This guard is the standing anti-overfit safeguard for the harness's own test evidence; future hardening rounds that add tests to `test_lazy_core.py` are now mechanically prevented from leaving them unregistered.
- Completion (gate-owned): the top-level PHASES `**Status:**` flip to Complete, the `COMPLETED.md` receipt, the ROADMAP strike, and queue trim are owned by the `__mark_complete__` gate — NOT authored as deliverable rows here.

---

## Completion (gate-owned)

Per `_components/phases-runtime-verification.md`: the SPEC.md/PHASES.md top-level `**Status:**` flips to Complete, the `COMPLETED.md` receipt write, the ROADMAP completion mark, and `queue.json` trim are owned EXCLUSIVELY by the `__mark_complete__` gate (which fires after the validation tail). They are NOT authored as `- [ ]` deliverable rows in any phase above. This repo's MCP Step-9 gate is operator-exempt (`SKIP_MCP_TEST.md`, `granted_by: operator`, `spec_class: untestable-via-mcp`, reason → the passing quality gates) per `.claude/skill-config/quality-gates.md`; validation here is the full Python test + lint suite.
