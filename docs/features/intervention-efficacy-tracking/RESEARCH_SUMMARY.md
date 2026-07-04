---
kind: research-summary
feature_id: intervention-efficacy-tracking
date: 2026-07-04
source: codebase-survey (cloud session; Gemini research skipped per operator direction)
---

# Research Summary — intervention-efficacy-tracking

Honest survey of every surface the SPEC names, verified against the lane's base
(`harness-telemetry-ledger` LANDED; `friction-kpi-registry` in a concurrent sibling lane).

## Surfaces verified

| SPEC claim | Verified reality |
|---|---|
| `lazy_core.apply_pseudo` at `user/scripts/lazy_core.py:3241` | Confirmed — `def apply_pseudo(` is at line 3241 on this base. The `__mark_complete__`/`__mark_fixed__` branch is ONE shared handler (`elif name in ("__mark_complete__", "__mark_fixed__")`, line ~3978), called by BOTH state scripts' `--apply-pseudo` CLI handlers (`lazy-state.py:10248`, `bug-state.py:6017`) — so a single capture call site inside the branch covers both pipelines by construction. Extra-return-key precedent confirmed: `flipped_phases`, `auto_ticked_rows`, `queue_trimmed`, `roadmap_struck`, `warnings`. |
| Receipt write precedes capture point | Confirmed — `write_completed_receipt(...)` runs at the top of the success path (section (a)); the receipt-noop guard (`existing_receipt ... → _noop()`) runs BEFORE it, so a re-completion never re-captures (idempotency for free). |
| `parse_sentinel` + nested `baseline:` map (deferred empirical check) | **Verified: nested map works.** `parse_sentinel` delegates to `yaml.safe_load` (lazy_core.py:337-377), which parses nested mappings natively. The record keeps the D3 nested `baseline:` map — no flattening needed. Round-trip pinned by a Phase-1 test. |
| Telemetry ledger event shapes (hard dep, deferred empirical check) | **Verified against SHIPPED code, not the sibling SPEC.** Envelope (lazy_core.py:13248-13305): `{"v": 1, "ts": <epoch float>, "run_id": <marker started_at>, "pipeline": "feature"\|"bug", "event": <type>, "item_id": <str\|None>, "data": {…}}`. Run identity = `run_id` (ISO-8601 `%Y-%m-%dT%H:%M:%SZ` → lexical order == chronological). D4-B vocabulary as shipped: `run-start`, `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`, `gate-refusal`, `containment-refusal`. Reader: `read_telemetry_events(paths=None, with_provenance=False)` — reads rotated segments oldest-first then the active file; tolerates torn lines/unknown `v`. Cloud runs flush committed segments to `docs/telemetry/cloud/<run_id colon-stripped>.jsonl` (`flush_cloud_telemetry_segment`) — the evaluator merges those in (the trends-aggregator precedent). |
| `friction-kpi-registry` (soft dep) | Being built CONCURRENTLY in a sibling lane. Treated exactly per the SPEC's soft-dep contract: `event:<type>` targets are fully supported; `kpi:<system>.<kpi-id>` targets are carried verbatim on the record and resolve through a single seam (`_resolve_target_signal` in `efficacy-eval.py`) that returns "unresolvable" for `kpi:` targets in this lane → honest `INCONCLUSIVE (kpi-unresolvable)`, never an error. This lane does NOT read or write `docs/kpi/`. |
| Ad-hoc bug enqueue path | Confirmed — the sanctioned route is `lazy-state.py --enqueue-adhoc --type bug --id … --name … --brief …` (lazy-state.py:10294-10317), which calls `enqueue_adhoc_bug` (lazy-state.py:690): the EXISTING `bug-state.py --enqueue-adhoc` subprocess (with `LAZY_ORCHESTRATOR=1` asserted in the child env — the established hermetic-against-ambient-marker pattern) + `ADHOC_BRIEF.md` seeding. `bug-state.py --enqueue-adhoc` alone takes no `--brief`, so the evaluator uses the `lazy-state.py --type bug` wrapper form. |
| Bug archive layout (recurrence guard layer 1) | `archive_fixed` moves a fixed bug dir to `docs/bugs/_archive/<bug_id>` (collision → `-archived-<date>` suffix; lazy_core.py:5052-5058). Guard layer 1 therefore checks `docs/bugs/reconsider-<id>/` AND any `docs/bugs/_archive/` entry whose name starts with `reconsider-<id>`. |
| Queue opt-in flag precedent | Confirmed — `"autodiscover": true` is read as a TOP-LEVEL sibling of `"queue"` in `docs/features/queue.json` (`_queue_autodiscover_enabled`, lazy-state.py:470). `"interventions": true` mirrors it. The `__mark_complete__` queue trim mutates only `qdata["queue"]`, so the top-level flag survives trims. NOTE: this lane does NOT set the flag in the live `docs/features/queue.json` (orchestrator-owned); tests use fixture queues and the operator/orchestrator flips the live flag. |
| Parity contract | `lazy_parity_audit.py::audit_state_script_parity` checks per-script regexes (`_REORDER_QUEUE_RE`, `_REASSERT_OWNER_RE`, active-repo binding). Capture parity holds by construction (shared `apply_pseudo`); the new `--record-intervention` CLI is added to BOTH scripts and a matching parity regex check is added to the audit (the `--reassert-owner` pattern). |
| End-of-run flush insertion point (deferred empirical check) | **Verified:** `/lazy-batch` §1c.6 item 2 carries the once-per-run incident-scan paragraph ("BEFORE `--run-end`"); `/lazy-batch-cloud` §1c.6 mirrors it at line ~391 with its cloud-divergence table row at ~989. The efficacy-eval flush paragraph lands alongside (after incident-scan, before `--run-end`) in BOTH files. |
| `/harden-harness` Step 4 | Confirmed at `user/skills/harden-harness/SKILL.md:242` — the HARDENING.md round template. The `--record-intervention` invocation is ADDITIVE to the round (per the SPEC: "replacing nothing — additive to its Step 4 log"), with `--id harden-<YYYY-MM>-r<N> --pipeline hardening`. |
| `/lazy-batch-retro` citation step | The retro lives at `user/skills/lazy-batch-retro/SKILL.md` (USER-level, not repo-scoped — the root CLAUDE.md table says repo(algobooth); on-disk reality is `user/skills/`). Step 6d (toolify resurface) is the report-only precedent shape; the efficacy citation lands as Step 6e with the same degrade-gracefully + status-bookend-line contract. |
| Refusal/guard context | `refuse_if_cycle_active` guards `apply_pseudo` at the library boundary (line 3412). The new `--record-intervention` CLI handler is guarded the same way (orchestrator-only op — it writes a committed doc). |

