# Implementation Phases — Lazy-Pipeline Ergonomics (post-e076ed30 retro refinements)

> Phases for [`SPEC.md`](./SPEC.md)

**Original phase count:** 3

**MCP runtime:** not-required — targets the claude-config harness (state scripts, validate-deny guard, orchestrator-voice contract, lazy-batch-retro grader); there is no AlgoBooth app surface. Verification is via `test_lazy_core.py`, `test_hooks.py`, both state-script `--test` smokes, `lint-skills.py`, and a next-marked-run live check — the standalone-tooling class with no app integration per docs/features/mcp-testing/SPEC.md.

---

## Touchpoint Summary

The AlgoBooth `npm run audit:touchpoints` gate is **SKIPPED** — these touchpoints live in claude-config, which has no package.json or audit tooling.

**Existing files to be modified:**
- `user/scripts/lazy_core.py` (registry schema for F1b; `update_repeat_counts` debounce for F2)
- `user/scripts/lazy_guard.py` (deny-reason wording for F1a; auto-readmit branch for F1b)
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` (coupled-pair mirror where shared helpers change)
- `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py`
- `user/skills/_components/orchestrator-voice.md` (F3 glyph)
- `repos/algobooth/.claude/skills/lazy-batch-retro/SKILL.md` (F3 R-V grader mirror)
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (F2 behavioral note: probe once; `--repeat-count-peek` for inspection)

This repo has no LOC-gate, so no Phase 0 decomposition is required.

---

## Validated Assumptions

Confirmed at source level during planning (2026-06-13). These changes are pure script logic + doc edits — none carries a runtime-coupled smell (no cross-boundary data shape, no sidecar/IPC/audio observable); the one runtime-observed fact (F2's double-probe inflation) was witnessed in the live retro.

| # | assumption | how-confirmed | evidence |
|---|---|---|---|
| A1 | `lazy_guard.py` denies a suffix-appended cycle_prompt because it hashes the FULL prompt (`prompt_sha256`) and `lookup_emission` returns None on miss → falls through to `_default_deny_reason()` | grep (code-provable; pure string/hash logic) | `lazy_guard.py:369` (`prompt_sha256`), `:372` (`lookup_emission`), `:430` (default deny) |
| A2 | The registry stores only `prompt_sha256`, NOT prompt text — so prefix/suffix matching (F1b) requires a registry schema addition | grep (code-provable) | `lazy_core.register_emission` (lazy_core.py:4264) appends `{nonce, prompt_sha256, emitted_at, class, item_id, consumed}`; no text field |
| A3 | `step_repeat_count` is HEAD-blind and increments on any unchanged `(feature_id, current_step)` regardless of intervening commits OR dispatches | grep (code-provable; deterministic) | `lazy_core.update_repeat_counts` lazy_core.py:2634–2641 |
| A4 | The double-probe inflated `step_repeat_count` and tripped a false `LOOP DETECTED` while `repeat_count` stayed low / HEAD advanced (i.e. no real stall) | runtime (observed in the live retro) | AlgoBooth `LAZY_BATCH_REVIEW_2026-06-13_overview.md` cross-cutting finding #2 (7 benign LOOP DETECTED blocks) |
| A5 | The guard consumes a registry nonce on every ALLOW (so a registry consume-count delta is a sound "did a dispatch happen between probes" oracle for F2's debounce) | grep (code-provable) | `lazy_guard.py:380` `consume_nonce(...)` on the first-time allow path |
| A6 | `orchestrator-voice.md` reserves `⏸` for park (T5) and is runtime-referenced-by-path (the source edit is the single authoritative copy) | grep | turn-routing PHASES Phase 7 Implementation Notes ("orchestrator-voice.md … runtime-referenced-by-path") |
| A7 | `--test` baselines are byte-pinned; all new behavior must be marker-gated or otherwise default-invisible | grep | turn-routing A10; user/scripts/CLAUDE.md Testing section |

---

## Cross-feature Integration Notes

Substantive upstream facts from turn-routing-enforcement (Complete) these phases consume:
- `prompt_sha256(prompt)` normalizes CRLF→LF (+ NFC + per-line trailing-whitespace strip, Phase 7) before hashing — F1b's prefix match MUST use the SAME `normalize_prompt_for_hash` so a suffix is detected after identical normalization.
- The deny path is `lazy_guard.py` → `_deny_and_ledger(_default_deny_reason(), …)`; `_CORRECTIVE_RECIPE` (lazy_guard.py:130) is the wording surface for F1a. `_hardening_cap_deny_reason()` must be left untouched (depth-1 cap).
- Registry entries are ephemeral (ring-cap ~64, 30-min TTL) — storing the normalized prompt text on each entry (F1b) is size-safe.
- `update_repeat_counts` peek discipline + `_atomic_write` are the persistence pattern; the debounce (F2) must persist whatever "last consume-count seen" it keys on inside the SAME signature file, additively (legacy-file-tolerant, like the `head`/`step_*` migrations).
- Coupled-pair mirroring (lazy-batch ↔ lazy-bug-batch ↔ lazy-batch-cloud) is a hard gate; `test_lazy_core.py` is a custom harness (run `python3 user/scripts/test_lazy_core.py`); NEVER regenerate `--test` baselines.

---

## Phases

### Phase 1: Validate-deny recovery ergonomics (F1)

**Scope:** Make the common validate-deny accident (a suffix appended to a script-emitted `cycle_prompt`) cheap to recover from. Two deliverables of escalating commitment: F1a (deny-reason names the sanctioned customization tools — pure win) and F1b (auto-readmit a pure-suffix superset — carries a flagged integrity tradeoff, decided at implementation).

**Deliverables:**
- [ ] **F1a — deny-reason ergonomics:** extend `_CORRECTIVE_RECIPE` (`lazy_guard.py`) so the `permissionDecisionReason` on a default (non-hardening) deny names the exact sanctioned customization path — `--context KEY=VALUE` for per-dispatch token bindings and `--emit-dispatch <class>` for ad-hoc classes — and states explicitly "never append to or edit the emitted prompt; re-probe and dispatch verbatim." Preserve every existing recipe substring the Phase 6/7 tests byte-match (add, don't replace).
- [ ] **F1b — pure-suffix auto-readmit (tradeoff-flagged):** add a registry-text field (`register_emission` stores the `normalize_prompt_for_hash`-normalized prompt text on each entry — A2) and a guard branch, evaluated BEFORE the default deny, that ALLOWS when the dispatched normalized prompt is a pure trailing-suffix superset of an *unconsumed, fresh, `class == "cycle"`* entry: `dispatched_norm.startswith(entry_norm)` with non-empty remainder. On auto-readmit: consume that entry's nonce, bind-on-allow (Phase 9 parity), and write an explicit `auto_readmit: true` event to the deny ledger (or a sibling telemetry line) so it is auditable and retro-gradable — NEVER silent. Excluded: hardening-class entries (depth cap untouched), any in-body edit (only a pure suffix qualifies → everything else still denies).
- [ ] **Open decision (record in Implementation Notes):** whether to ship F1b at all. It softens turn-routing's "hand-composed prompts are unexecutable" guarantee (a trailing suffix is read last and can override the prompt's tail clauses). If judged too costly, ship F1a alone and mark F1b superseded-by-decision. Default recommendation: ship F1b scoped as above (cycle-class, pure-suffix, audited).
- [ ] Tests (`test_lazy_core.py` + `test_hooks.py`): deny reason contains the `--context` / `--emit-dispatch` / "dispatch verbatim" substrings AND all preexisting recipe substrings; auto-readmit allows a suffix-appended cycle prompt + consumes the nonce + emits the `auto_readmit` event; in-body edit still denies; hardening-class suffix never auto-readmits; pipe-test through `lazy-dispatch-guard.sh`. ALL standing gates green, `--test` baselines byte-identical.

**Minimum Verifiable Behavior:** Through the real `lazy-dispatch-guard.sh` (pipe-test, marked run): a dispatch whose prompt = a registered cycle prompt + "\n\nORCHESTRATOR NOTE: …" is ALLOWED with `auto_readmit: true` in the ledger and the nonce consumed; the SAME prompt with a word changed mid-body is DENIED with a reason containing `--context` and `--emit-dispatch`.

**Runtime Verification** *(next marked run — NOT the implementation agent):*
- [ ] A live suffix-append accident auto-readmits (ledger shows `auto_readmit: true`) instead of forcing a hardening round — OR (if F1b dropped) the next deny reason names the `--context`/`--emit-dispatch` path.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification row above stands in.

**Prerequisites:** None (extends existing turn-routing surfaces).

**Files likely modified:** `user/scripts/lazy_guard.py`, `user/scripts/lazy_core.py` (registry text field, F1b), `user/scripts/test_lazy_core.py`, `user/scripts/test_hooks.py`.

**Testing Strategy:** `python3 test_lazy_core.py` (registry-text + auto-readmit unit coverage) + `python3 test_hooks.py` (guard pipe-test, both platforms) + both `--test` smokes + `lint-skills.py`. Ground truth: literal substring assertions on the deny reason; ledger `auto_readmit` flag presence; nonce `consumed: true` after auto-readmit. Boundary coverage: pure-suffix allow, in-body-edit deny, hardening-class suffix deny, no-marker fast-path unchanged.

**Integration Notes for Next Phase:** F1b's registry-text field is additive — Phase 2's debounce does not depend on it. The `auto_readmit` ledger event format should match the existing deny-ledger JSONL shape so retro graders read one stream.

**Context from prior phases (turn-routing-enforcement):** reuse `normalize_prompt_for_hash` for the prefix match (identical normalization is load-bearing); never weaken `_hardening_cap_deny_reason`; registry entries are ephemeral so storing text is safe; fail-open discipline — an auto-readmit-path error must fall through to the normal deny, never to a spurious allow.

---

### Phase 2: `step_repeat_count` double-probe debounce (F2)

**Scope:** Stop a re-read (two advancing probes for the same route with no dispatch between them) from inflating the HEAD-blind `step_repeat_count` and tripping a false `LOOP DETECTED`. A genuine oscillation (a real dispatch between repeats) must still trip.

**Deliverables:**
- [ ] **Debounce in `lazy_core.update_repeat_counts`:** do not increment `step_count` when the step signature is unchanged from the immediately-preceding advancing probe AND no dispatch occurred between the two probes. Oracle for "a dispatch occurred": the registry consume-count delta (A5) when a run marker is present — persist the last-seen consume-count in the signature file additively (legacy-tolerant, like the `head`/`step_*` migrations); if it is unchanged since the prior probe, this probe is a re-read → hold `step_count`. **Marker-gated:** when no marker is present (no registry), behavior is unchanged so `--test` baselines stay byte-identical.
- [ ] **Behavioral note (×3 mirrored SKILLs):** Step 1a prose — probe ONCE with the dispatch-bound `--emit-prompt`; use `--repeat-count-peek` for any inspection probe so only the single dispatch-bound probe advances the streaks. (Defense in depth alongside the script debounce.)
- [ ] Tests (`test_lazy_core.py`): two identical advancing probes with no consume between → `step_repeat_count` held (not incremented); two identical probes WITH a consume between → incremented (real oscillation still trips); peek probe never advances (unchanged); legacy signature file (no consume-count key) tolerated; no-marker path byte-identical. `--test` baselines byte-identical.

**Minimum Verifiable Behavior:** Hermetic `LAZY_STATE_DIR` fixture: `update_repeat_counts` called twice with the same `(feature_id, current_step)` and no registry-consume delta returns `step_repeat_count == 1` both times; with a consume recorded between the two calls it returns `1` then `2`.

**Runtime Verification** *(next marked run):*
- [ ] A double-probe of the same route in a live run does NOT emit a `LOOP DETECTED` block; a genuine same-step oscillation still does.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; live verification row above stands in.

**Prerequisites:** None (Phase 1 independent). Sequenced after Phase 1 for review linearity only.

**Files likely modified:** `user/scripts/lazy_core.py` (`update_repeat_counts`), `user/scripts/test_lazy_core.py`, `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (behavioral note).

