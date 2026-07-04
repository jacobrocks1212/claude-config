# CLAUDE.md — docs/features/

Feature specs for the harness itself, driven by the `/lazy` feature pipeline. Each `<slug>/` is
one work item that `lazy-state.py` walks from spec to completion. **The state machine reads these
files; it never asks the conversation** — so the on-disk contracts are load-bearing: a malformed
sentinel or a hand-flipped status corrupts the machine's view of the world. `lazy-state.py` +
`user/scripts/CLAUDE.md` are the authority; this file is orientation.

## Layout

```
docs/features/
├── ROADMAP.md          # human-facing row per feature
├── queue.json          # ordering + flags; autodiscover:true also picks up on-disk dirs;
│                       # optional per-entry deps:["<id>"] = machine-enforced hard deps (dep-gate)
└── <slug>/             # kebab-case; one feature
    ├── SPEC.md         # the Status: line is the state machine's truth
    ├── RESEARCH.md / RESEARCH_SUMMARY.md
    ├── PHASES.md
    ├── plans/          # implementation-plan files
    └── <sentinels>     # NEEDS_INPUT.md, BLOCKED.md, VALIDATED.md, COMPLETED.md, ...
```

## Lifecycle

```
spec → research → phases → plan → implement → retro → MCP validation → mark-complete
```

`mark-complete` writes a `COMPLETED.md` receipt and flips `Status → Complete`. **A `Complete`
status with no receipt is a hard error** — completion is receipt-gated by the integrity gate
inside `__mark_complete__`. `Superseded` is exempt.

## Conventions

- Slug dirs and `queue.json` ids are kebab-case.
- **`deps` is script-owned** (queue-dependency-dag): never hand-edit it — `lazy-state.py
  --sync-deps --id <id>` projects the SPEC `**Depends on:**` block's hard deps into it
  (`/spec-phases` Step 1.6 runs this). The dep-gate holds an entry until each dep is
  `Complete` with a `COMPLETED.md` receipt; a dangling/Superseded dep BLOCKs the dependent;
  a cycle refuses every probe at load.
- SPEC / sentinel / plan frontmatter follows `user/skills/_components/sentinel-frontmatter.md` —
  keep it valid; the state machine parses it.
- **Don't hand-write completion sentinels** — the gates write them. (A stray/misnamed `BLOCKED*`
  file is rejected by a write hook.)

## features vs specs vs bugs

- `docs/features/` — items in the lazy **feature** pipeline (this dir).
- `docs/specs/` — harness design specs implemented **outside** the lazy queue (see its CLAUDE.md).
- `docs/bugs/` — the lazy **bug** pipeline (`bug-state.py`; see its CLAUDE.md).
