---
name: cognito-storage
description: Provides a deep dive into the data persistence layer, including StorageContext patterns, data modeling conventions, and query optimization best practices.
version: 1.0.0
---
# Cognito Forms - Storage Skill

This skill provides deep expertise on the data persistence layer in Cognito Forms. Use this when you are interacting with the database, modifying data models, writing complex queries, or working with the `StorageContext`.

## Core Concepts
- **StorageContext**: The primary pattern for database interaction (likely a Unit of Work or Repository pattern).
- **Data Models**: The structure of the core entities (Forms, Entries, etc.).
- **Querying**: Best practices for writing efficient and readable queries.
- **Migrations**: The process for applying schema changes.

## When to Reference Additional Files
- For detailed examples and best practices on using `StorageContext`, read **`storage-context-patterns.md`**.
- When creating a new data model or modifying an existing one, consult the **`data-modeling-guide.md`**.
