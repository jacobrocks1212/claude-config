# Implementation Phases — `--cycle-begin --kind real` must require/validate `--sub-skill`

**Status:** In-progress

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure state-script CLI validation change (Python argparse handler + in-file `--test` smoke fixtures + docs). There is no app/MCP-reachable surface; per `docs/features/mcp-testing/SPEC.md` this is the "build tooling / no app integration" untestable class. Validation is via the scripts' own `--test` smoke harnesses and `lazy_parity_audit.py`, not the MCP HTTP server.

## Validated Assumptions

All load-bearing assumptions here are **code-provable** (argparse handler control flow, string constants, the in-file `--test` subprocess harness), ground-truthed at planning time — no runtime-coupled assumption rides into implementation:

- **`--cycle-begin` handler insertion point (both scripts) verified.** `lazy-state.py:11013-11015` and `bug-state.py:6629-6632` validate only id + nonce (`_die(...)`), immediately before the marker-write preamble. The new guard lands directly after the existing `_die`, before any run-marker read or `write_cycle_marker` call. Confirmed by reading both handlers.
- **`--sub-skill` is optional, default `None` (both scripts).** `lazy-state.py:10665`, `bug-state.py:6454`. A `--kind real` dispatch that omits it currently writes `sub_skill=None`.
- **`--kind meta` exemption is real and must be preserved.** `lazy_core.py:10962` (`if marker.get("kind") == "meta": …` disables signal (b) for meta cycles). The guard must therefore gate on `args.kind == "real"` only, leaving meta cycles free to omit `--sub-skill`.
- **`--test` smoke harness shape verified.** Both scripts run subprocess invocations of themselves with assembled arg vectors and assert on `returncode`/stdout (e.g. `lazy-state.py:9625-9642`, `bug-state.py:5227-5240`). Existing `--cycle-begin` fixtures already pass `--sub-skill execute-plan`, so they stay green; new fixtures follow the identical pattern.
- **Provenance:** `lazy-state.py` / `bug-state.py` are governed by budget/dispatch decision records (`--provenance-lookup`). This change is purely additive input validation on `--cycle-begin` and hardens the write-side `sub_skill` contract those records already assume; it contradicts no Locked Decision.

