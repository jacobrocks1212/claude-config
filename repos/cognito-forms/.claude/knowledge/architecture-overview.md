# Cognito Forms Architecture Overview

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Cognito.Services                          │
│            (ASP.NET MVC Controllers, Web API)                │
│                           ↓                                  │
├─────────────────────────────────────────────────────────────┤
│                       Cognito                                │
│         (Business Logic, CoreService, Data Layer)            │
│                           ↓                                  │
├─────────────────────────────────────────────────────────────┤
│                    Cognito.Core                              │
│      (Domain Models, Interfaces, Service Contracts)          │
└─────────────────────────────────────────────────────────────┘
```

### Backend Layers

| Layer | Project | Responsibility | C# Version |
|-------|---------|----------------|------------|
| **Domain** | `Cognito.Core` | Models, interfaces, service contracts | C# 10.0 |
| **Business Logic** | `Cognito` | CoreService, service implementations, data access | C# 8.0 |
| **Web/API** | `Cognito.Services` | ASP.NET MVC controllers, routing, auth | C# 10.0 |
| **Jobs** | `Cognito.Queue*` | Background processing, queue workers | C# 8.0 |

### Dependency Flow

```
Cognito.Services → Cognito → Cognito.Core
       ↓              ↓
Cognito.Queue*  →  Cognito  → Cognito.Core
```

- **Cognito.Core**: Zero dependencies on other Cognito projects
- **Cognito**: Depends only on Cognito.Core
- **Cognito.Services/Queue**: Depend on Cognito and Cognito.Core

## Frontend Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Cognito.Web.Client                          │
│  ┌─────────────┐  ┌─────────────┐                           │
│  │    spa      │  │   client    │   (Vue 2.7 Apps)          │
│  └──────┬──────┘  └──────┬──────┘                           │
│         └────────┬───────┘                                  │
│                  ↓                                          │
│  ┌─────────────────────────────┐                            │
│  │         vuemodel            │   (Vue Reactivity Bridge)  │
│  └──────────────┬──────────────┘                            │
│                 ↓                                           │
│  ┌─────────────────────────────┐                            │
│  │         model.js            │   (Entity Framework)       │
│  └─────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

### Frontend Apps

| App | Nx Project | Purpose |
|-----|------------|---------|
| `apps/spa` | `cognito-spa` | Form builder and admin interface |
| `apps/client` | `cognito-client` | Form rendering for end users |
| `apps/marketing` | `@cognitoforms/marketing` | Marketing pages |

### Frontend Libs

| Lib | Nx Project | Purpose |
|-----|------------|---------|
| `libs/model.js` | `@cognitoforms/model.js` | Reactive entity/type/property/rule framework |
| `libs/vuemodel` | `@cognitoforms/vuemodel` | Vue 2 reactivity bridge for model.js |
| `libs/element-ui` | `@cognitoforms/element-ui` | Forked Element UI components |
| `libs/types` | `@cognitoforms/types` | Generated TypeScript types from server |
| `libs/api` | `@cognitoforms/api` | API client services |
| `libs/utils` | `@cognitoforms/utils` | Shared utilities |

### Build Dependency Chain

```
model.js → vuemodel → element-ui → client/spa
```

First builds are slow due to this chain. Nx caches intermediate builds.

## Key Patterns

### Backend

- **Service Hierarchy**: `CoreService` → domain services → infrastructure
- **Module<T> DI**: Autofac modules for dependency injection
- **StorageContext**: Data access abstraction for Azure Table/Cosmos
- **BaseController**: Shared controller functionality, JSON serialization

### Frontend

- **Vue 2.7 Composition API**: `ref()`, `computed()`, composables
- **model.js Entities**: Reactive objects with rules and validation
- **vuemodel Bridge**: Connects model.js events to Vue reactivity
- **Source Adapters**: Bind entities to Vue component data

## Storage

| Storage | Use Case |
|---------|----------|
| Azure Table | Primary entity storage |
| Azure Blob | File uploads, large data |
| Azure Cosmos | Query-heavy workloads |
| Redis | Caching, rate limiting |

## Cross-References

See subdirectory CLAUDE.local.md files for detailed patterns:
- `Cognito.Core/CLAUDE.local.md` — Domain patterns
- `Cognito/CLAUDE.local.md` — Service patterns
- `Cognito.Services/CLAUDE.local.md` — Controller patterns
- `Cognito.Web.Client/CLAUDE.local.md` — Frontend patterns
