# Implementation Phases — By-reference dispatch `updatedInput` unapplied on Agent dispatch

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure claude-config harness change (state-script CLI + `lazy_core` reader + dispatch-template/skill prose + Python `--test`/pytest coverage); no Tauri/MCP app surface exists in this repo (mcp-testing SPEC untestable-class: "no app integration").

## Fix context (operator-locked — read before planning against symptoms)

The investigation concluded and the operator locked the fix on 2026-07-18 (records:
`SPEC.md` → "Fix scope — RESOLVED"; `NEEDS_INPUT_RESOLVED_2026-07-18.md` → "## Resolution (final —
fix fork)"; `PLATFORM_CONFIRMATION.md`). Root cause is **traced + platform-confirmed**:
`hookSpecificOutput.updatedInput` is silently dropped for the Agent tool as a CLASS (upstream
anthropics/claude-code#39814, closed not-planned), so a by-reference (`@@lazy-ref`) Agent dispatch
lands the bare token at the subagent instead of the resolved bytes. Serving path traced:
`register_emission` stores `prompt_raw` (`lazy_core/dispatch.py:1859`) → the emit handler surfaces
`@@lazy-ref nonce=<hex>` (`bug-state.py:9222` / `:10020`; `lazy-state.py` twins) → the guard's
F2a `resolve_emission_by_nonce` (`:2014`) ALLOW+consumes → **platform drops the `updatedInput`
rewrite** → subagent boots with the bare token.

Locked fix = **subagent-side resolve, made a first-class delivery mechanism (option c, designed
form)**. By-reference stays PREFERRED; the resolved bytes are delivered by the subagent reading them
back from the registry via a sanctioned consumed-nonce read; verbatim remains the documented fallback.

## Validated Assumptions

- **Platform behavior is CONFIRMED, not assumed** (evidence: `PLATFORM_CONFIRMATION.md` — upstream
  #39814 reproduces the exact symptom, closed not-planned). No runtime spike is owed: the earlier
  "unconfirmed-platform-behavior" dependency is retired. Background-vs-foreground is NOT the axis —
  the rewrite never applies to any Agent dispatch.
- The remaining fix surface is **code-provable**: a read-only CLI that returns `prompt_raw` for an
  already-consumed, TTL-fresh, run-gated nonce, plus prose/template contract changes. No cross-boundary
  runtime assumption remains; the runtime-assumption gate is satisfied without a spike.

## Touchpoint Audit (verified inline — dispatch unavailable; bounded set audited via Read/Grep against the live tree)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core/dispatch.py` | yes | `register_emission` stores `prompt_raw` (:1859); `resolve_emission_by_nonce` Gate-1 filters consumed (:2014); `emission_consumed_by_nonce` (:2166) | refactor/add | Add a NEW consumed-tolerant reader (returns `prompt_raw` for a consumed + TTL-fresh + run-start-gated entry). REUSE the TTL + run-start gate logic from `resolve_emission_by_nonce` (do not duplicate the gate math). **Do NOT relax Gate-1 of the existing resolver** — the guard's dispatch path depends on it filtering consumed. Reader is READ-ONLY; never un-consumes. |
| `user/scripts/lazy-state.py` | yes | `build_parser()`; `--emit-prompt`/`--emit-dispatch` handlers building the `@@lazy-ref nonce=` token | add | Wire `--resolve-ref <nonce>` → print the registered prompt bytes (exit 0) / print nothing + exit 1 on miss. Orchestrator/subagent-callable (a subagent must be able to run it — it is a read, not a lifecycle op). |
| `user/scripts/bug-state.py` | yes | `dispatch_prompt_ref` (:9222) / `cycle_prompt_ref` (:10020) token emission; `build_parser()` | add | Same `--resolve-ref <nonce>` action (coupled-pair mirror; nonce is the key, so the `--feature-id`/`--bug-id` divergence does not apply). |
| `user/scripts/lazy-parity-manifest.json` | yes | coupled-pair CLI-surface registry | modify | Register `--resolve-ref` so `lazy_parity_audit.py::audit_state_script_parity` asserts BOTH scripts expose it. |
| `user/scripts/tests/test_lazy_core/test_dispatch.py` | yes | dispatch/registry resolver tests | modify | Tests for the new reader: returns bytes for a consumed entry; None on missing / TTL-expired / predates-run. |
| both state scripts' in-file `--test` harness | yes | `def test_*` fixtures + baselines under `tests/baselines/` | modify | `--resolve-ref` CLI fixtures on both scripts; regenerate byte-pinned baselines via `_normalize_smoke_output`. |
| dispatch-template emission (shared helper in `lazy_core/dispatch.py` + the two emit handlers) | yes | `f"@@lazy-ref nonce={...}"` at `bug-state.py:9222`/`:10020` (+ `lazy-state.py` twins) | refactor | Wrap the emitted ref surface with the contractual first-step instruction via a shared `lazy_core` helper so both scripts stay parity (single author of the ref-surface string). |
| `user/skills/lazy-batch/SKILL.md` | yes | §1d by-reference dispatch prose | modify | By-reference stays PREFERRED with the new delivery mechanism; verbatim = documented fallback; subagent resolves the nonce first. Coupled-pair edit. |
| `user/skills/lazy-bug-batch/SKILL.md` | yes | coupled dispatch prose | modify | Mirror lazy-batch. Parity-audited. |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | yes | coupled dispatch prose | modify | Mirror (per the coupled-pair table). |

No premise-grade contradictions surfaced; all findings are anchor-grade and already reflected in the phases below.

---

### Phase 1: Consumed-nonce resolver + `--resolve-ref` CLI (both state scripts, parity)

**Phase kind:** corrective

**Scope:** Add the sanctioned consumed-nonce read surface — a `lazy_core.dispatch` reader that returns the registered `prompt_raw` bytes for a nonce the guard already ALLOW+consumed **this run** (read-only, run-scoped, TTL-gated, never un-consumes), exposed as `--resolve-ref <nonce>` on both `lazy-state.py` and `bug-state.py`. This is the mechanism a subagent uses to recover its full instructions after the platform drops the by-reference `updatedInput` rewrite.

**Deliverables:**
- [ ] New reader in `user/scripts/lazy_core/dispatch.py` (e.g. `resolve_consumed_emission_by_nonce`) returning `prompt_raw` (fallback `prompt_norm`) for a **consumed**, TTL-fresh, run-start-gated registry entry — reusing the TTL + run-start gate logic of `resolve_emission_by_nonce`; READ-ONLY, never mutates `consumed`. Existing `resolve_emission_by_nonce` Gate-1 (unconsumed-only) is left UNCHANGED.
- [ ] `--resolve-ref <nonce>` CLI action on `user/scripts/lazy-state.py` (`build_parser()` + handler): prints the resolved prompt bytes to stdout + exit 0 on hit; prints nothing + exit 1 on miss (nonce absent / TTL-expired / predates run). Subagent-callable (a read; NOT gated by `refuse_if_cycle_active`).
- [ ] `--resolve-ref <nonce>` CLI action on `user/scripts/bug-state.py` (coupled-pair mirror — identical behavior; nonce keyed).
- [ ] Register `--resolve-ref` in `user/scripts/lazy-parity-manifest.json` so `lazy_parity_audit.py` asserts both scripts expose it.
- [ ] Tests: `tests/test_lazy_core/test_dispatch.py` — reader returns bytes for a consumed entry, None for missing / TTL-expired / cross-run; both scripts' in-file `--test` fixtures exercise `--resolve-ref` (hit → bytes/exit 0, miss → exit 1); byte-pinned `--test` baselines regenerated; `lazy_parity_audit.py --repo-root .` green.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --repo-root . --resolve-ref <a-consumed-nonce>` prints the exact registered prompt bytes and exits 0 (and `bug-state.py` does the same for the same nonce); an unknown nonce prints nothing and exits 1. Verified by the two scripts' `--test` harnesses + `pytest tests/test_lazy_core/test_dispatch.py` + `python3 user/scripts/lazy_parity_audit.py --repo-root .`.

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; the surface is a state-script CLI + `lazy_core` reader fully covered by the hermetic `--test`/pytest tiers.

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core/dispatch.py` — new consumed-tolerant reader beside `resolve_emission_by_nonce`.
- `user/scripts/lazy-state.py` — `--resolve-ref` arg + handler.
- `user/scripts/bug-state.py` — `--resolve-ref` arg + handler (mirror).
- `user/scripts/lazy-parity-manifest.json` — new coupled CLI-surface row.
- `user/scripts/tests/test_lazy_core/test_dispatch.py` + `tests/baselines/{lazy-state,bug-state}-test-baseline.txt` — coverage + regenerated baselines.

**Testing Strategy:** Pure hermetic Python. Register an emission, consume its nonce, assert the new reader returns the stored `prompt_raw`; assert TTL-expiry and cross-run gating return None; drive the CLI action through both `--test` harnesses. Run the parity audit to prove the coupled-pair mirror.

**Integration Notes for Next Phase:** Phase 2's emitted first-step instruction names the exact CLI form landed here (`--resolve-ref <nonce>` on the correct pipeline's script) — keep the flag name and the per-pipeline script mapping stable so the emitted instruction is copy-runnable.

---

### Phase 2: By-reference delivery contract — self-resolving dispatch template + coupled-skill prose

**Phase kind:** corrective

**Scope:** Make by-reference dispatch self-delivering. The emitted `@@lazy-ref` ref surface gains a contractual FIRST STEP telling the receiving subagent to resolve its instructions via the Phase-1 `--resolve-ref` read before doing anything else (so a subagent that receives the bare token never takes zero tool-uses / returns "no task attached"). Update the coupled dispatch skills so by-reference stays PREFERRED with the new mechanism and verbatim is the documented fallback. Add the zero-tool-use dead-return regression.

**Deliverables:**
- [ ] Shared `lazy_core` helper (single author of the ref-surface string) wraps the emitted `@@lazy-ref nonce=<hex>` token with the first-step instruction ("your full instructions are registered under nonce X; FIRST run `<pipeline state-script> --repo-root <root> --resolve-ref X` and follow the returned prompt before anything else"), consumed by both emit handlers (`lazy-state.py` cycle/dispatch emit + `bug-state.py:9222`/`:10020`) so the surfaced `dispatch_prompt_ref`/`cycle_prompt_ref` carries it.
- [ ] `user/skills/lazy-batch/SKILL.md` §1d: by-reference stays PREFERRED with the new delivery mechanism; document verbatim as the fallback; state the subagent-side resolve-first contract.
- [ ] `user/skills/lazy-bug-batch/SKILL.md`: mirror (coupled-pair edit).
- [ ] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`: mirror per the coupled-pair table.
- [ ] Tests: a regression asserting the emitted ref surface carries the `--resolve-ref` first-step instruction (both pipelines), covering the zero-tool-use dead-return near-miss (a bare-token surface with no resolve instruction is the failure mode this guards). `lazy_parity_audit.py --repo-root .` green after the coupled-skill edits.

**Minimum Verifiable Behavior:** `python3 user/scripts/bug-state.py --repo-root . --emit-prompt …` (with a live marker) surfaces a `cycle_prompt_ref` whose text contains both the `@@lazy-ref nonce=` token AND a runnable `--resolve-ref` first-step instruction; the `lazy-state.py` twin does the same. Verified by the new dispatch-emission regression test + both `--test` harnesses.

**MCP Integration Test Assertions:** N/A — the surface is emitted prompt text + skill prose, covered by the hermetic emission regression test; no app runtime.

**Prerequisites:**
- Phase 1: the `--resolve-ref` reader + CLI must exist so the emitted first-step instruction points at a real, runnable command.

**Files likely modified:**
- `user/scripts/lazy_core/dispatch.py` — shared ref-surface-wrapper helper.
- `user/scripts/lazy-state.py` / `user/scripts/bug-state.py` — emit handlers consume the wrapper (parity).
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — coupled dispatch prose.
- `user/scripts/tests/test_lazy_core/test_dispatch.py` (+ in-file `--test` fixtures) — emission-carries-instruction regression.

**Testing Strategy:** Assert the emitted ref surface string contains the resolve instruction for both pipelines (the near-miss guard: a bare token with no instruction fails the test). Run `lazy_parity_audit.py` to prove the three coupled skills stay in lockstep, and re-run `project-skills.py` to confirm the cloud/lazy-bug projections expand cleanly.

**Integration Notes for Next Phase:** None — final phase. On completion the state machine routes to the completion gate; the top-level PHASES `**Status:**` is set to `In-progress` when Phase 2's work lands (implementation done, validation via the invariant gate-battery pending), never `Fixed` (gate-owned).

---

## Implementation Notes

- **Origin / provenance:** operator-locked fix from `NEEDS_INPUT_RESOLVED_2026-07-18.md` ("## Resolution (final — fix fork)", option c) + `PLATFORM_CONFIRMATION.md` (upstream anthropics/claude-code#39814). The SPEC's earlier "DEFERRED to park" fix-scope section was superseded/reconciled to the locked scope during this `/plan-bug` cycle.
- **Coupled-pair discipline:** every state-script change (the `--resolve-ref` CLI, the ref-surface wrapper) is a `lazy-state.py` ↔ `bug-state.py` coupled-pair edit — run `python3 user/scripts/lazy_parity_audit.py --repo-root .` after each. The three dispatch skills (`lazy-batch` ↔ `lazy-bug-batch` ↔ `lazy-batch-cloud`) are a coupled-prose set — mirror edits and re-run `project-skills.py`.
- **Do NOT weaken the existing guard:** `resolve_emission_by_nonce`'s consumed-filter (Gate-1) stays intact; the new reader is additive. Verbatim dispatch remains fully hash-validated by the guard's `lookup_emission` ALLOW+consume path (the integrity mechanism is unaffected by this bug).
