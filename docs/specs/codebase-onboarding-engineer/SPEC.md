# Codebase Onboarding Engineer (`/onboard`) — Feature Specification

> A strictly read-only Claude Code skill that gets a developer productive in an unfamiliar codebase fast — by reading source, tracing real execution paths, and stating only code-grounded facts — shipped as one user-level skill with per-repo tailored projections for Cognito Forms and AlgoBooth.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-05-24

**Depends on:** (none)

<!-- No other SPEC.md files exist in claude-config; this skill composes existing _components/ (build-time includes, not spec dependencies). -->

---

## Executive Summary

`/onboard` is a read-only repository-orientation skill. Its job is to shorten time-to-understanding in an unfamiliar codebase: it inventories structure, finds runtime entry points, traces a concrete execution path end-to-end, and explains how the pieces map together — always grounded in source files that were actually inspected, never in inference, opinion, or improvement advice.

The skill is **inspired by** a third-party "Codebase Onboarding Engineer" agent, but it is rebuilt to this repo's conventions and split into a universal method plus per-repo knowledge. There is exactly **one** user-level skill (`user/skills/onboard/`). Repo-specific knowledge is injected at projection/runtime via `.claude/skill-config/onboarding-repo-map.md`, with a framework-agnostic default in `_components/`. Two tailored projections ship in v1: **Cognito Forms** (C# / .NET Framework 4.7.2 monolith + Vue 2.7/TS Nx frontend) and **AlgoBooth** (Rust/Tauri + TS/Vue, web audio).

Two invariants define the skill and are enforced both structurally and in prose:

1. **Read-only** — it cannot mutate the repo. Enforced by an `allowed-tools` whitelist (no `Write`/`Edit`/`NotebookEdit`) plus prose.
2. **Facts only** — it states what the code does, citing files; it does not infer intent, evaluate quality, or recommend changes. Enforced by evidence discipline borrowed from `_components/source-reread.md` and explicit scope-control rules.

## User Experience

### Invocation

- `/onboard` — whole-repo orientation from cold.
- `/onboard <area-or-question>` — scoped orientation, e.g. `/onboard payments flow`, `/onboard where do form submissions get persisted`, `/onboard the model.js → Vue reactivity bridge`.

### Output contract (three levels, always in this order)

1. **1-Line Summary** — one sentence stating what the codebase (or scoped area) is.
2. **5-Minute Explanation** — primary tasks in code, primary inputs, primary outputs, key files (path + responsibility), main code paths (entry → orchestration → core → outputs).
3. **Deep Dive** — type/runtime, entry points with *why each matters*, top-level structure table, key boundaries (presentation / application-domain / persistence-I/O / cross-cutting), responsibilities by file, a numbered concrete code-flow trace with real file paths, how the pieces map together, and a **Files inspected** / **Files not inspected** honesty line.

In a tailored repo, the Deep Dive uses that repo's real entry points and a "if you only read N files first, read these" shortcut.

### What it will not do (visible scope boundaries)

No refactoring plans, no code-review findings, no optimization or "safer edit location" advice, no product-feature commentary, no repository mutation. When inspection is partial, it says exactly which files were and were not read rather than pretending whole-repo comprehension.

## Technical Design

### File layout (no `manifest.psd1` change required)

`user/skills`, and each repo's `.claude/skill-config` + `.claude/skills`, are **directory symlinks** (`DotClaudeDirs` / `Type=Directory` in `manifest.psd1`). New files under them are tracked automatically — no manifest edit, no `setup.ps1` re-run.

```
user/skills/onboard/SKILL.md                                  # universal method + output contract (the skill)
user/skills/_components/onboarding-repo-map.md                # generic, framework-agnostic default (injection fallback)
repos/cognito-forms/.claude/skill-config/onboarding-repo-map.md   # Cognito Forms tailoring (override)
repos/algobooth/.claude/skill-config/onboarding-repo-map.md       # AlgoBooth tailoring (override)
```

### Frontmatter (house style — full conversion from the pasted agent)