**Testing Strategy:** `python3 test_lazy_core.py` Phase-2 section (hermetic fixture) + both `--test` smokes + `lint-skills.py`. Ground truth: the MVB count sequence; no-marker output byte-identical. Boundary coverage: consume-delta present/absent, peek unchanged, legacy-file migration, marker-absent unchanged.

**Integration Notes for Next Phase:** The signature-file schema gains one additive key — document it in the `update_repeat_counts` docstring alongside the existing `head`/`step_*` migration notes.

**Context from prior phases (lazy-hardening Phase 10 / turn-routing):** `step_repeat_count` is deliberately HEAD-blind to catch commit-per-iteration oscillation — the debounce must NOT reintroduce a HEAD reset (that was rejected for a reason); it keys on *dispatch occurrence*, not commits. Mirror the `peek`/`_atomic_write` discipline; legacy state files must read what they can (no hard schema dependency).

---

### Phase 3: Runtime-reboot glyph disambiguation (F3)

**Scope:** Give runtime-reboot / blocking-foreground-wait status zones their own glyph so `⏸` is reserved for park (T5), and teach the retro grader the distinction so the overload stops reading as a deviation. Doc-only.

**Deliverables:**
- [ ] **`orchestrator-voice.md`:** introduce a distinct glyph (proposed `⟳`) for runtime-reboot / blocking-foreground-wait status zones (a sanctioned T6 rich-zone marker), and state that `⏸` is reserved EXCLUSIVELY for park (T5). Add the new glyph to the sanctioned-output marker grammar so the Zero-Text rule still recognizes it.
- [ ] **`lazy-batch-retro` R-V grader:** mirror the distinction — the R-V-3 check recognizes the runtime-reboot glyph as a legitimate status zone (not a `⏸`-overload advisory) and flags `⏸` used for a non-park wait as the (minor) deviation instead.
- [ ] Tests: `lint-skills.py --check-projected --check-capabilities` clean (the voice component projects into every consuming skill); a focused assertion or doc-corpus check if one exists for marker grammar. No state-script behavior changes → both `--test` smokes byte-identical by construction.