## Touchpoint Audit

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy-state.py` | yes | `--cycle-begin` handler at `11013`; `_die()`; `--sub-skill` arg at `10665` | edit | Insert the guard right after the `_die("--cycle-begin requires --feature-id and --nonce")` line (`11015`); reuse the existing module-level `_die()` helper — do NOT write a new error path |
| `user/scripts/bug-state.py` | yes | `--cycle-begin` handler at `6629`; `_die()`; `--sub-skill` arg at `6454` | edit (coupled mirror) | Insert the identical guard after `_die("--cycle-begin requires --bug-id and --nonce")` (`6632`); byte-parallel to the lazy-state edit |
| `user/scripts/lazy-state.py` `--test` harness | yes | subprocess-fixture pattern at `9625-9642` | edit | Add two fixtures: real-without-`--sub-skill` exits non-zero + zero marker written; meta-without-`--sub-skill` exits 0. Reuse the existing fixture scaffold |
| `user/scripts/bug-state.py` `--test` harness | yes | subprocess-fixture pattern at `5227-5240` | edit | Mirror the same two fixtures (bug-id variant) |
| `user/scripts/lazy_core.py` (10972-10993 read-side guard) | yes | `detect_cycle_bracket_friction` signal (b) | **unchanged** | RETAINED as defense-in-depth; do NOT modify — SPEC Proven Findings explicitly keeps it |
| `user/scripts/CLAUDE.md` | yes | `--cycle-begin` CLI reference + "Per-sub_skill commit budget is DERIVED" note | edit | Promote the prose "MANDATES `--sub-skill`" to documented HARD enforcement (script `_die`, not prose-only) |

No net-new files. No contradictions surfaced — the SPEC's serving-path trace matches disk exactly, so no drift correction was needed.

## Coupled-Pair / Parity Note

`--cycle-begin` is a coupled-pair CLI on both state scripts (root `CLAUDE.md` Coupled Skill Pairs / `lazy-parity-manifest.json`). The validation guard AND its `--test` smoke fixtures MUST land on both scripts in the same phase — a half-applied edit would fail `python3 user/scripts/lazy_parity_audit.py --repo-root .` (must stay exit 0). This is why the fix is a single phase: splitting it across phases would leave parity red mid-plan.

---

### Phase 1: Require `--sub-skill` on `--kind real` at `--cycle-begin` (both state scripts) + smoke fixtures + docs

**Scope:** Add write-side validation so a `--kind real` cycle marker can never be born with `sub_skill=None`, mirrored across both state scripts as a coupled-pair edit, with `--test` smoke fixtures proving both the refusal and the meta exemption, and a docs promotion of the prose contract to documented hard enforcement.

**Deliverables:**
- [x] In `user/scripts/lazy-state.py` `--cycle-begin` handler (after the id+nonce `_die` at ~11015), add: `if args.kind == "real" and not (args.sub_skill or "").strip(): _die("--cycle-begin --kind real requires --sub-skill")`. The guard runs BEFORE any run-marker read or `write_cycle_marker` call, so a refused real cycle mutates zero marker state.
- [x] In `user/scripts/bug-state.py` `--cycle-begin` handler (after the id+nonce `_die` at ~6632), add the byte-parallel guard (same condition, same message text). Coupled-pair mirror.
- [x] Add two `--test` smoke fixtures to `user/scripts/lazy-state.py`: (a) `--cycle-begin --feature-id … --nonce … --kind real` WITHOUT `--sub-skill` exits non-zero AND writes no cycle marker; (b) `--cycle-begin --feature-id … --nonce … --kind meta` WITHOUT `--sub-skill` exits 0. Follow the existing subprocess-fixture scaffold (~`9625`).
- [x] Add the mirrored two `--test` fixtures to `user/scripts/bug-state.py` (bug-id variant), following its scaffold (~`5227`).
- [x] Update `user/scripts/CLAUDE.md`: promote the `--cycle-begin` "MANDATES `--sub-skill`" prose to a documented HARD enforcement (a `--kind real` cycle now script-refuses a missing `--sub-skill`; `--kind meta` remains exempt). Note the Round-3 read-side guard (`lazy_core.py:10972-10993`) is RETAINED as defense-in-depth for legacy/meta/degraded markers.
- [x] Tests: both scripts' `--test` harnesses pass (`python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both exit 0), and `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0.

**Implementation Notes (2026-07-06):**
- Guard landed verbatim as specified in both scripts, immediately after the existing id+nonce `_die`, before the run-marker read / `reconcile_cycle_begin_git_consistency` / `write_cycle_marker` calls — zero marker mutation on refusal.
- New fixture `cycle-begin-real-requires-sub-skill` added to both `--test` harnesses (mirrored, `--feature-id`/`--bug-id` variant), asserting: (a) real+no-sub-skill refuses with no marker written, (b) meta+no-sub-skill still succeeds and writes a marker, (c) real+sub-skill regression stays green.
- **Regression fallout (not anticipated by the SPEC/plan):** three existing `--cycle-begin` fixture call sites per script relied on the (until now unenforced) `--kind real` default WITHOUT passing `--sub-skill` and asserted exit 0 — `cycle-marker-mutation-guard` fixture (d), `cycle-begin-git-consistency-reconciliation` fixture (lazy-state.py only), and `cycle-end-bracket-fail-open` fixture (both scripts). Each was auditing an orthogonal concern (marker overwrite, git-lock reconciliation, fail-open bracket append) and would have started failing under the new guard. Fixed by adding `--sub-skill execute-plan` to those five invocations (3 in lazy-state.py, 2 in bug-state.py) — no assertion logic changed, only the fixture's own `--cycle-begin` setup call. Confirmed via a full sweep of every `"--cycle-begin"` call site in both files before landing the guard, not just the two call sites the plan named.
- Docs: `user/scripts/CLAUDE.md`'s `--cycle-begin` CLI reference line now documents the hard enforcement + cross-references the retained read-side guard and the (unmodified) `lazy_core.py:10990` prose comment.
- Gates run: `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py --repo-root .`, `doc-drift-lint.py --repo-root .` — all exit 0.
- Files modified: `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/CLAUDE.md`.

**Minimum Verifiable Behavior:** `LAZY_ORCHESTRATOR=1 python3 user/scripts/lazy-state.py --cycle-begin --feature-id feat-x --nonce deadbeef --kind real --repo-root <tmp-repo>` (no `--sub-skill`) exits non-zero with the corrective stderr `--cycle-begin --kind real requires --sub-skill` and writes no cycle marker; the same command with `--kind meta` exits 0; the same command with `--kind real --sub-skill execute-plan` exits 0. This is exercised deterministically by the new `--test` smoke fixtures.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior reachable via the MCP HTTP server. This phase's behavior is a CLI exit-code + stderr contract, verified by the in-file `--test` smoke harness and the parity audit (the repo-appropriate equivalents of runtime verification for a state-script change).

**Prerequisites:** None (single phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — add `--kind real` requires `--sub-skill` guard in `--cycle-begin` handler + two `--test` fixtures.
- `user/scripts/bug-state.py` — coupled-pair mirror of the guard + two `--test` fixtures.
- `user/scripts/CLAUDE.md` — promote prose contract to documented hard enforcement.

**Testing Strategy:**
Deterministic, hermetic — no runtime/MCP needed. The two new fixtures per script assert the refusal (non-zero exit + zero marker mutation) and the meta exemption (exit 0) directly through the scripts' own `--test` subprocess harnesses. Existing `--cycle-begin` fixtures (which pass `--sub-skill execute-plan`) stay green, proving no regression on the happy path. `lazy_parity_audit.py` confirms the coupled-pair edit is symmetric.

**Integration Notes for Next Phase:**
- Single phase — no next phase. The read-side fail-open guard (`lazy_core.py:10972-10993`) is deliberately UNCHANGED; do not remove or weaken it (it still fail-opens correctly for `--kind meta` and legacy markers).
- Out of scope (per SPEC Open Questions): budget thresholds, the `_MULTI_COMMIT_DISPATCH_SKILLS` registry class (`adhoc-derive-multi-commit-budget-from-dispatch-sites`), and removal of the read-side guard.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to Fixed and writes FIXED.md once this phase's validation tail (`/mcp-test` → coverage audit) passes. This plan never flips top-level status itself.
