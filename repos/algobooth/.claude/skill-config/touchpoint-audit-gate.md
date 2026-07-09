## Touchpoint Audit Gate (MANDATORY — BEFORE DRAFTING PLAN)

### What counts as a "touchpoint"

A **touchpoint** is an **existing source file the planned implementation will modify** — NOT the file you're about to write right now. This distinction matters because this gate is invoked from planning skills (`/spec-phases`, `/spec-phases-batch`, `/plan`, etc.) whose immediate output is a markdown document, while the *plan* inside that document targets source files.

| Skill invoking the gate | Immediate output (IGNORE for audit) | Touchpoints to audit |
|--|--|--|
| `/spec-phases`, `/spec-phases-batch` | `PHASES.md` | Every existing source file listed under "Files likely modified" across all proposed phases, plus any file the SPEC's Technical Design names |
| `/plan` | `plans/<name>.md` | Every existing source file the plan says it will edit |
| `/fix`, `/implement-phase`, ad-hoc edits | The edits themselves | Every existing source file about to be edited |

**Do NOT skip the audit just because the current operation writes a markdown doc.** That is the most common failure mode — see "When to skip" below for the only valid skip cases.

### Collecting touchpoints

1. Enumerate every **existing** source file the plan will modify (paths **relative to the AlgoBooth repo root** — the cwd when npm runs). Sources of truth, in order:
   - SPEC.md "Technical Design" / "Files likely modified" lists, if present
   - The proposed phase structure you just synthesized (each phase's "Files likely modified" list)
   - Any file you grepped/read while analyzing boundaries that the plan will edit
2. Drop entries that don't exist on disk yet (brand-new files have no LOC to grow) — but **keep** them in a separate list for the §Touchpoint Summary so the reader sees them.
3. Pass the existing-file list to the audit:

```bash
npm run audit:touchpoints -- --json <path1> <path2> ... > /tmp/touchpoint-audit.json
```

Parse the output. Identify all entries where `verdict.kind === "block"`.

### If any verdict is `block`

The plan **MUST** include a **"Phase 0: Decomposition"** entry BEFORE any phase that touches a blocked file. (If multiple files block and decompose along different seams, prefer separate Phase 0.a / 0.b sub-phases over one mega-refactor phase.) Document:

- Which files are being decomposed and their current LOC
- The decomposition strategy from `recommendation` (`split-first`, `decompose-store`, etc.)
- The target shape after decomposition (new module boundaries, file names)
- Which subsequent phase picks up the original feature work after decomposition lands
- Testing strategy proving the decomposition is behavior-preserving (snapshot tests, golden outputs, etc.)

**OR** — if decomposition is genuinely out of scope (e.g., the user explicitly wants a hotfix that must touch `voice.rs`), surface the block report to the user via `AskUserQuestion` with these options:

- **Add a decomposition phase** (recommended — preserves long-term health)
- **Acknowledge and proceed without** (records the decision as a deliberate exception in a §Plan Notes section at the bottom of the plan, citing the specific block report)

Do not silently proceed past a `block` verdict.

### If no verdict is `block`

Continue to plan drafting. Warn verdicts are informational — note them in a §Touchpoint Summary table at the top of the plan so the implementer is aware before they start growing the file further.

### When to skip (narrow — read carefully)

Skip ONLY if **both** are true:

- The plan's collected touchpoints list (after the "Collecting touchpoints" step above) is empty or contains only files that do not yet exist on disk, AND
- No SPEC.md/phase text identifies any existing source file as a target

Writing a markdown document (PHASES.md, plans/*.md, SPEC.md updates) is **not** by itself a valid skip reason. If the document plans source edits, audit those source files.

If you do skip, record the skip reason in the plan's §Touchpoint Summary along with the empty-touchpoint evidence ("SPEC names no existing files; all proposed phase targets are new modules X, Y, Z").

### Heuristic note

The audit is regex-based, not AST. Some `block` verdicts may be conservative. The `AskUserQuestion` branch above covers the case where the human disagrees with the block. Document any overrides explicitly in §Plan Notes so the decision is auditable.

### AGPL / IP placement gate (strudel-sidecar/)

**Any new file under `strudel-sidecar/` must be justified against the SPEC's `## AGPL / IP Placement` section** — `strudel-sidecar/` is public AGPL code (`docs/legal/AGPL_PUBLICATION_MANIFEST.md`), so an unjustified file there is a disclosure, not a refactor. This applies to plans (`/write-plan`, `/implement-phase`) AND out-of-band fixes (`/fix`), which land sidecar code just as easily. If the driving SPEC lacks the section, or there is no SPEC (ad-hoc fix), record the justification explicitly in the plan/fix notes — why the code can't be host-side computation over data that already crosses the wire — and honor the coupled updates: a new kind of `audio_event.capnp` payload → `docs/legal/AGPL_ISOLATION.md` updated in the same commit; a new AGPL dependency or any server-side Strudel execution → `AGPL_PUBLICATION_MANIFEST.md` entry first. If the placement can't be justified, surface it (`AskUserQuestion` / `NEEDS_INPUT.md`) instead of silently landing sidecar code.
