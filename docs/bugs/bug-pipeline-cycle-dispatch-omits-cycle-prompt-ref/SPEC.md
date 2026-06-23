# Bug-pipeline cycle dispatch omits `cycle_prompt_ref` (every bug cycle goes by value) — Investigation Spec

> `bug-state.py --emit-prompt` registers the cycle prompt in the by-reference registry but never surfaces the `@@lazy-ref` token, so `/lazy-bug` and `/lazy-bug-batch` dispatch every real-skill cycle by value — re-inlining 9.5–12K-char prompts the feature pipeline passes as a 49-char reference.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-23
**Placement:** docs/bugs/bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref
**Related:** `docs/bugs/_archive/byref-dispatch-undercounts-forward-cycles` (the feature-pipeline by-reference counter fix); root `CLAUDE.md` mission ("script-emitted prompts over hand-composed ones"); coupled-pair table (`/lazy-batch` ↔ `/lazy-bug-batch`)

---

## Verified Symptoms

1. **[VERIFIED]** In a real AlgoBooth `/lazy-bug-batch` run (session `a6c71b1c`, bug `adhoc-add-midi-mapping-jog-tool`), the cycle-1 (`spec-bug`), cycle-2 (`plan-bug`), and cycle-3 (`execute-plan`) worker dispatches each carried the **full prompt text** (9520 / 9520 / 12374 chars) in the Agent tool's `prompt:` field — by value. — confirmed by mining the session JSONL.
2. **[VERIFIED]** The by-reference dispatches in the same run (`@@lazy-ref nonce=…`, 49 chars) were **all `--emit-dispatch` meta-dispatches** (`input-audit`, `needs-runtime-redispatch`, `hardening`) carrying `dispatch_prompt_ref` — *not* ordinary `--emit-prompt` cycle dispatches. The nonce `52ac…` that looked like "cycle 4 mcp-test" was a `needs-runtime-redispatch` meta-dispatch. — confirmed by tracing nonces to their emitting `--emit-dispatch <class>` calls.
3. **[VERIFIED]** Every `bug-state.py --emit-prompt` probe in the run emitted `cycle_prompt` (present) with **`cycle_prompt_ref` entirely absent** from the JSON (not even `null`) — including the mcp-test probes. — confirmed by grepping the probe tool-results.
4. **[VERIFIED]** The run marker was live throughout (meta-dispatch refs registered and resolved fine), so the absence is **not** a marker/staleness condition. — confirmed by the successful `dispatch_prompt_ref` emissions interleaved with the by-value cycles.

The user's original framing ("subagent prompts should be passed by reference") is confirmed as a real defect, but the symptom is **not** visible in the worker's prompt panel: the `lazy-dispatch-guard.sh` PreToolUse hook resolves a `@@lazy-ref` token to the full bytes (`updatedInput`) before the worker runs, so a correct by-reference dispatch *also* displays full text. The defect is on the **orchestrator emission side** — the token-cost win that never happened.

## Reproduction Steps

1. Run `/lazy-bug-batch` against any repo with a live run marker.
2. For any real-skill cycle (`spec-bug`, `plan-bug`, `execute-plan`, `mcp-test`), inspect the `bug-state.py --emit-prompt` probe JSON: `cycle_prompt` is present, `cycle_prompt_ref` is absent.
3. Observe the orchestrator dispatch the Agent worker with the full `cycle_prompt` verbatim (no `@@lazy-ref` token available to use).

**Expected:** Each `--emit-prompt` cycle probe surfaces `cycle_prompt_ref: "@@lazy-ref nonce=<hex>"`, and the orchestrator dispatches the 49-char token (by reference), exactly as `lazy-state.py` / the feature pipeline does.
**Actual:** `cycle_prompt_ref` is never surfaced; the orchestrator falls back to verbatim by-value dispatch for every bug-pipeline cycle.
**Consistency:** Always (deterministic — a missing assignment, not a race).

## Evidence Collected

### Source Code (root cause)

`user/scripts/bug-state.py:5807-5812` — registers the emission but **discards the returned entry**:

```python
cycle_prompt = state.get("cycle_prompt")
if cycle_prompt:
    lazy_core.register_emission_if_marked(   # return value discarded
        cycle_prompt, "cycle",
        item_id=state.get("feature_id"),
    )
```

`user/scripts/lazy-state.py:10036-10050` — the correct parallel block **captures and surfaces** the token:

```python
cycle_prompt = state.get("cycle_prompt")
if cycle_prompt:
    _ref_entry = lazy_core.register_emission_if_marked(
        cycle_prompt, "cycle",
        item_id=state.get("feature_id"),
    )
    if _ref_entry is not None:
        state["cycle_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"
    else:
        state["cycle_prompt_ref"] = None
else:
    state["cycle_prompt_ref"] = None
```

The registration itself succeeds in both scripts (the prompt *is* in `lazy-prompt-registry.json`, so the hook *could* resolve a token) — but `bug-state.py` never hands the orchestrator a nonce to dispatch with.

### Runtime Evidence

Session `~/.claude/projects/C--Users-Jacob-repos-AlgoBooth/a6c71b1c-…jsonl`:

