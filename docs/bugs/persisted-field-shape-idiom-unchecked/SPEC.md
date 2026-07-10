# Persisted Field Shape Locked Without Idiom Check — Investigation Spec

> Lifecycle-state decisions are optioned by *where the flag lives*, never by *data shape*, and reuse discovery operates at capability granularity only — so 57077 locked an `IsArchived` bool while the codebase's own idiom (`EntityMeta.DateDisabled`, a nullable `[Overwatch]` DateTime) sat unexamined, forcing the Phase-7 rewrite across 9 call sites, snapshots, and typegen.

**Status:** Concluded
**Fixed:** 2026-07-10 — implemented out-of-pipeline (operator-directed subagent orchestration; fix scope in this SPEC)
**Severity:** P2
**Discovered:** 2026-07-10
**Placement:** docs/bugs/persisted-field-shape-idiom-unchecked
**Related:** 57077 case study (Phase 7), `_components/reuse-discovery-protocol.md`

---

## Verified Symptoms

1. **[VERIFIED]** The `/spec` re-baseline Decision 2 menu offered exactly: (A) new `Archived` state on `Organization`, (B) no new state, (C) reuse `VerificationStatus.Disabled` — no `DateTime?` / timestamp option; shape was never on the menu. — Session `42d69d3d` #504.
2. **[VERIFIED]** The operator named the bool himself inside a question about revision cost ("Assuming the new property is something like Organization.IsArchived, then it should correctly be false (default)…?"); the model verified only the no-revision sub-question, and the next session's Explore agents were primed with the bool as fait accompli ("We will add a new `Organization.IsArchived` bool flag"). — `42d69d3d` #506-512; `c78da220` #46.
3. **[VERIFIED]** `EntityMeta.DateDisabled` — the existing nullable-`[Overwatch]`-DateTime lifecycle idiom — appears in ZERO sessions, even though the investigation had grepped date-shaped lifecycle vocabulary ("no IsDeleted/Archived/DateDeleted on Organization"). — `42d69d3d` #491 args; cross-session grep.
4. **[VERIFIED]** Phase 7 rewrote the marker to `DateTime? DateArchived` for reporting ("when was this archived / how long retained" — a bool cannot answer), touching 9 production read/write sites, the OW-schema snapshot, and generated `organization.ts`. — PHASES.md:387-469.

## Reproduction Steps

1. Run `/spec` (with the Cognito reuse-first override or the generic protocol) on a feature adding a persisted lifecycle marker to an entity.
2. Observe Step 1b.7 / `reuse-discovery-protocol.md`: the Reuse Ledger (R1–R6) inventories existing **systems/types/components/conventions** at capability granularity ("does a system for X exist?"); nothing forces a **field-shape** search ("does an analogous field exist, and what shape is it?").
3. Observe the brainstorm decision menus: options enumerate placement/reuse choices; shape (bool vs nullable timestamp vs status enum) is not an axis.

**Expected:** a new persisted lifecycle field is optioned by shape with a cited grep for existing analogues (`Date*`, `Is*` lifecycle fields on core entities), defaulting to timestamp over bool ("a timestamp is a bool plus provenance").
**Actual:** shape defaults to whatever phrasing enters the conversation first; the idiom search never runs. (Skill-audit Q5: capability-level only; NO dedicated provision.)
**Consistency:** structural.

## Evidence Collected

### Serving-path trace (root cause — `traced`)

```
IsArchived bool locked → Phase-7 rewrite
  → user/skills/_components/reuse-discovery-protocol.md:10-57 (R1 capability extraction → R4
      ledger rows → R5 acceptable-new gate) — granularity is CAPABILITY/system; a per-field
      shape precedent has no ledger row category, so DateDisabled never became a search target
                                                                             ← THE FIX SITE
  → user/skills/spec/SKILL.md decision menus — options generated per placement, not shape
      (42d69d3d #504: A/B/C menu with no timestamp option)  [no direct edit needed: the
      protocol addition below feeds the menu via the ledger]
```

Fix-site-on-path: yes — the protocol defines what the discovery searches for; the missing search is why the idiom stayed invisible.

## Proven Findings

1. The information was one grep away and the investigation had already run adjacent greps — this is a missing *checklist item*, not a capability gap.
2. Timestamp-vs-bool is the general case: a timestamp subsumes the bool and carries provenance; the reporting need that forced Phase 7 ("when?") is generically foreseeable.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Reuse discovery protocol | `user/skills/_components/reuse-discovery-protocol.md` | missing field-shape idiom step |

## Fix Scope (locked with operator, 2026-07-10)

Add a compact **field-shape idiom rule** to `user/skills/_components/reuse-discovery-protocol.md` (single writer, single file):

- When the feature introduces a **new persisted field/marker** (especially lifecycle state), the ledger must include a shape row: enumerate shape options (bool vs nullable timestamp vs status enum vs reuse-existing-state), grep the codebase for existing analogues (`Date*`, `Is*`, status-enum lifecycle fields on core entities), and cite the precedent found (or a negative-search trail).
- Default preference: **nullable timestamp over bool** — "a timestamp is a bool plus provenance"; deviating requires a stated reason in the SPEC.
- Name 57077 `IsArchived`→`DateArchived` (vs the extant `EntityMeta.DateDisabled` idiom) as the anti-pattern.

## Open Questions

- (none — fix scope locked)
