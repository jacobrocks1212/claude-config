---
kind: adhoc-brief
bug_id: coupled-overlay-drift-gate-not-in-mandatory-gates
enqueued_by: lazy-adhoc
date: 2026-07-19
---

# Ad-hoc bug: Wire generate-coupled-skills.py --check into the mandatory gate list (coupled-overlay drift not gated at authoring/commit time)

generate-coupled-skills.py --check (the coupled-overlay drift gate) is not in the mandatory gate battery, so per-pair overlays silently drifted from their committed hand-authored SKILL.md across 3 commits (ca7f2c8b, f79c1a12, and through Round 114) before being caught mid-run. Round 114's gate list ran the enforced lazy_parity_audit.py but not the advisory generate-coupled-skills.py --check. Durable fix: wire generate-coupled-skills.py --check into the mandatory authoring/commit-time gate battery so overlay drift fails fast. Spun off from harden Round 116 (fix commit 96f938ae).
