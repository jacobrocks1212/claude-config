---
name: nx-monorepo
description: Nx monorepo workspace patterns for managing multi-package TypeScript/JavaScript projects. Use when working with Nx workspaces, running builds, testing, understanding project dependencies, and configuring caching.
triggers:
  - "nx.json"
  - "project.json"
  - "nx run"
  - "nx build"
  - "nx test"
  - "nx affected"
  - "nx graph"
  - "@nx/"
  - "apps/"
  - "packages/"
  - "libs/"
---

# Nx Monorepo Patterns

## When to Use This Skill
- Working in Nx monorepo workspaces
- Running builds and tests across packages
- Understanding project dependencies
- Configuring task caching and pipelines
- Managing shared dependencies

## Project Structure
```
workspace/
├── nx.json                 # Nx configuration
├── package.json            # Root dependencies
├── tsconfig.base.json      # Shared TypeScript config
├── apps/
│   ├── web-app/           # Application
│   └── api/               # Another application
├── packages/              # Or libs/
│   ├── ui/                # Shared UI components
│   ├── utils/             # Shared utilities
│   └── types/             # Shared types
```

## Essential Commands

### Running Tasks
```bash
# Run single target for single project
nx run my-app:build
nx run my-app:test
nx run my-app:serve

# Shorthand
nx build my-app
nx test my-app
nx serve my-app

# Run target for all projects
nx run-many --target=build
nx run-many --target=test

# Run with parallelism control
nx run-many --target=build --parallel=4

# Run for specific projects
nx run-many --target=build --projects=app1,app2
```

### Affected Commands (CI Optimization)
```bash
# Only build projects affected by changes
nx affected --target=build

# Compare against specific base
nx affected --target=test --base=main --head=HEAD

# List affected projects
nx show projects --affected
```

### Dependency Graph
```bash
# Open interactive graph
nx graph

# Show dependencies for a project
nx graph --focus=my-app

# Export as JSON
nx graph --file=graph.json
```

## Project Configuration

### project.json
```json
{
  "name": "my-app",
  "sourceRoot": "apps/my-app/src",
  "projectType": "application",
  "targets": {
    "build": {
      "executor": "@nx/vite:build",
      "outputs": ["{options.outputPath}"],
      "options": {
        "outputPath": "dist/apps/my-app"
      }
    },
    "serve": {
      "executor": "@nx/vite:dev-server",
      "options": {
        "buildTarget": "my-app:build"
      }
    },
    "test": {
      "executor": "@nx/vite:test",
      "options": {
        "passWithNoTests": true
      }
    },
    "lint": {
      "executor": "@nx/eslint:lint",
      "options": {
        "lintFilePatterns": ["apps/my-app/**/*.{ts,tsx,vue}"]
      }
    }
  },
  "tags": ["scope:frontend", "type:app"]
}
```

### nx.json Configuration
```json
{
  "targetDefaults": {
    "build": {
      "dependsOn": ["^build"],
      "cache": true
    },
    "test": {
      "cache": true
    },
    "lint": {
      "cache": true
    }
  },
  "namedInputs": {
    "default": ["{projectRoot}/**/*", "sharedGlobals"],
    "sharedGlobals": ["{workspaceRoot}/tsconfig.base.json"],
    "production": [
      "default",
      "!{projectRoot}/**/*.spec.ts",
      "!{projectRoot}/test/**/*"
    ]
  },
  "parallel": 3,
  "cacheDirectory": ".nx/cache"
}
```

## Task Pipeline (dependsOn)

```json
{
  "targetDefaults": {
    "build": {
      "dependsOn": ["^build"]  // Build dependencies first
    },
    "test": {
      "dependsOn": ["build"]   // Build this project first
    },
    "deploy": {
      "dependsOn": ["build", "test"]  // Build and test first
    }
  }
}
```

- `^build` - Run build on all dependencies first
- `build` - Run build on this project first
- `["^build", "^test"]` - Run both on dependencies

## Caching

### How Caching Works
Nx hashes inputs (source files, dependencies, environment) and caches outputs. Same inputs = cached result.

### Cache Configuration
```json
{
  "targetDefaults": {
    "build": {
      "cache": true,
      "inputs": ["production", "^production"],
      "outputs": ["{options.outputPath}"]
    },
    "test": {
      "cache": true,
      "inputs": ["default", "^production"]
    }
  }
}
```

### Cache Commands
```bash
# Clear local cache
nx reset

# View cache status
nx show project my-app --web
```

## Workspace Libraries

### Creating Libraries
```bash
# Generate a new library
nx g @nx/js:library utils --directory=packages/utils

# Generate Vue library
nx g @nx/vue:library ui --directory=packages/ui
```

### Importing Between Projects
```typescript
// In tsconfig.base.json
{
  "compilerOptions": {
    "paths": {
      "@myorg/utils": ["packages/utils/src/index.ts"],
      "@myorg/ui": ["packages/ui/src/index.ts"]
    }
  }
}

// In application code
import { formatDate } from '@myorg/utils';
import { Button } from '@myorg/ui';
```

## Project Tags & Boundaries

### Defining Tags
```json
// project.json
{
  "tags": ["scope:frontend", "type:app"]
}
```

### Enforcing Boundaries
```json
// .eslintrc.json
{
  "rules": {
    "@nx/enforce-module-boundaries": [
      "error",
      {
        "depConstraints": [
          {
            "sourceTag": "type:app",
            "onlyDependOnLibsWithTags": ["type:lib", "type:util"]
          },
          {
            "sourceTag": "scope:frontend",
            "onlyDependOnLibsWithTags": ["scope:frontend", "scope:shared"]
          }
        ]
      }
    ]
  }
}
```

## CI Configuration

### GitHub Actions Example
```yaml
- name: Install dependencies
  run: pnpm install --frozen-lockfile

- name: Run affected tests
  run: npx nx affected --target=test --base=origin/main

- name: Run affected builds
  run: npx nx affected --target=build --base=origin/main
```

### Using Nx Cloud (Remote Caching)
```bash
# Connect to Nx Cloud
npx nx connect

# Tasks automatically cached remotely
nx run-many --target=build
```

## Common Patterns

### Shared TypeScript Config
```json
// tsconfig.base.json
{
  "compilerOptions": {
    "strict": true,
    "moduleResolution": "bundler",
    "target": "ES2022",
    "paths": { /* library mappings */ }
  }
}

// apps/my-app/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": { /* app-specific */ }
}
```

### Workspace-Wide Scripts
```json
// package.json
{
  "scripts": {
    "build": "nx run-many --target=build",
    "test": "nx run-many --target=test",
    "lint": "nx run-many --target=lint",
    "serve": "nx run-many --target=serve --parallel=100"
  }
}
```

## Critical Rules

1. **Use affected commands in CI** - Only build/test what changed
2. **Enable caching** - Dramatically speeds up builds
3. **Define proper dependsOn** - Ensure correct build order
4. **Use tags for boundaries** - Prevent architectural violations
5. **Keep libraries focused** - Single responsibility per library

## Troubleshooting

```bash
# Debug task execution
nx build my-app --verbose

# Show what would run (dry run)
nx affected --target=build --dry-run

# Reset everything
nx reset
rm -rf node_modules
pnpm install
```
