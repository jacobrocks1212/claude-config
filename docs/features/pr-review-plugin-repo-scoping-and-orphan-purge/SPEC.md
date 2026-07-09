# PR-Review Plugin Repo-Scoping & Orphan Purge — Feature Specification

> Scope the cognito-pr-review plugin to the Cognito Forms repo so its 14 agents + 7 commands stop loading into every session machine-wide, archive the 6 orphaned v1 agents (+ dead legacy rules doc), and fix the plugin's doc drift.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:** (none)

---

## Executive Summary

The cognito-pr-review plugin is enabled at the **user level** (`user/settings.json` line 145: `"cognito-pr-review@local-tools": true`), so its full registration surface — 14 agents and 7 commands — loads into **every Claude Code session on the machine**, including all AlgoBooth/claude-config/personal-project sessions where the plugin is never used, and (compounding) into every one of the 6–16 subagents each PR review spawns. Session mining (2026-07-09, ~40 review runs) measured every Cognito Forms subagent starting at a ~50–70k-token baseline; the plugin's registry lines are a pure-waste slice of that baseline in every non-Cognito session.

Six of the 14 registered agents are **v1 orphans** — `cognito-architecture`, `cognito-frontend`, `cognito-api-design`, `cognito-behavior`, `cognito-test-coverage`, `review-synthesizer` (57,861 bytes) — referenced by no pipeline command (only `rebuild-agents.md`, `learn-from-pr.md`'s mapping table, the README, and each other; `synthesizer-v2.md` explicitly calls review-synthesizer "legacy reference"). They are not just dead weight: session logs show **three mistaken dispatches** of v1 agents during real reviews (sessions `a5e28058`, `62742c3b`), i.e. the orphans actively cause misrouting. `knowledge/code-review-rules.md` (29,613 bytes) is likewise dead — referenced only by the README as "Legacy reference".

This feature (a) moves plugin enablement to the Cognito Forms repo's `.claude/settings.json` (authored in claude-config at `repos/cognito-forms/.claude/settings.json`), (b) archives the 6 orphan agents + the dead rules doc to `archived/` and purges their rows from `rebuild-agents.md` / `learn-from-pr.md`, and (c) fixes doc drift discovered en route: `plugin.json` and the plugin `CLAUDE.md` claim "95 rules" (actual: **115** across 8 category YAMLs), and the plugin `CLAUDE.md`'s stated `source_weights` values never matched `knowledge/weights.yaml`.

## User Experience

Operator-facing changes only:

- **Non-Cognito sessions** no longer list any `cognito-pr-review:*` agents or `/cognito-pr-review:*` commands — smaller system prompt, no misrouting surface.
- **Cognito Forms sessions** behave identically: all 7 commands and the 8 live agents remain available (enablement resolves from the repo's `.claude/settings.json`).
- **Agent pickers / dispatch** inside reviews can no longer select a v1 orphan (they are unregistered once out of `agents/`).
- `/cognito-pr-review:rebuild-agents` gets faster and simpler — it stops regenerating rule content into five orphan agents nobody dispatches.

## Technical Design

### A. Repo-scoped enablement

1. In `repos/cognito-forms/.claude/settings.json` (claude-config authored, symlinked to the live repo), add:
   ```json
   {
     "enabledPlugins": { "cognito-pr-review@local-tools": true }
   }
   ```
   merged into the existing hooks-bearing settings object.
2. Remove the `"cognito-pr-review@local-tools": true` entry from `user/settings.json`'s `enabledPlugins`.
3. The `extraKnownMarketplaces.local-tools` directory-source definition **stays user-level** — repo settings only flip the enablement bit. (Docs-confirmed 2026-07-09 — see Resolved by Research: project-level `enabledPlugins` resolves against a user-level marketplace, project scope wins over user on conflicts, and enablement is activation-only — content still serves from the shared user-level versioned cache. The A.4 restart-verification remains as the empirical sanity check; the previously-documented fallback is unnecessary.)
4. Session-restart + verification in both a Cognito Forms session (commands/agents present) and a claude-config session (absent).

### B. Orphan purge

1. `git mv` the six orphan agent files from `user/plugins/local-tools/plugins/cognito-pr-review/agents/` to `archived/cognito-pr-review-v1-agents/` (claude-config's deprecation trail), and `git mv` `knowledge/code-review-rules.md` alongside them; add rows to `archived/CLAUDE.md` per house convention.
2. Purge the v1 regeneration instructions from `commands/rebuild-agents.md` (the sections instructing rule-embeds into the five orphans).
3. Re-point `commands/learn-from-pr.md`'s category→agent mapping table at the live consumers (sweep + the two checker agents).
4. Prune README.md references.
5. Bump plugin version (the live plugin loads from the versioned cache `~/.claude/plugins/cache/local-tools/cognito-pr-review/<version>/` per `installed_plugins.json` — an unbumped cache would keep serving the orphans; see Related bug `pr-review-plugin-cache-split-brain-freezes-weights`).

### C. Doc-drift fixes

- `plugin.json` description + `CLAUDE.md` "Knowledge" section: "95 rules" → "115 rules across 8 categories" (verified 2026-07-09: api-design 9, code-consistency 24, csharp-architecture 25, frontend-vue 16, performance 10, security 5, template-binding 4, testing 22).
- Plugin `CLAUDE.md` Knowledge section: replace the stale hardcoded `source_weights` values (`investigation 0.9 / intrafile 0.7 / reuse 0.7`) with a pointer to `knowledge/weights.yaml` as the live source (no literal values — they drift by design under calibration).

## Implementation Phases

1. **Phase 1 — Repo-scoped enablement.** Settings edits (A.1–A.3), restart-verification in both repo contexts (A.4). Deliverable: plugin absent from non-Cognito sessions, present in Cognito Forms sessions.
2. **Phase 2 — Orphan archive + doc purge.** B.1–B.5 (archive moves, rebuild-agents/learn-from-pr/README purge, version bump). Deliverable: 8 registered agents, `/rebuild-agents` regenerates only live agents.
3. **Phase 3 — Doc-drift fixes.** C (rule count, source_weights pointer). Deliverable: plugin docs match reality; `grep -c 'id:' knowledge/rules/*.yaml` total equals the documented count.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Plugin absent outside Cognito Forms | Start a session in claude-config | No `cognito-pr-review:*` agents in the available-agents list; no `/cognito-pr-review:*` commands | Session system-prompt agent/command listing |
| Plugin present in Cognito Forms | Start a session in the Cognito Forms repo | All 7 commands + 8 live agents listed | Session listing in that repo |
| Orphans unregistered | Any session post-change | No `cognito-pr-review:cognito-architecture` (etc.) in agent list; files under `archived/cognito-pr-review-v1-agents/` | Agent list + `git log --follow` on moved files |
| rebuild-agents regenerates only live agents | Run `/cognito-pr-review:rebuild-agents` | No writes to archived agent files; sweep.md (and live checkers) regenerated | Command output + `git status` |
| Doc counts truthful | `grep -c '\- id:' knowledge/rules/*.yaml` | Sum equals the count stated in plugin.json/CLAUDE.md | Shell check |
| Baseline context drop (KPI) | mine-sessions digest over non-Cognito sessions pre/post | `turn1-baseline-ctx-tokens-noncognito` decreases | `digest_sessions.py` first-ctx column |

## KPI Declaration

```json
{
  "id": "pr-review-noncognito-baseline-ctx",
  "system": "cognito-pr-review",
  "title": "Turn-1 baseline context in non-Cognito sessions",
  "friction": "The globally-enabled plugin loads 14 agents + 7 commands into every session on the machine, inflating the startup context baseline (and every subagent's) in repos where the plugin is never used.",
  "signal": {
    "source": "session-log-mining",
    "selector": "turn1-baseline-ctx-tokens-noncognito"
  },
  "unit": "tokens",
  "direction": "down-is-good",
  "baseline": {
    "value": null,
    "captured_at": null,
    "window": "90d",
    "provenance": "pending"
  },
  "band": null,
  "review_by": "2026-10-01",
  "repo_scope": "machine-global",
  "notes": "Measured on demand via mine-sessions digest_sessions.py first_ctx over non-Cognito-Forms project dirs. No automated collector — compute renders honest NO-DATA until mined. Baseline capture: median first_ctx across sessions started in the window, excluding Cognito Forms project dirs."
}
```

## Resolved by Research (2026-07-09)

- **Repo-level enablement vs user-level marketplace — CONFIRMED supported** (Claude Code docs: settings precedence + plugins reference). Project `.claude/settings.json` `enabledPlugins` resolves against a user-level `extraKnownMarketplaces` definition; precedence is Managed > Local > Project > User (project beats user on conflicts, no merge). With the user-level entry removed and the repo-level entry `true`, sessions in other repos stop loading the plugin's agents/commands. Enablement is an **activation flag only** — content still serves from the single shared user-level versioned cache (`installed_plugins.json` unchanged), so this feature does NOT resolve the cache split-brain bug; version bumps are still how content edits propagate.
- **No serve-from-source mode exists** for marketplace plugins (the cache is always the serving location). Docs offer `--plugin-dir` (per-session) and `@skills-dir` in-place plugins as the in-place-loading alternatives — recorded as candidate fix directions on bug `pr-review-plugin-cache-split-brain-freezes-weights`.

## Locked Decisions

| # | id | Decision | Decided |
|---|----|----------|---------|
| 1 | learn-from-pr-mapping | Re-point the category→agent table at the live consumers, keyed by rule category. Categories are also the shard unit under `pr-review-sweep-rule-sharding-and-read-dedup` (category-level locked 2026-07-09), so the table is 1:1 with shards with no extra mapping layer | 2026-07-09 — mechanical, recommended option |

## Open Questions

(none — the `rebuild-agents.md` edit conflict with the sharding feature is machine-enforced: `pr-review-sweep-rule-sharding-and-read-dedup` declares a hard dep on this feature)

## Research References

No external research phase (skipped per operator direction 2026-07-09). Evidence base, gathered in-session:

- Session mining of ~40 review runs (Cognito Forms project dirs): subagent baseline ctx ~50–70k; three mistaken v1-agent dispatches (`cognito-architecture`, `cognito-frontend`, `cognito-test-coverage`).
- Internals audit with file:line citations: orphan reference graph (only rebuild-agents.md / learn-from-pr.md / README), `synthesizer-v2.md:226` "legacy reference"; byte counts verified 2026-07-09.
- Settings verification: `user/settings.json:145` enablement; `extraKnownMarketplaces.local-tools` directory source; `repos/cognito-forms/.claude/settings.json` currently hooks-only.
