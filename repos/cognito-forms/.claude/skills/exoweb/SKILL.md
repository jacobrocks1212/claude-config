---
name: exoweb
description: Provides guidance for working with the ExoWeb JavaScript framework and ExoModel library, focusing on usage in build.js, object model (Type, Property, Rule), client-server synchronization, common patterns, and known pitfalls.
version: 1.0.0
allowed-tools: ["Read", "Grep"]
---

# ExoWeb Framework Skill

This skill provides guidance for maintaining and working with the ExoWeb JavaScript framework, a component used within the Cognito Forms codebase, particularly in build scripts like `build.js`.

## Overview

ExoWeb is an end-to-end web framework combining JavaScript and ASP.NET technologies. It provides a rich JavaScript object model, intuitive UI code based on HTML/CSS/JavaScript, model- and UI-driven validation, and seamless synchronization of changes between client and server.

**In this codebase**, ExoWeb's primary role is within the build process to define and extend client-side models that synchronize with server-side models.

**Primary Directive:** When working with ExoWeb code, prioritize consistency with existing patterns. Avoid introducing modern JavaScript idioms that may conflict with ExoWeb's object model and runtime. Treat this as maintenance-focused work.

## Key Architecture Components

### Object Model (ExoModel)
ExoWeb uses the open-source ExoModel library to represent server-side object models (Entity Framework, NHibernate) on the client:

- **JSON-based representation**: Client models are built/modified through JSON from server
- **Type mapping**: Each model type becomes a unique JavaScript type with the same name
- **Change detection**: Automatically tracks property modifications, list changes, object creation/deletion
- **`ExoWeb.Model.Type`**: Core construct for defining an entity or object type
- **`ExoWeb.Model.Property`**: Defines a property on a Type (data type, attributes)
- **`ExoWeb.Model.Rule`**: Defines validation and calculation logic

### Rules & Validation
- **Calculated properties**: Automatically update when dependent properties change
- **Custom rule logic**: Triggered by property modifications
- **Metadata-driven validation**: Auto-generates rules from server-side model characteristics
- **Real-time feedback**: Validation issues embedded in the model until resolved
- **Common rules**: `required`, `range`, `regex`, and custom validation rules

### Client-Server Synchronization
- Maintains event logs tracking all changes
- Events replay on server during async requests
- Keeps client and server models synchronized
- Allows selective client-side operation execution

## Development Guidelines

1. **Follow Existing Patterns**: Mimic the structure and style of existing ExoWeb definitions in `build.js` and related files
2. **Use ExoWeb APIs**: Do not manipulate model objects directly. Use provided APIs for defining types, properties, and rules
3. **Use Getter/Setter Methods**: Always use `get_PropertyName()` and `set_PropertyName()` to ensure change tracking works
4. **Test Thoroughly**: Changes to ExoWeb models can have far-reaching consequences. Test affected client-side functionality thoroughly
5. **Isolate Changes**: Keep modifications small and isolated to minimize risk

## When to Reference Additional Files

- For examples of how to define models and rules, see `common-patterns.md`
- To understand common mistakes, debugging tips, and required workarounds, see `pitfalls-and-workarounds.md`
- For specific information on how ExoWeb is used in the build process, see `build-process-integration.md`

## Example Activation Scenarios

This skill should activate when you:
- Need to modify `build.js` or other files containing ExoWeb definitions
- Are asked to add a new validation rule to a model
- Need to understand how client-side JavaScript models are generated or defined
- Encounter errors related to `ExoWeb.Model` or ExoModel components
- Work with calculated properties or model synchronization
- Debug issues with change tracking or validation
