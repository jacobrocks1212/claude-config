<!-- AlgoBooth repo cycle-prompt addenda.

     PURPOSE: repo-specific instructions the Python emitter
     (lazy_core.emit_cycle_prompt) appends to every assembled cycle_prompt —
     AFTER the base sections, BEFORE the loop block — token-bound and
     residue-checked exactly like the base template. This is the SANCTIONED
     home for repo-specific cycle guidance: orchestrators must NEVER hand-append
     to cycle_prompt (a live orchestrator hand-spliced the audio gate on
     2026-06-11; that path is now closed).

     GRAMMAR: identical @section grammar + selection semantics as
     ~/.claude/skills/_components/lazy-batch-prompts/cycle-base-prompt.md — see
     that file's header for the marker shape, the (pipeline, mode, skills)
     selection rule, and the 14 bindable {tokens}. A section is appended IFF its
     pipelines / modes / skills filters match the cycle. Any {…} that is not one
     of the 14 base tokens is residue the emitter REFUSES on (naming THIS file) —
     use <angle-bracket> placeholders for non-token braces. Everything before the
     first @section marker (this comment) is metadata and is NEVER emitted.
-->

<!-- @section audio-invariants pipelines=feature,bug modes=workstation,cloud skills=execute-plan,retro-feature,mcp-test -->
Audio invariants (AlgoBooth HARD requirement — when this cycle touches audio DSP):
  - Editing ANY file under `crates/audio-engine/src/` (voice, callback, dattorro,
    convolution, ...) → READ `crates/audio-engine/INVARIANTS.md` BEFORE editing,
    including the ArcSwap Guard-across-`Arc<dyn Trait>` NO-OP invariant (a Guard
    obtained through a trait-object boundary is NOT zero-copy — use `load_full()`).
  - Every NEW DSP module MUST add a §10.1 row to `INVARIANTS.md` AND a
    `crates/audio-engine/tests/lint_baselines.rs::HOT_PATH_FILES` entry, at the SAME
    commit that introduces the module.

<!-- @section over-cap-gate-decomposition pipelines=feature,bug modes=workstation,cloud skills=execute-plan,retro-feature -->
Over-cap gate decomposition (AlgoBooth — the concrete case of the turn-end over-cap rule):
  The aggregate `npm run qg -- ts` routinely EXCEEDS the ~10-min Bash cap → the harness
  auto-backgrounds it and your process tree is torn down at turn end (a resultless pause).
  Do NOT run the aggregate `npm run qg -- ts` from a cycle subagent, and never
  `run_in_background` a long gate. Run its FOUR under-cap sub-gates SYNCHRONOUSLY in the
  FOREGROUND instead — the SAME npm scripts (`run_ts_gates` in `scripts/quality-gate.sh`):
    - `npm run type-check`   (vue-tsc --noEmit)
    - `npm run lint`         (eslint)
    - `npm run test:run`     (vitest)
    - `npm run build`        (vue-tsc && vite build)
  These four AND ONLY these four are the `ts` aggregate (the `qg:*` lint/ratchet checks belong
  to OTHER groups — `arch`, `docs` — NOT `ts`), so foreground-running them runs the SAME checks
  without skipping or weakening any gate; confirm membership against `run_ts_gates` if it may
  have changed. The heavy Rust/sidecar gates (`npm run qg -- rust` / `-- sidecar`) are
  queue-routed via the machine build queue (the `qg-rust` / `qg-sidecar` skills) — their
  sanctioned over-cap handling, distinct from this TS-gate foreground decomposition.
