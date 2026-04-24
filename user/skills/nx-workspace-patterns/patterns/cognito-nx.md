# Cognito Forms Nx Workspace Patterns

This document provides Nx-specific patterns for the Cognito Forms frontend monorepo.

## Workspace Structure

```
Cognito.Web.Client/
├── apps/
│   ├── spa/           # Main SPA application (form builder, dashboard)
│   ├── client/        # Client-facing form submission app
│   ├── marketing/     # Marketing site
│   └── website/       # Public website
├── libs/              # Shared libraries
│   ├── ui/            # Shared UI components
│   ├── data-access/   # API clients, state management
│   ├── util/          # Utility functions
│   └── feature/       # Feature-specific modules
├── nx.json            # Nx configuration
├── project.json       # Project-level configuration
└── tsconfig.base.json # Shared TypeScript config
```

## Critical Rules

### Build Commands

```powershell
# NEVER use dotnet build or dotnet run for the full solution
# Use project-specific PowerShell scripts

# For frontend development, use Nx commands
cd Cognito.Web.Client

# Serve specific app
npx nx serve spa
npx nx serve client

# Build specific app
npx nx build spa --configuration=production

# Run affected builds only
npx nx affected:build --base=main

# Run affected tests
npx nx affected:test --base=main
```

### Dependency Rules

```
# apps/ can import from libs/
# libs/ can import from other libs/ (respect dependency constraints)
# libs/ CANNOT import from apps/

# Recommended library types:
# - feature-* : Feature modules (lazy loaded)
# - ui-*      : Presentational components
# - data-*    : Data access, state management
# - util-*    : Pure utility functions
```

## Running Commands

### Serve Applications

```powershell
# Development server for SPA
npx nx serve spa --port 4200

# Development server for client app
npx nx serve client --port 4201

# Serve multiple apps
npx nx run-many --target=serve --projects=spa,client --parallel
```

### Building

```powershell
# Build single app
npx nx build spa

# Production build
npx nx build spa --configuration=production

# Build all affected by changes
npx nx affected:build --base=origin/main

# Build with dependency graph
npx nx build spa --with-deps
```

### Testing

```powershell
# Run tests for specific project
npx nx test spa

# Run tests for affected projects
npx nx affected:test --base=origin/main

# Run tests with coverage
npx nx test spa --coverage

# Run e2e tests
npx nx e2e spa-e2e
```

### Linting

```powershell
# Lint specific project
npx nx lint spa

# Lint affected
npx nx affected:lint --base=origin/main

# Fix lint issues
npx nx lint spa --fix
```

## Project Configuration

### project.json Example

```json
{
  "name": "spa",
  "$schema": "../../node_modules/nx/schemas/project-schema.json",
  "projectType": "application",
  "sourceRoot": "apps/spa/src",
  "prefix": "app",
  "targets": {
    "build": {
      "executor": "@nrwl/webpack:webpack",
      "outputs": ["{options.outputPath}"],
      "options": {
        "outputPath": "dist/apps/spa",
        "main": "apps/spa/src/main.ts",
        "tsConfig": "apps/spa/tsconfig.app.json"
      },
      "configurations": {
        "production": {
          "optimization": true,
          "sourceMap": false,
          "extractLicenses": true
        },
        "development": {
          "optimization": false,
          "sourceMap": true
        }
      }
    },
    "serve": {
      "executor": "@nrwl/webpack:dev-server",
      "options": {
        "buildTarget": "spa:build",
        "port": 4200
      }
    },
    "test": {
      "executor": "@nrwl/jest:jest",
      "outputs": ["{workspaceRoot}/coverage/apps/spa"],
      "options": {
        "jestConfig": "apps/spa/jest.config.ts",
        "passWithNoTests": true
      }
    }
  },
  "tags": ["scope:spa", "type:app"]
}
```

## Shared Libraries

### Creating a New Library

```powershell
# Generate a new UI library
npx nx g @nrwl/vue:lib ui-button --directory=libs/ui

# Generate a data access library
npx nx g @nrwl/js:lib data-forms --directory=libs/data-access

# Generate a utility library
npx nx g @nrwl/js:lib util-validation --directory=libs/util
```

