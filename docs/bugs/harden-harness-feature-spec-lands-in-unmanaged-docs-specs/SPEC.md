# `/harden-harness` Lands Feature-Scope Investigation Specs in the Unmanaged `docs/specs/` Archive — Investigation Spec

> `/harden-harness` Step 2.5 ("Bug-spec FIRST") tells the agent to author the investigation
> spec at `docs/bugs/<slug>/SPEC.md`, but for a **feature-scope** deliverable it directs
> `/spec` **under `docs/specs/`**. `docs/specs/` is the historical / manually-authored spec
> ARCHIVE and is explicitly NOT under lazy-pipeline management (`docs/features/ROADMAP.md`:
> "`docs/features/` is the lazy-managed home; `docs/specs/` remains the historical /
> manually-authored spec archive (not under pipeline management)"). A feature-scope spec landed
> there therefore **cannot be driven by `/lazy-batch`** — `depdag.py` resolves a queue
> `spec_dir` to `<repo_root>/docs/features/<spec_dir|id>`, never `docs/specs/`. The step also
> omits the enqueue (queue.json + ROADMAP.md) that a pipeline-managed feature requires. The
> result is a feature deliverable that silently falls out of the pipeline and must be relocated
> + enqueued by hand.

**Status:** Concluded
**Severity:** P2 (process-integrity — a feature-scope harden deliverable is authored in a
directory the pipeline cannot see, so it is silently dropped from `/lazy-batch` until a human
notices and relocates it. No data loss; the cost is manual rework + a stranded, undriven spec.)
**Discovered:** 2026-07-17
**Placement:** docs/bugs/harden-harness-feature-spec-lands-in-unmanaged-docs-specs
**Related:**
- `user/skills/harden-harness/SKILL.md` Step 2.5 (`**Where:**` bullet) — the defective prose.
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — this investigation is the
  Step-2.5 audit-trail artifact for the corresponding hardening round (Round 82).
- `docs/features/spike-pipeline-role/` — the concrete instance: the Round-80 Spike-role harden
  authored this genuine new-capability spec at `docs/specs/spike-pipeline-role/`; it had to be
  manually `git mv`'d to `docs/features/` + given a queue.json (tier 1) + ROADMAP.md row before
  `/lazy-batch` could pick it up (claude-config commit `be8acba4`, 2026-07-17).
- `docs/features/ROADMAP.md` — the authority statement that `docs/specs/` is not pipeline-managed.
- `user/scripts/lazy_core/depdag.py:1453` — `spec_dir` resolves to `docs/features/<spec_dir|id>`.

## Reconstructed route (harden-harness Step 1)

- **Trigger kind:** manual (`/harden-harness <description>`) — operator-directed, observed live
  this session immediately after the operator had to hand-relocate `spike-pipeline-role`.
- **Divergence point:** Step 2.5, the `**Where:**` bullet. For a genuine new feature/capability
  the prose reads: *"Use `/spec` under `docs/specs/` ONLY when the change is a genuine new
  feature/capability whose scope warrants it."* That directs a feature deliverable into the
  archive tree the pipeline does not scan, and says nothing about enqueuing it.
- **Symptom (verified):** the Round-80 Spike-role harden authored a feature-scope spec at
  `docs/specs/spike-pipeline-role/SPEC.md`. `/lazy-batch` never saw it (not under
  `docs/features/`, no queue.json entry, no ROADMAP row). The operator had to relocate +
  enqueue it by hand (commit `be8acba4`).

## Root cause (harden-harness Step 2)

- **Class:** `ambiguous-prose` / `missing-contract`. The Step-2.5 prose actively routes the
  *feature-scope* deliverable to the wrong directory (`docs/specs/`, unmanaged) and carries no
  contract for the enqueue (queue.json + ROADMAP.md) a pipeline-managed feature needs. The
  bug-scope path (`docs/bugs/<slug>/`) is already correct — `docs/bugs/` is lazy-managed.
- **Why it's not merely operator error:** the skill is the authority for where the deliverable
  lands; it explicitly named `docs/specs/`, so the agent followed the contract exactly and
  still produced an un-drivable spec. The fix must make the directory follow **scope**:
  defect → `docs/bugs/`, feature → `docs/features/` (+ enqueue), and explicitly forbid a
  feature-scope deliverable under `docs/specs/`.

## Proposed fix scope

Rewrite the Step 2.5 `**Where:**` bullet (and lightly the `**How to produce it:**` bullet) so
the deliverable directory is chosen by scope:

- **defect / regression / friction** → `docs/bugs/<slug>/SPEC.md` (via `/spec-bug`) — unchanged.
- **genuine new feature / capability** → `docs/features/<slug>/` (via `/spec`) **and enqueue**
  it (queue.json entry + ROADMAP.md row) so `/lazy-batch` can drive it. Never land a
  feature-scope deliverable under `docs/specs/`.
- Preserve the ONE sanctioned `docs/specs/` use for this skill: the
  `docs/specs/turn-routing-enforcement/` hardening-log and design-fork NEEDS_INPUT sentinels —
  those are the harness's own manually-maintained contract/audit area, not a pipeline
  deliverable.

Prose-only change to `SKILL.md`; no script/hook/test behavior changes.

## Related prior class (honesty note — not a spin-off trigger here)

A related "harden deliverable in the wrong directory" incident exists (2026-06-12 split-brain
hardening-log written under the target repo's working tree instead of claude-config — noted in
the Step-4 template). That was a **cross-repo** path-resolution mistake in a **different
component** (Step-4 log path). This one is a **within-claude-config** managed-vs-archive
routing defect in Step 2.5. Different mechanism + different symbol, and this fix is structural
(a scope→directory contract, not a phrase added to a matcher), so it does not meet the
same-class/same-symbol ≥2 bar for an over-fit spin-off.
