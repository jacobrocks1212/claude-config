# `generate-coupled-skills.py --check` (coupled-overlay drift gate) not in the mandatory gate battery — Investigation Spec

> The overlay-drift gate exists but is not wired into the mandatory authoring/commit-time gate battery, so per-pair overlays silently drifted from their committed hand-authored SKILL.md across three commits before being caught reactively mid-run.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-19
**Fixed:** 2026-07-19
**Fix commit:** 62c108bc
**Placement:** docs/bugs/coupled-overlay-drift-gate-not-in-mandatory-gates
**Related:** `docs/bugs/_archive/coupled-overlays-drift-from-committed-skills/` (the instance fix that reconciled the drift and spun THIS durable fix off — fix commit `96f938ae` / `b6289e4b`); `coupled-pair-generation` (PROVISIONAL) feature; CLAUDE.md "Coupled Skill Pairs" table; `.claude/skill-config/gate-battery.json`; `.claude/skill-config/quality-gates.md`

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[REPORTED]** Per-pair coupled-skill overlays drifted from their committed hand-authored SKILL.md across three commits (`ca7f2c8b`, `f79c1a12`, and Round 114's `4ba985f4`) with no gate failing, until surfaced reactively mid-run. — source: the archived sibling bug `coupled-overlays-drift-from-committed-skills/SPEC.md` (commit-bisect evidence, verified there by direct `git checkout` + `--check` at each commit).
2. **[VERIFIED]** The mandatory gate battery run by harden rounds and feature commits (`.claude/skill-config/gate-battery.json`) contains 7 gates including `parity-audit` (`lazy_parity_audit.py`) but does NOT contain a `generate-coupled-skills.py --check` gate. — confirmed by direct read of the manifest (7-row `gates` array, no drift-gate row).
3. **[VERIFIED]** `generate-coupled-skills.py --check` is a real, exit-coded drift gate (exit 0 ok / 1 drift / 2 malformed) and currently exits 0 on the committed tree (the instance drift was reconciled by the sibling bug). — confirmed by direct run: `coupled-pair generation: all pairs byte-identical (fresh)  EXIT=0`.

## Reproduction Steps

1. Read `.claude/skill-config/gate-battery.json` — observe the `gates` array has 7 entries; none invokes `generate-coupled-skills.py`.
2. Read `.claude/skill-config/quality-gates.md` — observe the "Lazy skill-family changes" / "Mixed / feature completion" gate lists name `lazy_parity_audit.py` but never `generate-coupled-skills.py --check`.
3. Edit a canonical or derived coupled SKILL.md (e.g. `user/skills/lazy-batch/SKILL.md`) WITHOUT re-extracting the matching overlay, then run the full battery (`python3 user/scripts/gate-battery.py` or the 7 gates individually).
4. Observe the battery passes green — the overlay drift is invisible to it.
5. Independently run `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` — observe it (would) report DRIFT and exit 1, proving the gate that WOULD catch it is simply not in the mandatory list.

**Expected:** overlay drift fails the mandatory authoring/commit-time gate battery (fast-fail at commit time), exactly as `lazy_parity_audit.py` drift does.
**Actual:** overlay drift is only caught by the advisory, out-of-band `generate-coupled-skills.py --check`, which no gate runs — so drift lands uncaught and surfaces reactively mid-run.
**Consistency:** deterministic — the gate is structurally absent from the battery manifest.

## Evidence Collected

### Source Code

The mandatory gate battery is fully manifest-driven:

- **`.claude/skill-config/gate-battery.json`** — the single source of truth for what the battery runs. Its `gates` array (7 rows) includes `parity-audit` (`python3 user/scripts/lazy_parity_audit.py --repo-root .`) but has NO row invoking `generate-coupled-skills.py`.
- **`user/scripts/gate-battery.py`** — `_load_manifest()` reads exactly `<toplevel>/.claude/skill-config/gate-battery.json` (`gate-battery.py:154`), `main()` loads its `gates` (`:352`) and runs `for gate in gates` (`:363`) — i.e. the battery runs *precisely* the manifest's gates and nothing more. A gate absent from the manifest never runs.
- **`.claude/skill-config/quality-gates.md`** — the PROSE gate list injected into skills. Its "Lazy skill-family changes" (`:18`) and "Mixed / feature completion" (`:24`) sections name `lazy_parity_audit.py --report` as the coupled-pair check but never mention `generate-coupled-skills.py --check`, so a human/agent following the prose gates also never runs the drift gate.

### Related Documentation

- The archived sibling bug `docs/bugs/_archive/coupled-overlays-drift-from-committed-skills/SPEC.md` proved the class in full: three commits edited coupled SKILL.md files without re-extracting overlays; the drift was NOT caught because "the mandatory gate list run by harden rounds and feature commits includes `lazy_parity_audit.py` (the ENFORCED coupled-pair audit) but NOT `generate-coupled-skills.py --check` (the advisory overlay-drift gate)." It fixed the INSTANCE (`--extract` to reconcile the overlays) and explicitly front-enqueued THIS bug for the durable prevention.
- The root `CLAUDE.md` "Coupled Skill Pairs" note and the `coupled-pair-generation` feature both flag the generator as PROVISIONAL — the hand-authoring discipline is load-bearing and the generator is a drift *gate* (`--check`), NOT a replacement authoring workflow. That is precisely why the `--check` gate must run mechanically: the discipline is human and therefore fallible.

### Git History

Three commits established the drift (from the sibling bug's bisect): `ca7f2c8b` (introduced `lazy-bug-batch` + `lazy-batch-cloud` drift), `f79c1a12` (introduced `lazy-cloud` drift), `4ba985f4` (Round 114, kept `lazy-bug-batch` drift). All three passed their gates because the drift gate was not among them.

## Theories

### Theory 1: The drift gate is simply not registered in the manifest battery
- **Hypothesis:** `generate-coupled-skills.py --check` catches coupled-overlay drift but is absent from `.claude/skill-config/gate-battery.json` (and unmentioned in `.claude/skill-config/quality-gates.md`), so no authoring/commit-time gate ever runs it, letting drift land uncaught.
- **Supporting evidence:** the manifest has 7 gates, none invoking `generate-coupled-skills.py` (verified by read); the runner runs exactly the manifest's gates (`gate-battery.py:154/352/363`); the prose gate list omits it (`quality-gates.md`); the sibling bug's proven root cause names this exact gap.
- **Contradicting evidence:** none.
- **Status:** Confirmed.

## Proven Findings

**Root cause (`traced`).** The mandatory authoring/commit-time gate battery is manifest-driven, and the manifest omits the coupled-overlay drift gate.

Serving-path trace (surface → source), each hop cited `file:line`:

```
symptom: coupled-overlay drift lands at commit time with no gate failing
  → the gate battery runs ONLY the manifest's gates    user/scripts/gate-battery.py:363  (for gate in gates)
  → gates loaded from the manifest                      user/scripts/gate-battery.py:352  (_load_manifest)
  → manifest read from a fixed path                     user/scripts/gate-battery.py:154  (.claude/skill-config/gate-battery.json)
  → the manifest's 7-row gates array                    .claude/skill-config/gate-battery.json:3-11
       ← has `parity-audit` (line 7) but NO `generate-coupled-skills.py --check` row  ← the fix site
  (secondary prose surface, same omission)              .claude/skill-config/quality-gates.md:18,24
```

**Fix-site-on-path:** the fix — adding a `generate-coupled-skills.py --check` gate row to `.claude/skill-config/gate-battery.json` (and naming it in the `quality-gates.md` coupled-pair prose) — changes the exact artifact `_load_manifest` reads to decide what the battery runs. The changed node is ON the traced serving path (it is *consumed* by the runner's gate loop), satisfying the fix-site-on-path rule. The cause is not runtime-coupled: it is a deterministic static config read, confirmed by inspecting the manifest and the runner source.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Mandatory gate battery manifest | `.claude/skill-config/gate-battery.json` | Missing the drift-gate row — the primary fix site. |
| Prose gate list | `.claude/skill-config/quality-gates.md` | Coupled-pair prose omits the drift gate; a human/agent following it never runs `--check`. |
| The drift gate itself | `user/scripts/generate-coupled-skills.py` (`--check`) | Already correct and exit-coded (0/1/2); consumed by the fix, not modified. |
| Doc-drift/CLI-surface consistency | root `CLAUDE.md`, `user/scripts/CLAUDE.md` | May need a note that the drift gate is now in the mandatory battery (verify `doc-drift-lint.py` + `cli-surface-lint.py` still clean after the manifest edit). |

## Open Questions

- None blocking. Fix scope is well-bounded: add a `generate-coupled-skills.py --check` gate to the battery manifest and reference it in the coupled-pair prose gate list. Planning (`/plan-bug`) will decide the exact gate `id`/`cmd` and whether the `quality-gates.md` prose update warrants its own work unit.