## Spec assumptions that proved wrong / drifted

1. **Retro skill location:** the SPEC's research references imply the retro is AlgoBooth
   repo-scoped (matching the root CLAUDE.md table); on disk it is `user/skills/lazy-batch-retro/`.
   The citation step is added there.
2. **`bug-state.py --enqueue-adhoc --brief`:** D7's sketch names
   `bug-state.py --enqueue-adhoc … --brief …`, but the bug script's enqueue takes no brief; the
   brief-seeding lives in the `lazy-state.py --enqueue-adhoc --type bug` wrapper
   (`enqueue_adhoc_bug`). The evaluator uses that documented `--type bug` form — same shipped
   path, correct flag surface.
3. Nothing else drifted — line anchors for `apply_pseudo` (3241) and the telemetry substrate
   were exact on this base.

## Integration points (implementation targets)

- `user/scripts/lazy_core.py` — constants block, `parse_intervention_hypothesis`,
  `record_intervention` (+ frontmatter serializer + merged telemetry reader), capture call in
  the `__mark_complete__`/`__mark_fixed__` branch.
- `user/scripts/lazy-state.py` + `user/scripts/bug-state.py` — `--record-intervention` CLI
  (+ `--pipeline`, `--shipped-commit`, `--shipped-date`, `--target-signal`,
  `--expected-direction`, `--signal-independence`, `--review-after-runs` flags), reusing `--id`.
- `user/scripts/lazy_parity_audit.py` — `--record-intervention` parity regex.
- `user/scripts/efficacy-eval.py` — NEW standalone evaluator.
- `user/scripts/test_lazy_core.py` (register in `_TESTS`), NEW `user/scripts/test_efficacy_eval.py`.
- `user/skills/lazy-batch/SKILL.md` + `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`
  §1c.6 (coupled-pair mirrored flush paragraph), `user/skills/lazy-batch-retro/SKILL.md` Step 6e,
  `user/skills/harden-harness/SKILL.md` Step 4.
- Docs: root `CLAUDE.md` scripts row, `user/scripts/CLAUDE.md` table row + intervention section,
  NEW `docs/interventions/CLAUDE.md` (record schema + `## Intervention Hypothesis` authoring
  surface).
