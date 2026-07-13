---
kind: implemented
feature_id: state-cli-contract-registry
date: 2026-07-13
provenance: pipeline-gated
derivation: commit-brackets
commits: [3411b45, 84f4a03, b77b5b2, 535a03a]
decisions: []
---

# Implementation Ledger

**What shipped:** The state-script CLI surface (86 flags on `lazy-state.py`, 75 on `bug-state.py`, plus the smaller pipeline tools) has no machine-readable contract: nothing lints skill/component prose against the real argparse surface, so agents invoke flags that don't exist (~46 transcript-mined argparse usage errors across ~25 sessions, including 10 invocations of a `surface_resolver.py --route-mcp-test-tier` flag that exists nowhere in the tree), and the only defenses are prose Gotcha blocks in `user/scripts/CLAUDE.md`. Two coupled deliverables: (a) a committed, introspection-generated `cli-surface.json` registry + a deterministic lint of every `--flag` mention in SKILL.md/component prose against it (+ an optional runtime "did you mean" on argparse error); (b) extraction of the twins' shared flag/handler surface into a parameterized `state_cli.py` builder — 72 of `bug-state.py`'s 75 flags are name-identical to `lazy-state.py`'s and ~half its production lines are verbatim copies — so coupled-pair parity for that surface becomes structural instead of a hand-maintained regex ratchet.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