**Minimum Verifiable Behavior:** `lint-skills.py --check-projected --check-capabilities` exits 0 with the new glyph in the marker grammar; a grep of `orchestrator-voice.md` shows `⏸` described as park-only and the runtime-reboot glyph defined as a distinct T6 zone.

**Runtime Verification** *(next marked run):*
- [ ] A runtime-reboot status zone in a live run uses the new glyph; the next `/lazy-batch-retro` grades R-V-3 with no `⏸`-overload advisory.

**MCP Integration Test Assertions:** N/A — no MCP runtime in claude-config; doc-only.

**Prerequisites:** None.

**Files likely modified:** `user/skills/_components/orchestrator-voice.md`, `repos/algobooth/.claude/skills/lazy-batch-retro/SKILL.md`.

**Testing Strategy:** `lint-skills.py` full flags; manual grep confirmation of the glyph grammar + R-V wording. No script tests (doc-only) — confirm `--test` smokes untouched.

**Integration Notes for Next Phase:** Final phase. The new glyph becomes observable evidence in future retro R-V grading.

**Context from prior phases (turn-routing Phase 7):** `orchestrator-voice.md` is runtime-referenced-by-path (not `!cat`-embedded), so the source edit is the single authoritative copy — no projection regen needed beyond `lint-skills.py`.

---

## Completion (gate-owned)

SPEC/PHASES `**Status:**` flips and any receipt are the pipeline gate's action, not checkboxes here.
