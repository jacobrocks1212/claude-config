# Cognito.Web.Client — Frontend Monorepo

## Gotchas
- **Vue 2.7** with Composition API — NOT Vue 3 (no `<script setup>`, no Pinia, no `defineComponent` auto-import)
- Nx project names differ from directory names — use `npx nx show projects` to list
- Build dependency chain: `model.js` -> `vuemodel` -> `client`/`spa` (first build is slow)
- TypeScript strict mode enabled

## Nx Project Name Mapping
| Directory | Nx Project Name |
|-----------|----------------|
| `apps/spa` | `cognito-spa` |
| `apps/client` | `cognito-client` |
| `apps/marketing` | `@cognitoforms/marketing` |
| `libs/model.js` | `@cognitoforms/model.js` |
| `libs/vuemodel` | `@cognitoforms/vuemodel` |
| `libs/element-ui` | `@cognitoforms/element-ui` |
| `libs/types` | `@cognitoforms/types` |
| `libs/api` | `@cognitoforms/api` |
| `libs/utils` | `@cognitoforms/utils` |

## Apps
- **spa** — Form builder and admin interface (see `apps/spa/CLAUDE.local.md`)
- **client** — Form rendering for end users (see `apps/client/CLAUDE.local.md`)
- **marketing** / **website** — Marketing/public website (Nx: `@cognitoforms/marketing`)

## Key Libs
- **model.js** — Entity/Type/Property/Rule reactive model framework (see `libs/model.js/CLAUDE.local.md`)
- **vuemodel** — Vue 2 reactivity bridge for model.js (see `libs/vuemodel/CLAUDE.local.md`)
- **element-ui** — Forked Element UI components
- **types** — Generated TypeScript types from server models (see below)
- **api** — API client services
- **utils** — Shared utilities

## Server-Generated Types (`libs/types/server-types/`)
TypeScript interfaces auto-generated from C# server models. **These are committed to source control.**

When backend models change (in `Cognito.Core/Model/` etc.):
1. Backend build triggers type regeneration
2. Changes appear in `libs/types/server-types/`
3. **Commit these changes alongside your backend changes**

Check for generated type changes:
```bash
git status Cognito.Web.Client/libs/types/server-types/
```

**Discarding a regeneration (git safety):** A Debug build regenerates `Cognito.Web.Client/libs/types/server-types/**/*.ts` from the C# server types. To discard that regeneration, revert only that path:
```bash
git checkout -- "Cognito.Web.Client/libs/types/server-types"
```
Never use repo-wide `git checkout`/`git clean`/`git reset --hard` for this — it destroys untracked work (newly created, not-yet-committed source/test files) with no recovery.

## Package Manager
pnpm (not npm/yarn). Use `pnpm install` for dependencies.

## Testing
```bash
npx nx test <project-name> -- --testPathPattern="<pattern>" --no-coverage
```

## Testing Conventions
- Prefer **Vue Testing Library** (`@testing-library/vue`) for behavior tests (element visibility, clicks, user interactions)
- Use **@vue/test-utils** only for prop/data flow tests or internal component mechanics
- VTL version 5 is installed (compatible with Vue 2)

---

## Maintaining This Document

Update this file when:
- Adding new architectural patterns or service hierarchies
- Discovering non-obvious gotchas that would trip up future developers
- Renaming or restructuring directories/files mentioned here

Do NOT add: version numbers, line numbers, test counts, or other specifics that change frequently.
