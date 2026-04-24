---
name: Guiding Cognito Forms Development
description: Provides development guidance for the Cognito Forms codebase, including .NET backend patterns, Vue.js client code, service architecture, and integration with FormsService and StorageContext.
version: 1.0.0
allowed-tools: ["Read", "Grep", "Glob"]
---

# Cognito Forms Development Skill

This skill provides expert guidance for developing features in the Cognito Forms codebase. It has access to architectural patterns, coding standards, and common pitfalls.

## Project Architecture Overview

### Backend (.NET)
- **Core Projects**:
  - `Cognito.Core/` - Core business logic and data models
  - `Cognito.Services/` - Main web application and API services
  - `Cognito/` - Core domain logic and utilities
- **Key Services**:
  - `FormsService` - Main entry submission and form management
  - `StorageContext` - Data persistence layer
  - `AutoCreateEntriesService` - Auto-create entries logic
- **Testing**: `Cognito.Forms.UnitTests/` with test files in `TestFiles/`

### Frontend (Vue.js Monorepo)
- **Location**: `Cognito.Web.Client/`
- **Apps**:
  - `apps/spa/` - Single Page Application (admin interface)
  - `apps/client/` - Public form client (form display/submission)
- **Shared Libraries**: `libs/` containing shared components, API clients, Vue models, and UI elements

## Progressive Disclosure Workflow

To provide the most relevant information without overwhelming the context, follow this workflow:

1.  **For General Coding Standards:** If the request is about naming conventions, code organization, comments, or error handling syntax, **read `coding-standards.md`**.
2.  **For Architectural Patterns:** If the request involves service design, data persistence (`StorageContext`), submission flows (`FormsService`), or queue processing, **read `architecture-patterns.md`**.
3.  **For Debugging & Pitfalls:** If the user is debugging an issue or asks about common mistakes, **read `common-pitfalls.md`**. This file contains known gotchas related to caching, async, nulls, and submission flows.
4.  **For Specific Implementation:** Use the information from the relevant file(s) to answer the user's specific question about their code.

## When NOT to use this skill
- Do not use this skill for general programming questions unrelated to the Cognito Forms codebase.
- Do not use this skill to answer questions about infrastructure, deployment, or production credentials.

## Feedback Loop
When providing code, review it against the checklists in `coding-standards.md` and the anti-patterns in `common-pitfalls.md` to ensure high quality and prevent common errors.