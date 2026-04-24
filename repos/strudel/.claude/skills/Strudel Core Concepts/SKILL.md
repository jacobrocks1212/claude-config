---
name: strudel-core-concepts
description: Provides guidance for working with the core concepts and syntax of the Strudel live coding environment. This skill covers the fundamental building blocks of creating music with Strudel, including patterns, cycles, pitch, and the various notation systems.
version: 1.0.0
allowed-tools: ["Read", "Grep"]
---

# Strudel Core Concepts Skill

This skill provides guidance for understanding and using the fundamental concepts of the Strudel live coding environment. It is essential for creating and manipulating musical patterns.

## Overview

Strudel is a live coding environment based on TidalCycles, but implemented in JavaScript. It uses a unique pattern language to create complex musical structures from simple building blocks. Understanding the core concepts is crucial for effectively using Strudel.

**Primary Directive:** When creating music in Strudel, prioritize a clear understanding of how patterns, cycles, and notation work together. Refer to the documentation to ensure you are using the correct syntax and functions.

## Key Concepts

### Patterns
Patterns are the fundamental building blocks of Strudel. They are abstract representations of time-based events. For a detailed explanation, refer to `patterns.md`.

### Cycles
Cycles are the primary unit of time in Strudel. All patterns are organized within cycles. Understanding how cycles work is key to controlling the tempo and rhythm of your music. See `cycles.md` for more information.

### Pitch and Notes
Strudel provides several ways to represent musical pitch, including note names, MIDI numbers, and frequencies. The `pitch.md` and `notes.md` documents provide a comprehensive overview of how to work with pitch in Strudel.

### Notation Systems
Strudel offers two primary notation systems for creating patterns:

-   **Mini-Notation**: A concise, domain-specific language for writing rhythmic and melodic patterns. It is the most common way to write patterns in Strudel. For a full reference, see `mini-notation.md`.
-   **Mondo-Notation**: A newer, more powerful notation system that allows for more complex patterns and function calls. Learn more in `mondo-notation.md`.

### Basic Syntax
The basic coding syntax of Strudel is based on JavaScript, with some special features to make live coding easier. The `code.md` and `intro.md` documents provide an introduction to the syntax and how to get started with creating patterns.

## Development Guidelines

1.  **Start with the Basics**: If you are new to Strudel, start by learning the basics of patterns, cycles, and mini-notation.
2.  **Experiment**: The best way to learn Strudel is by experimenting. Try out different functions and see what they do.
3.  **Refer to the Documentation**: The documentation provides a wealth of information on all aspects of Strudel. Use it as a reference when you are unsure about something.

## When to Reference Additional Files

-   For a deep dive into how patterns work, see `patterns.md`.
-   To understand the concept of cycles and tempo, refer to `cycles.md`.
-   For information on how to represent pitch, see `pitch.md` and `notes.md`.
-   For a comprehensive guide to the mini-notation, see `mini-notation.md`.
-   To learn about the more advanced mondo-notation, see `mondo-notation.md`.
-   For an introduction to the basic syntax of Strudel, see `code.md` and `intro.md`.
