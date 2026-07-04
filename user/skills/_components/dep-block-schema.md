## Depends-on Block — Schema & Resolution

The canonical machine-parseable dependency block carried in every `SPEC.md`. Used by `/spec`, `/spec-phases`, `/write-plan`, `/lazy` (Step 4.6), and `/realign-spec` to build a reliable dependency graph and to drive look-back reality checks against completed upstream features.

### Schema (must be exact)

A markdown section named exactly `**Depends on:**`, placed immediately after the SPEC's title/frontmatter and before the first design heading.

Form A — has dependencies:

```
**Depends on:**

- <feature-id> — <kind> — <one-sentence reason>
- <feature-id> — <kind> — <one-sentence reason>
```

Form B — no dependencies:

```
**Depends on:** (none)
```

Rules:

- Separator between feature-id, kind, and reason is the em-dash character `—` (U+2014). Hyphen-minus `-` is invalid.
- `<feature-id>` matches `^[a-z0-9][a-z0-9-]*$` and resolves to a feature directory (see "Upstream resolution" below).
- `<kind>` is one of:
  - **hard** — this feature's design hinges on concrete decisions made when the upstream is implemented (API shape, schema, IPC contract). Downstream consumers MUST reality-check upstream PHASES.md before working this feature.
  - **soft** — needs upstream to exist but not its impl specifics.
  - **composes** — this feature builds atop the upstream as a peer/extension; the upstream is part of the feature's surface area.
- `<reason>` is one sentence. Trailing period optional but should be consistent within a file.
- A TODO marker may follow the block: `<!-- TODO: confirm kind for <feature-id> -->`. Treat as a warning, not an error.

### Parsing protocol

When a skill needs to load the dep block from a SPEC.md:

1. Read the SPEC.md.
2. Locate the line matching `^\*\*Depends on:\*\*` (exact). If absent, treat as `(none)` and warn — the spec predates the schema or violates lint.
3. If the line ends with `(none)` (with optional trailing whitespace), the dep set is empty.
4. Otherwise, read subsequent lines starting with `- ` until a blank line or a new markdown heading. For each:
   - Split on ` — ` (space, em-dash, space). Must yield exactly 3 parts.
   - Validate kind ∈ {hard, soft, composes}.
   - Validate feature-id matches the regex above.
   - Malformed lines: skip with a warning. Do NOT abort — the project's doc-lint catches schema errors; skills are read-only consumers.
5. Return a list of `{feature_id, kind, reason}` records.

### Upstream resolution

Given a `<feature-id>` parsed from a dep line, locate its directory:

1. **Sibling-first:** check `<current-spec-parent>/../<feature-id>/SPEC.md`. If it exists, use that directory.
2. **queue.json fallback (algobooth and similar):** if `docs/features/queue.json` exists at the project root, look up the entry where `id == <feature-id>` and use its `spec_dir` relative to the project root.
3. **Search fallback:** glob `docs/features/**/<feature-id>/SPEC.md`. If exactly one hit, use it. If zero or multiple, warn and skip this dep.

Once the upstream directory is resolved, the following artifacts are available for look-back:

- `<upstream-dir>/SPEC.md` — design contract
- `<upstream-dir>/PHASES.md` — phase-level decisions made during implementation (authoritative for what was actually built; surfaces Implementation Notes)
- `<upstream-dir>/plans/*.md` — implementation plans (cite from `/write-plan`)
- `<upstream-dir>/VALIDATED.md` / `<upstream-dir>/RETRO_DONE.md` — completion sentinels

### Completion check

A feature is "Complete" for reality-check purposes if EITHER:

- Its row in `docs/features/ROADMAP.md` is strikethrough and marked `COMPLETE`, OR
- `<upstream-dir>/SPEC.md` carries `**Status:** Complete`.

Hard deps on incomplete upstreams produce a soft warning but no reality check — there's nothing settled to look back at yet.

### Queue projection (`deps` field — queue-dependency-dag)

The dep block's **hard** deps are additionally projected into the item's `queue.json` entry as a
flat `"deps": ["<id>", ...]` field — the machine-enforced counterpart the state scripts' dep-gate
holds items on (an item whose declared dep is not `Complete`/`Fixed` with a valid receipt is never
dispatched). The projection is **script-owned**: `lazy-state.py --sync-deps --id <id>` (features)
/ `bug-state.py --sync-deps --id <id>` (bugs), invoked by `/spec-phases` Step 1.6 once the SPEC
baseline is locked — never a hand edit. Only `hard` kinds project (soft/composes need the upstream
to *exist*, not be Complete — they stay prose-only); the prose block above remains the SSOT for
kinds and reasons. Same-pipeline bare ids only in v1 — `bug:`/`feature:` prefixes are reserved for
a future cross-pipeline version and are refused. A probe-time drift diagnostic warns when an
entry's queue set diverges from its SPEC hard set (re-run `--sync-deps` to re-project). Editing
this block after phases exist? Re-run the sync so prose and machine state cannot silently drift.

### Skills that consume this schema

| Skill | Reads | Writes |
|-------|-------|--------|
| `/spec` | nothing (authors the block) | the block in SPEC.md |
| `/spec-phases` | upstream PHASES.md (per hard dep) | downstream PHASES.md cross-feature integration notes |
| `/write-plan` | upstream `plans/*.md` (per hard dep on Complete upstream) | downstream plan `## References` |
| `/lazy` Step 4.6 | the block; delegates to `/realign-spec` | nothing directly |
| `/realign-spec` | upstream PHASES.md and `plans/*.md` (per hard dep on Complete upstream) | `plans/realign-<date>.md` |

### Read-only guarantee

No skill that consumes this schema may modify any upstream artifact. The look-back mechanism is strictly read-on-upstream, write-on-downstream. If a skill produces a recommendation that implies upstream changes, surface it to the user — do not act on it.