| Dispatch | Step | `prompt:` form | Source |
|---|---|---|---|
| Cycle 1 | spec-bug | full text, 9520 chars | `--emit-prompt` (no ref) |
| input-audit | — | `@@lazy-ref nonce=75de…` | `--emit-dispatch input-audit` |
| Cycle 2 | plan-bug | full text, 9520 chars | `--emit-prompt` (no ref) |
| Cycle 3 | execute-plan | full text, 12374 chars | `--emit-prompt` (no ref) |
| "Cycle 4" | mcp-test redispatch | `@@lazy-ref nonce=52ac…` | `--emit-dispatch needs-runtime-redispatch` |
| hardening | — | `@@lazy-ref nonce=ec2…` | `--emit-dispatch hardening` |

Probe JSON for every `--emit-prompt` cycle: `cycle_prompt` present, `cycle_prompt_ref` ABSENT.

### Git History

The feature-pipeline by-reference machinery (`@@lazy-ref` cycle tokens) landed with the prompt-registry work and was hardened in `byref-dispatch-undercounts-forward-cycles` (archived, fixed 2026-06-19, commit `674e0df`). The bug pipeline's `--emit-prompt` registration was added in the same Phase-1 registry integration but the `cycle_prompt_ref` surfacing line was never mirrored into `bug-state.py`.

### Related Documentation

- Root `CLAUDE.md` mission: "**Efficient** — minimize wasted tokens … script-emitted prompts over hand-composed ones."
- `user/scripts/CLAUDE.md` Coupling Rule: changes to the state machine must be mirrored across the coupled `lazy-state.py` ↔ `bug-state.py` pair; `lazy_parity_audit.py` is the gate.

## Theories

### Theory 1: Unmirrored coupled-pair parity gap — `cycle_prompt_ref` surfacing missing from `bug-state.py`
- **Hypothesis:** The Phase-1 registry integration added `register_emission_if_marked` to both scripts, but only `lazy-state.py` was extended (in a later edit) to capture `_ref_entry` and set `state["cycle_prompt_ref"]`. The mirror into `bug-state.py` was never made, so the bug pipeline registers-but-never-surfaces.
- **Supporting evidence:** Source diff between the two blocks is exactly the missing capture+assign; runtime probes show the field absent; marker was live (rules out staleness).
- **Contradicting evidence:** None found.
- **Status:** **Confirmed.**

## Proven Findings

- **Root cause:** `bug-state.py:5807-5812` discards the return value of `register_emission_if_marked` and never sets `state["cycle_prompt_ref"]`; `lazy-state.py:10036-10050` does. The bug pipeline therefore has no by-reference token to dispatch and falls back to by-value for every cycle.
- **Not a marker/race issue:** the field is unconditionally absent, deterministic.
- **Worker-panel symptom is a red herring:** the guard resolves the token to full bytes before the worker runs, so by-reference and by-value look identical in the worker panel; the cost is purely orchestrator-side emission tokens.
- **Secondary gap:** `lazy_parity_audit.py` did not catch this divergence — the audit apparently does not assert `cycle_prompt_ref` surfacing parity across the two `--emit-prompt` paths. Worth a fix-time check so the mirror can't silently drift again.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Bug-pipeline prompt emission | `user/scripts/bug-state.py` (~5807-5812) | Missing `cycle_prompt_ref` surfacing — the fix site |
| Reference impl | `user/scripts/lazy-state.py` (~10036-10050) | Correct block to mirror (no change) |
| Parity audit | `user/scripts/lazy_parity_audit.py` | Does not assert this parity — candidate hardening |
| Smoke tests | `bug-state.py --test` in-file harness | Add a fixture asserting `cycle_prompt_ref` present under a live marker |
| Consumers (no change owed) | `/lazy-bug`, `/lazy-bug-batch` SKILL.md | Already prefer `cycle_prompt_ref` when present — they begin using it for free once surfaced |

## Fix Scope (for /plan-bug)

Mechanical coupled-pair mirror — small and low-risk:

1. In `bug-state.py:5807-5812`, capture `_ref_entry` and set `state["cycle_prompt_ref"]` exactly as `lazy-state.py:10036-10050` (token when entry present, `None` otherwise, `None` when no `cycle_prompt`).
2. Add a `bug-state.py --test` fixture: live marker + real-skill emit ⇒ probe carries `cycle_prompt_ref: "@@lazy-ref nonce=…"`; no marker ⇒ `None` (byte-identical-when-absent preserved).
3. Run the parity audit (`lazy_parity_audit.py --repo-root . --pair lazy-bug-batch`); if it doesn't already cover the `cycle_prompt_ref` surfacing, add that assertion so the pair can't drift again.
4. Regenerate the byte-pinned `bug-state` smoke baseline only via `_normalize_smoke_output` (never by hand).

## Open Questions

- Should the parity audit gain a generic "every `state[...] =` surfaced field in one `--emit-prompt` path exists in the other" check, or just a targeted `cycle_prompt_ref` assertion? (Targeted is sufficient to close this bug; generic is a larger hardening.)
