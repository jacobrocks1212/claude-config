# Two autonomous queue-walkers on the same branch have no arbitration → operator must adjudicate; push collisions force manual merges — Investigation Spec

> When two autonomous `/lazy-batch` queue-walkers run against the same repo/branch (same git account), the second walker's `--run-start` silently overwrites the first's live run marker instead of being refused — because `refuse_run_start_clobber` allows ALL same-pipeline overwrites (it cannot distinguish a sanctioned checkpoint-resume from a genuinely-concurrent second walker). With no deterministic arbitration, collisions on feature selection and push ordering surface mid-run and escalate to the operator, and overlapping edits fall to manual multi-commit merges.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/concurrent-same-branch-walkers-no-arbitration
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/CLAUDE.md`; `docs/features/multi-repo-concurrent-runs/` (solved the cross-repo case via per-repo keyed state dirs + `refuse_run_start_clobber`; explicitly left the **same-repo / same-branch / same-pipeline** case as "refused by construction" — but that refusal has a gap, see Proven Findings)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[OBSERVED in logs]** The orchestrator detected a second autonomous session committing+pushing to the same branch and, lacking arbitration, had to ask the operator — session `5c33b6ba` @ `2026-06-11 15:49` (AskUserQuestion): "A second autonomous Claude session is actively committing + pushing to this same main branch (same git account, 3 claude.exe processes live) … Two autonomous queue-walkers on one branch risk colliding on feature selection and push ordering." (operator response: "Continue full run. The other session is finished.").
2. **[OBSERVED in logs]** Overlapping parallel edits from another session surfaced as an 8-commit remote advance requiring manual merge reconciliation — session `f2437fdb` @ `2026-06-08T20:34:34`: "The remote advanced with 8 commits from another session, and they overlap heavily with my files — including … the exact Step 1g region I just componentized." (manual two-session merge reconciliation, 20:35–20:43).

## Reproduction Steps

1. Start `/lazy-batch` in repo R (writes the run marker via `lazy-state.py --run-start`; `pipeline:feature`, age-fresh, bound or bind-pending).
2. In a SECOND session, start `/lazy-batch` in the SAME repo R (same `repo_root` → same keyed state subdir → same marker file).
3. The second session's `--run-start` calls `refuse_run_start_clobber("feature")`.

**Expected:** the second `--run-start` is refused (the first run is live, age-fresh, same repo, same pipeline, and NO checkpoint is waiting → this is a concurrent second walker, not a resume), naming the in-flight run and instructing the operator how to proceed.
**Actual:** `refuse_run_start_clobber` returns early at the `existing_pipeline == incoming_pipeline` branch (`lazy_core.py:8735–8736`) and `write_run_marker` overwrites the first run's marker. Both walkers proceed on the same branch with no arbitration; collisions on feature selection / push ordering surface mid-run and escalate to the operator (Symptom 1), and overlapping edits force a manual merge (Symptom 2).
**Consistency:** deterministic — any same-repo same-pipeline second `--run-start` while the first marker is live + age-fresh takes the allow branch.

## Evidence Collected

### Source Code

- **`lazy_core.py::refuse_run_start_clobber(incoming_pipeline, *, now=None)` (≈ line 8665).** The ENTRY guard on every `--run-start`. It reads the marker raw, honors only 24h AGE staleness, and refuses ONLY when the existing marker's pipeline DIFFERS from the incoming one (the D-B cross-pipeline-clobber defect from `hardening-blind-to-process-friction`). The same-pipeline branch returns unconditionally:
  ```python
  if existing_pipeline == incoming_pipeline:
      return  # same-pipeline re-run-start (checkpoint resume) → allow overwrite
  ```
  The docstring's DISCRIMINATOR rationale states: "A SAME-pipeline re-`--run-start` is the legitimate checkpoint-resume case … and is ALLOWED to overwrite." This conflates two distinct cases — there is no check that a checkpoint is actually present.
- **`lazy-state.py:7378–7398` (feature `--run-start` handler).** Order of guards: `refuse_if_cycle_active("--run-start")` → `refuse_run_start_clobber("feature")` → `write_run_marker(...)`. The clobber guard runs and may `sys.exit(3)` BEFORE `consume_run_checkpoint()` (line 7403). Critically, the checkpoint FILE is already on disk at clobber-check time — a legitimate resume always has `lazy-run-checkpoint.json` present (written by the prior `--run-end --reason checkpoint`), whereas a second concurrent walker has NONE. So the discriminator the guard is missing is available without reordering anything: a non-destructive existence read of the checkpoint file.
- **`lazy_core.py::consume_run_checkpoint()` (≈ line 10606).** Reads-and-DELETES `lazy-run-checkpoint.json` (consume-once). The resume signal. `write_run_checkpoint` (≈ line 10595) is the only producer, written exclusively by a `--run-end --reason checkpoint` (a sanctioned pause). A fresh second-walker `--run-start` never has this file.
- **`refuse_run_start_clobber` mirrored on the bug pipeline** (`bug-state.py` calls `refuse_run_start_clobber("bug")`) — the coupled pair shares the `lazy_core` helper, so any fix lands on BOTH pipelines for free (audited by `lazy_parity_audit.py`).

### Git History

No recent code change introduced this — the gap is inherent to the `refuse_run_start_clobber` design as shipped by `hardening-blind-to-process-friction` (cross-pipeline only) and was knowingly scoped out by `multi-repo-concurrent-runs` ("refused by construction" was asserted for the same-repo case but the actual refusal only covers cross-pipeline, not same-pipeline-concurrent).

### Related Documentation

- `docs/features/multi-repo-concurrent-runs/SPEC.md` — solved cross-repo concurrency via per-repo keyed state dirs (`claude_state_dir()` → `~/.claude/state/<repo_key>/`). Its "Same-repo second run" UX promises a refusal "naming the in-flight run (`started_at`, `forward_cycles`)" — but the implemented `refuse_run_start_clobber` only delivers that for a DIFFERENT pipeline. The same-pipeline-concurrent case is the residual gap this bug closes.
- `user/scripts/CLAUDE.md` → "Same-repo refusal / cross-repo concurrency": documents `refuse_run_start_clobber` as refusing "a live, non-stale, DIFFERENT-pipeline marker." Confirms by its own wording that same-pipeline concurrent is NOT refused.

## Theories

### Theory 1: The same-pipeline allow branch conflates checkpoint-resume with a concurrent second walker
- **Hypothesis:** `refuse_run_start_clobber` allows every same-pipeline overwrite to permit checkpoint-resume, but a genuinely-concurrent second walker is also same-pipeline and same-repo, so it slips through the same branch and clobbers the live marker.
- **Supporting evidence:** `lazy_core.py:8735–8736` (the unconditional same-pipeline return); the docstring explicitly equates "same-pipeline re-run-start" with "checkpoint resume"; a legitimate resume always carries a `lazy-run-checkpoint.json` file (the genuine discriminator) which a second walker lacks.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

### Theory 2: Mid-run detection is too late — collisions surface after both walkers are already committing
- **Hypothesis:** Because `--run-start` does not arbitrate up front, two walkers both proceed, and the conflict is only noticed mid-run when one detects the other's pushes (Symptom 1) or when remote advances with overlapping edits (Symptom 2) — forcing an operator escalation or a manual merge.
- **Supporting evidence:** both symptom log entries are mid-run detections, not up-front refusals; there is no up-front same-pipeline arbitration in the `--run-start` path.
- **Contradicting evidence:** none. (This is the downstream consequence of Theory 1, not an independent root cause.)
- **Status:** Confirmed (consequence of Theory 1).

## Proven Findings

**Root cause (CONFIRMED):** `refuse_run_start_clobber` (in `lazy_core.py`) refuses a `--run-start` clobber ONLY when the existing live marker belongs to a DIFFERENT pipeline. The same-pipeline branch returns unconditionally (`lazy_core.py:8735–8736`) on the justification that it is a "checkpoint resume" — but it never verifies a checkpoint is actually present. A second concurrent same-repo, same-pipeline `/lazy-batch` walker therefore overwrites the first walker's live run marker silently. With the marker clobbered, there is no deterministic arbitration between the two walkers, so collisions on feature selection and push ordering are detected only mid-run and escalated to the operator (Symptom 1), and overlapping parallel edits surface as a multi-commit remote advance requiring a manual merge (Symptom 2).

**Why the existing prior art does NOT cover this:** `multi-repo-concurrent-runs` scoped state per repo (closing the CROSS-repo false-block) and added `refuse_run_start_clobber` for the CROSS-pipeline clobber — but it left the same-repo / same-pipeline / genuinely-concurrent case unprotected. The feature's own SPEC asserted "a second run in the same repo is refused by construction," but the construction only refuses cross-pipeline. This bug is the missing leg of that promise.

**The discriminator that closes the gap (CONFIRMED available):** a legitimate checkpoint-resume is uniquely identified by the presence of `lazy-run-checkpoint.json` on disk (written only by `--run-end --reason checkpoint`; consumed-and-deleted by the next `--run-start`). At clobber-check time the file is already present for a resume and absent for a second walker. So the same-pipeline allow branch should be split:
- **checkpoint file present** (a sanctioned resume) → allow the overwrite (current behavior, correct).
- **checkpoint file absent + marker live + age-fresh** (a concurrent second walker) → REFUSE (exit 3, zero side effects), naming the in-flight run's `started_at` / `forward_cycles` (matching the `multi-repo-concurrent-runs` UX promise and the cross-pipeline refusal message shape).

The refuse function must read the checkpoint NON-destructively (existence check only — NOT `consume_run_checkpoint`, which deletes), because it runs before the handler's own `consume_run_checkpoint()` call and must not consume the resume signal it is gating on.

**Recommended fix scope (⚖ D7 scope-class — refusal vs. lease both reach the same end-state):**
1. **Primary (recommended): extend `refuse_run_start_clobber` to arbitrate the same-pipeline case.** In the `existing_pipeline == incoming_pipeline` branch, before returning, check for a live (age-fresh) marker AND the ABSENCE of `lazy-run-checkpoint.json`. If both hold, refuse with a diagnostic naming the in-flight run (mirror the cross-pipeline refusal message + the `multi-repo-concurrent-runs` "Same-repo second run" UX). Keep the allow path for: stale (>24h) markers, and same-pipeline-with-checkpoint-present (genuine resume). This reuses the existing chokepoint, lands on BOTH pipelines via the shared `lazy_core` helper, and is consistent with the cross-pipeline refusal already in place.
2. **Tests:** add `test_lazy_core.py` fixtures — (a) same-pipeline live marker + NO checkpoint → exit-3 refusal; (b) same-pipeline live marker + checkpoint present → allow (resume preserved); (c) same-pipeline stale (>24h) marker → allow (reclaim preserved); (d) cross-pipeline behavior unchanged. Run the full set per the Coupling Rule: `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`, and `lazy_parity_audit.py` (the helper is shared/coupled).
3. **Docs:** update `user/scripts/CLAUDE.md` ("Same-repo refusal / cross-repo concurrency") and the root `CLAUDE.md` to state that same-pipeline concurrent same-repo runs are now refused (checkpoint-discriminated), closing the `multi-repo-concurrent-runs` residual gap. Add a reverse-reference there to this bug.

**Alternative considered (NOT recommended this cycle):** a full feature/queue-item lease + fencing-token arbitration (the `lazy_coord.py` concurrency plane already provides exactly this for `lazy-worker` sessions). That machinery enables true PARALLEL same-repo work via worktree isolation, which is a larger product capability than this bug requires. The bug's symptoms are about UNINTENDED concurrent walkers on ONE branch with no worktree isolation — for that, up-front refusal (option 1) is the correct, minimal, in-scope fix. If the operator later wants intentional parallel same-repo walkers, that is the `lazy-worker` + `lazy_coord.py` path, not `/lazy-batch` on a shared branch. (Both options converge on the same end-state for THIS bug — no unintended second walker proceeds unarbitrated — so this is scope-class, not product-class.)

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Run-start clobber arbitration | `user/scripts/lazy_core.py` (`refuse_run_start_clobber`, ≈ line 8665) | Add same-pipeline concurrent-walker refusal gated on checkpoint-absence; the single fix site, shared by both pipelines |
| Feature run-start handler | `user/scripts/lazy-state.py` (≈ 7378–7398) | No logic change needed (the guard call already exists); confirm the checkpoint file is on disk at guard time (it is — consume happens later at 7403) |
| Bug run-start handler | `user/scripts/bug-state.py` (`refuse_run_start_clobber("bug")` call) | Inherits the fix via the shared helper; verify parity via `lazy_parity_audit.py` |
| State-machine tests | `user/scripts/test_lazy_core.py`, `lazy-state.py --test`, `bug-state.py --test` | New fixtures for the four same-pipeline cases above |
| Docs | `user/scripts/CLAUDE.md`, root `CLAUDE.md` | Document the closed gap + reverse-reference this bug |

## Open Questions

None blocking implementation. Two design points are pre-resolved as scope-class (⚖ D7):
- Arbitration mechanism: up-front refusal (recommended) vs. lease/worktree parallelism — both reach the same end-state for this bug; refusal is the minimal in-scope fix, `lazy_coord.py` parallelism is a separate capability. (resolved — refusal.)
- Resume discriminator: presence of `lazy-run-checkpoint.json` (non-destructive read) cleanly separates a sanctioned resume from a concurrent walker. (resolved — checkpoint-file existence.)
