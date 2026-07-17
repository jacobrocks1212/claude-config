# Cognito.Web.Client — Frontend Monorepo

## Gotchas
- Vue 2.7 with Composition API — NOT Vue 3

## Key Libs
Build chain: `model.js` (reactive entity framework) → `vuemodel` (Vue 2 bridge) → `client`/`spa`. `element-ui` is a **fork** — import from `@cognitoforms/element-ui`, never `element-ui`.

## Server-Generated Types
See `libs/types/CLAUDE.local.md` for the regeneration workflow. Git safety when discarding a bad regeneration: revert only that path (`git checkout -- "Cognito.Web.Client/libs/types/server-types"`) — never repo-wide `git checkout`/`git clean`/`git reset --hard`, which destroys untracked work with no recovery.

## Testing Conventions
Prefer Vue Testing Library over `@vue/test-utils` for behavior tests; see `.agents/agent-docs/testing.md` for the full verification-command decision table. VTL version 5 is installed (compatible with Vue 2).

Maintenance: record non-obvious gotchas and pattern/structure changes here; do NOT add version numbers, line numbers, or test counts.