The pasted agent's `color` / `emoji` / `vibe` frontmatter and emoji-decorated "Identity/Memory/Personality" sections are dropped (per `CLAUDE.md`: no emojis unless requested; every existing skill uses lean frontmatter). The *substance* — 3-level output, read-only rules, the 5-step method — is preserved.

```yaml
---
name: onboard
description: Read-only codebase onboarding — inventories structure, finds entry points, traces real execution paths, and explains a repo using only code-grounded facts. Use when orienting in an unfamiliar codebase or asking "where do I start / what owns this behavior".
argument-hint: "[area or question, e.g. 'payments flow' or 'where submissions persist']"
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Agent"]
---
```

- `plan-mode: never` — the skill is read-only and produces an explanation, not a change plan.
- `allowed-tools` omits `Write`/`Edit`/`NotebookEdit` — the structural read-only guarantee. `Bash` is included for read-only inspection (`ls`, `find`, `grep`, `git log`); prose forbids mutating commands.
- `Agent` is included to dispatch **Explore** subagents for breadth (see method Step 1/3) per `_components/subagent-partitioning.md`.

### Tooling notes (accurate per-repo)

- **tree-sitter MCP** (global, per `user/CLAUDE.md`) supports **C#, TS, TSX, Vue, JS, JSX — not Rust**. The Cognito projection recommends it for structural queries (`get_file_structure` before reading large files; `find_symbol_usages` / `get_callers` / `get_callees` for blast radius). The AlgoBooth projection recommends it for the **frontend half only**; Rust structure is read via `Read`/`Grep`.
- The `mcp` **capability namespace** in `capabilities.txt` gates *project-MCP-server* components and is unrelated to the global tree-sitter server. Cognito's `capabilities.txt` stays as-is (`no MCP`); this skill does **not** require flipping it on. AlgoBooth already declares `mcp`.
- The skill must **not** run build/test/run tooling (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`, `tauri:dev`, `/mcp-test`) — those build, mutate, or launch the app and violate read-only.

### Method (5 steps — adapted, framework-agnostic in the skill body)

1. **Inventory & classification** — manifests, lockfiles, framework markers, top-level dirs; classify as app / library / monorepo / service / mixed. For broad repos, dispatch parallel **Explore** subagents (`subagent-partitioning.md`) to map regions concurrently and protect context.
2. **Entry-point discovery** — startup files, routers, handlers, CLI commands, workers, package exports — the smallest set of files that define how the system starts.
3. **Execution & data-flow tracing** — follow one concrete path end-to-end: entry → validation → orchestration → core logic → persistence/side-effects → output. Note async/queue/worker hops.
4. **Boundary & ownership analysis** — module seams, shared utilities, public interface vs. implementation detail; surface dead code / misleading names *descriptively*.
5. **Onboarding output** — emit the 3-level output contract.

### Evidence discipline (the "facts only" invariant)

Adapted from `_components/source-reread.md`: never claim a module owns behavior without pointing to the file(s) that implement/route it; quote symbol/route/config names exactly; if it wasn't in the inspected code, don't state it; always close with the **Files inspected / not inspected** line.

### Projection mechanism

The SKILL.md injects the repo map with the repo's standard fallback pattern:

```
!`cat .claude/skill-config/onboarding-repo-map.md 2>/dev/null || cat ~/.claude/skills/_components/onboarding-repo-map.md`
```

- **At runtime** inside a configured repo, `.claude/` is symlinked, so the repo's tailored file resolves; elsewhere it falls back to the generic `_components/` default.
- **At projection time**, `project-skills.py --repos-dir ...` auto-discovers repos with `skill-config/` and emits `skills-projected/<repo>/` with the override resolved, plus `skills-projected/_default/` with the fallback.

### Component inventory ("all of its components")

| Component | New / reused | Role |
|-----------|--------------|------|
| `user/skills/onboard/SKILL.md` | new | The skill: universal method + output contract + read-only/scope rules + injection line |
| `_components/onboarding-repo-map.md` | new | Generic framework-agnostic repo-map default (injection fallback) |
| `repos/cognito-forms/.claude/skill-config/onboarding-repo-map.md` | new | Cognito Forms tailoring (content below) |
| `repos/algobooth/.claude/skill-config/onboarding-repo-map.md` | new | AlgoBooth tailoring (content below) |
| `_components/source-reread.md` | reused (ethos) | Evidence-discipline pattern the "facts only" rule is modeled on |
| `_components/subagent-partitioning.md` / `subagent-launch.md` | reused | Parallel Explore-subagent dispatch for breadth in Step 1/3 |

### Cognito Forms projection — intended content of `onboarding-repo-map.md`

> Multi-tenant form builder. **Backend:** C# on .NET Framework 4.7.2 (SDK-style csproj), Azure. **Frontend:** Vue 2.7 Composition API + TypeScript, Nx monorepo (pnpm).

- **Backend layers & entry points** (dependency flow `Cognito.Services`/`Cognito.Queue*` → `Cognito` → `Cognito.Core`):
  - `Cognito.Core/` — domain models, interfaces, service contracts (zero intra-project deps).
  - `Cognito/` — business logic; `CoreService` is the service-hierarchy root; data access via `StorageContext`; Autofac `Module<T>` DI.
  - `Cognito.Services/` — ASP.NET MVC controllers + Web API; `BaseController`; routing/auth — **the HTTP entry point**.
  - `Cognito.Queue*/` (`Cognito.QueueJob` / `QueueService` / `QueueWorker`) — background jobs.
- **Frontend entry points** (build chain `model.js → vuemodel → element-ui → client/spa`; first builds slow, Nx caches):
  - `Cognito.Web.Client/apps/spa` (`cognito-spa`) — builder/admin (GlobalState, composables, Element UI).
  - `apps/client` (`cognito-client`) — form rendering for end users.
  - libs: `model.js` (reactive entity/type/property/rule framework, ExoModel-based), `vuemodel` (Vue 2 reactivity bridge), `element-ui` (forked), `types` (generated from server), `api`, `utils`.
- **Read these first:** backend — the relevant `Cognito.Services` controller → its `CoreService`/domain service in `Cognito` → `StorageContext`. Frontend — the entity definition in `model.js` → the `vuemodel` bridge → the Vue component/composable in `apps/spa` or `apps/client`.
- **Request trace:** HTTP → `Cognito.Services` controller (`BaseController`) → `Cognito` service (CoreService hierarchy) → `StorageContext` (Azure Table primary / Blob files / Cosmos query-heavy / Redis cache) → JSON response. Background work → queue → `Cognito.Queue*` worker.
- **Tooling:** tree-sitter MCP for C#/TS/Vue structure (use `get_file_structure` before opening large files). **`FormsService.cs` is 9,600+ lines — consult the `forms-service` index skill before reading it.** Do not run `/msbuild` or `/mstest` (read-only).
- **Navigation aids (not substitutes for the code):** domain skills `cognito-auth`, `cognito-payments`, `cognito-entry-indexing`, `cognito-expressions`, `linked-lookups`, `cognito-storage`, `cognito-queue-jobs`, and `knowledge/architecture-overview.md`.
- **Newcomer traps:** the model.js↔backend seam (ExoWeb/ExoModel); Vue **2.7** not Vue 3; C# `LangVersion` varies per project (8 vs 10 — `Core`/`Services` are 10); SDK-style csproj auto-includes `.cs`; two test projects — `Cognito.UnitTests` (unit/MSTest) vs. `Cognito.Forms.UnitTests` (Selenium integration).

### AlgoBooth projection — intended content of `onboarding-repo-map.md`

> Rust/Tauri desktop app with a TS/Vue frontend and Web Audio. Nx workspace. Feature specs/queue live under `docs/features/`.

Because verified depth on AlgoBooth internals is limited, this file lists **known anchors** plus an explicit *verify-on-first-read* instruction (consistent with the skill's evidence-first ethos):

- **Frontend (TS/Vue):** `src/` with UI components in `src/components/` (per `algobooth-ui`); Web Audio code in the frontend (per `web-audio`).
- **Backend (Rust/Tauri):** `src-tauri/` (per `tauri-patterns` auto-invoke); Tauri **commands** form the Rust↔JS IPC boundary; entry typically `src-tauri/src/main.rs` *(verify on first read)*.
- **Specs/roadmap:** `docs/features/<feat>/SPEC.md`, `queue.json`, `ROADMAP.md` — the native home of the `/spec` + `/lazy` workflow.
- **Cross-language trace:** UI event (Vue component in `src/components/`) → Tauri `invoke` IPC → Rust command handler in `src-tauri/` → core Rust logic → result back across IPC → reactive UI update. Audio path runs through Web Audio API nodes.
- **Tooling:** tree-sitter MCP covers the **frontend (TS/Vue/JS) only — not Rust**; read Rust structure with `Read`/`Grep`. Do not run `tauri:dev` or `/mcp-test` (read-only).
- **Newcomer traps:** the Tauri IPC seam (Rust `#[tauri::command]` ↔ JS `invoke`); audio timing; the queue-driven `docs/features` workflow.

## Implementation Phases

- **Phase 1 — Skill + generic default.** Author `user/skills/onboard/SKILL.md` (frontmatter, 5-step method, output contract, read-only/scope rules, injection line) and `_components/onboarding-repo-map.md` (framework-agnostic default).
- **Phase 2 — Cognito Forms projection.** Write `repos/cognito-forms/.claude/skill-config/onboarding-repo-map.md` per the content above.
- **Phase 3 — AlgoBooth projection.** Write `repos/algobooth/.claude/skill-config/onboarding-repo-map.md` per the content above (with verify-on-read hedging).
- **Phase 4 — Validate & project.** Run `python ~/.claude/scripts/project-skills.py` and `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities`; spot-check `skills-projected/_default/onboard`, `skills-projected/cognito-forms/onboard`, `skills-projected/algobooth/onboard` to confirm the right map resolved in each and no injection broke.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| 3-level output produced | run `/onboard` in any repo | output contains 1-Line + 5-Minute + Deep Dive with `file:line` refs and a Files-inspected line | chat output |
| Read-only is structural | run `/onboard` | no `Write`/`Edit` occurs; frontmatter `allowed-tools` excludes them | session tool log; `SKILL.md` frontmatter |
| Cognito map resolves | run `/onboard` in Cognito Forms | Deep Dive names `Cognito.Core/Cognito/Cognito.Services` + `model.js → vuemodel` chain | projected `SKILL.md` / chat output |
| AlgoBooth map resolves | run `/onboard` in algobooth | Deep Dive names `src-tauri` Rust IPC + `src/components` + `docs/features` | projected output / chat |
| Generic fallback works | run `/onboard` in an unconfigured repo | injection falls back to `_components` default; framework-agnostic method runs | `skills-projected/_default/onboard` |
| No review/refactor drift | run `/onboard` | output contains zero improvement/optimization/"better-if" statements | chat output review |
| Projection builds clean | run `project-skills.py` + `lint-skills.py` | no broken injections; per-repo projections differ correctly | script output |

## Open Questions

- **AlgoBooth entry points are partially inferred** (`src-tauri/src/main.rs`, command names). Deepen by running `/onboard` in-repo once and capturing verified anchors *(estimated — verify during Phase 3 / first in-repo run)*.
- **Scoped deep mode** — should `/onboard <area>` auto-fan-out parallel Explore subagents per subsystem? Deferred to a possible v2.
- **More projections** — `strudel`, `housing-locator`, `story` also have `skill-config/`. Out of scope for v1; the injection fallback already gives them the generic map.

## Research References

Phase 2 (Gemini Deep Research) was **skipped at the user's request**. The method draws on internal conventions (`_components/source-reread.md` evidence discipline; `subagent-partitioning.md` for breadth) and uses the third-party "Codebase Onboarding Engineer" agent as inspiration only — its substance was kept, its format (emoji/vibe/personality) discarded per house style.
