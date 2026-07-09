# Cognito.Web.Client — Frontend Monorepo

## Gotchas
- **Vue 2.7** with Composition API — NOT Vue 3 (no `<script setup>`, no Pinia, no `defineComponent` auto-import)

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

## Key Libs
Build chain: `model.js` (reactive entity framework) → `vuemodel` (Vue 2 bridge) → `client`/`spa`. `element-ui` is a **fork** — import from `@cognitoforms/element-ui`, never `element-ui`.

## Server-Generated Types (`libs/types/server-types/`)
TypeScript interfaces auto-generated from C# server models — **committed to source control**. A Debug backend build regenerates them; commit the regenerated files alongside your backend changes (check `git status Cognito.Web.Client/libs/types/server-types/`).

**Discarding a regeneration (git safety):** revert only that path:
```bash
git checkout -- "Cognito.Web.Client/libs/types/server-types"
```
Never use repo-wide `git checkout`/`git clean`/`git reset --hard` for this — it destroys untracked work (newly created, not-yet-committed files) with no recovery.

## Testing Conventions
- Prefer **Vue Testing Library** (`@testing-library/vue`) for behavior tests (element visibility, clicks, user interactions)
- Use **@vue/test-utils** only for prop/data flow tests or internal component mechanics
- VTL version 5 is installed (compatible with Vue 2)