### Library Structure

```
libs/ui/button/
├── src/
│   ├── lib/
│   │   ├── Button.vue
│   │   ├── Button.spec.ts
│   │   └── index.ts
│   └── index.ts
├── project.json
├── tsconfig.json
├── tsconfig.lib.json
└── tsconfig.spec.json
```

### Importing Libraries

```typescript
// Use path aliases defined in tsconfig.base.json
import { Button } from '@cognito/ui/button'
import { FormService } from '@cognito/data-access/forms'
import { validateEmail } from '@cognito/util/validation'
```

## Caching Configuration

### nx.json Cache Settings

```json
{
  "tasksRunnerOptions": {
    "default": {
      "runner": "nx/tasks-runners/default",
      "options": {
        "cacheableOperations": ["build", "lint", "test", "e2e"],
        "cacheDirectory": ".nx/cache"
      }
    }
  },
  "targetDefaults": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["production", "^production"],
      "cache": true
    },
    "test": {
      "inputs": ["default", "^production"],
      "cache": true
    },
    "lint": {
      "inputs": ["default"],
      "cache": true
    }
  },
  "namedInputs": {
    "default": ["{projectRoot}/**/*", "sharedGlobals"],
    "production": [
      "default",
      "!{projectRoot}/**/*.spec.ts",
      "!{projectRoot}/**/*.test.ts",
      "!{projectRoot}/jest.config.ts"
    ],
    "sharedGlobals": ["{workspaceRoot}/tsconfig.base.json"]
  }
}
```

## Dependency Graph

```powershell
# Visualize dependency graph
npx nx graph

# Analyze dependencies for a project
npx nx graph --focus=spa

# Check for circular dependencies
npx nx lint --rule @nrwl/nx/enforce-module-boundaries
```

## Common Patterns

### Feature Module Organization

```
libs/feature/form-builder/
├── src/
│   ├── lib/
│   │   ├── components/
│   │   │   ├── FormCanvas.vue
│   │   │   ├── FieldPalette.vue
│   │   │   └── index.ts
│   │   ├── composables/
│   │   │   ├── useFormBuilder.ts
│   │   │   └── index.ts
│   │   ├── store/
│   │   │   ├── form-builder.store.ts
│   │   │   └── index.ts
│   │   └── form-builder.module.ts
│   └── index.ts
└── project.json
```

### Environment Configuration

```typescript
// apps/spa/src/environments/environment.ts
export const environment = {
  production: false,
  apiUrl: 'http://localhost:5000/api',
  featureFlags: {
    newFormBuilder: true
  }
}

// apps/spa/src/environments/environment.prod.ts
export const environment = {
  production: true,
  apiUrl: 'https://api.cognitoforms.com',
  featureFlags: {
    newFormBuilder: true
  }
}
```

## Troubleshooting

### Clear Nx Cache

```powershell
# Clear local cache
npx nx reset

# Clear and rebuild
rm -rf node_modules/.cache
rm -rf .nx/cache
npm install
```

### Debug Build Issues

```powershell
# Verbose build output
npx nx build spa --verbose

# Skip cache for debugging
npx nx build spa --skip-nx-cache

# Print affected projects
npx nx print-affected --base=origin/main --select=projects
```

### Fix Dependency Issues

```powershell
# Check for missing dependencies
npx nx dep-graph

# Validate workspace
npx nx workspace-lint

# Reset node_modules
rm -rf node_modules
npm install
```

## Integration with Backend

### API Proxy Configuration

```javascript
// apps/spa/proxy.conf.json
{
  "/api": {
    "target": "http://localhost:5000",
    "secure": false,
    "changeOrigin": true
  }
}
```

### Shared Types with Backend

```typescript
// libs/shared-types/src/lib/models.ts
// These types should mirror C# DTOs

export interface Form {
  id: string
  name: string
  fields: FormField[]
  createdAt: Date
  updatedAt: Date
}

export interface FormField {
  id: string
  type: FieldType
  label: string
  required: boolean
  validation?: ValidationRule[]
}

export type FieldType =
  | 'text'
  | 'number'
  | 'email'
  | 'date'
  | 'select'
  | 'checkbox'
  | 'file'
```
