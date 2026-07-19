# Research — Cycle-Prompt Deflation

**Operator-directed skip-research (2026-07-19).** No external Gemini deep-research pass is
required for this feature. Per the SPEC's Research References, the work is internal harness
plumbing grounded entirely in the claude-config codebase and the 2026-07-19 session-corpus
mining evidence pass:

- The `emit_cycle_prompt` / `@section` prompt-assembly architecture (`lazy_core/dispatch.py`).
- The ~16.8 KB assembled-field ceiling and the ~13–14 KB boilerplate split measured in-repo.
- The `phases-slice-scoped-reads` cautionary precedent (a prose read-mandate that was ignored in
  this exact prompt), motivating the prose→verdict-rule deflation.
- The `lazy-batch-skill-deflation` playbook and its `skill-size-ratchet.py` gate, which this
  feature extends from whole-file skills to the assembled cycle prompt.
- The coupled-pair machinery (`generate-coupled-skills.py` + overlays) the upstream
  `coupled-pair-generation` established, through which every `cycle-base-prompt.md` section edit
  must flow.

All grounding is in-repo and already captured in the SPEC; no external source synthesis is
needed. Proceed directly to PHASES decomposition and planning.
