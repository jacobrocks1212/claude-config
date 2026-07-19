---
kind: gate-verdict
feature_id: park-provisional-parks-claude-config-auto-generated-stubs
gate_version: 1
date: 2026-07-19
scope_hit: [user/scripts/lazy_core/docmodel.py, user/skills/_components/sentinel-frontmatter.md]
checks:
  overfit: pass
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: net-new — adds a narrow claude-config-scoped carve-out (`_auto_generated_carveout_applies` + `_sentinel_repo_is_claude_config`) to `provisional_eligibility`; retires no existing rule. It pays for itself by removing per-run operator toil (auto-accepting machine-generated triage-stub recommendations that would otherwise all park), a deterministic net reduction in decisions surfaced.
---

## Adversarial answers

### overfit
`harness-gate.py --staged` reported `overfit: pass` (no evidence). The carve-out keys on a STRUCTURAL provenance pair (`auto_generated: true` + `auto_generated_origin` ∈ a closed set `{canary-revert, incident-capture}`) plus a repo discriminator (`manifest.psd1` + `user/settings.json`), NOT on any incident-shaped literal or id prefix. **Nearest recurrence this rule does NOT catch (by design):** a NEW auto-generated origin (say a future `adhoc-toolify` enqueuer) would NOT be rescued until its tag is added to `_AUTO_GENERATED_HARNESS_ORIGINS` — deliberate: a new machine origin is an explicit, reviewable one-line addition, never a silent id-pattern match. The rule keys on declared machine provenance, so it can never accidentally rescue an operator-authored stub (which never carries the marker).

### tautology
Not a self-emitted-signal change. The efficacy signal for this fix is operator-toil / park volume on `--park-provisional` runs (independent of what this change emits). If this change were broken, the metric would show either (a) auto-generated stubs STILL all parking (carve-out never fires — regression) or (b) a genuine operator stub_origin sentinel being auto-accepted (carve-out over-fires — a correctness bug the `_still_parks` / `_outside_claude_config_parks` regression tests pin). Both are observable, so the change is falsifiable.

### gate_weakening
`harness-gate.py --staged` reported `gate_weakening: pass`. No gate is removed or softened: the general `stub_origin` fail-closed exclusion stands verbatim for every non-carve-out case. The carve-out is ADDITIVE and fail-CLOSED (any missing/malformed marker piece ⇒ the exclusion still applies). No `def test_*` deleted, no numeric threshold changed, no denial/`refuse_*`/`exit 3` removed, no exemption-set membership added to a security/integrity allow-list — the closed origin set is a NEW structural constant, not a weakening of an existing gate.

### complexity
Net-new (see `retires:` above). Two small pure helpers (`_sentinel_repo_is_claude_config`, `_auto_generated_carveout_applies`) + one closed constant + one branch inside the existing `stub_origin` check. The added surface pays for itself by eliminating recurring operator decisions on machine-generated triage noise (observed: 4 canary stubs parked in one run), and is covered by four new regression tests (eligible-in-claude-config / operator-stub-still-parks / outside-claude-config-parks / unrecognized-origin-parks).
