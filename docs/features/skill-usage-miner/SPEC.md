# Skill Usage Miner + Dead-Weight Audit — Feature Specification

> 80+ user skills and growing; mine session logs (same READ-ONLY infrastructure as `toolify-miner.py`) for per-skill invocation frequency, flag never-invoked skills for `archived/`, and flag high-frequency prose skills as toolification candidates.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The skills tree only grows (plus stray artifacts — `user/skills/sh.exe.stackdump` is a crash dump
checked in). There is no usage signal distinguishing load-bearing skills from dead weight, so the
harness accretes prompt-surface and maintenance burden with no pruning loop, contradicting the
"efficient" mission criterion.

## Direction (deliberately not locked)

- **Miner:** stdlib-only, read-only over `~/.claude/projects/**/*.jsonl` (the `toolify-miner.py`
  parsing layer is directly reusable) — count Skill-tool invocations + slash-command mentions per
  skill per time window.
- **Report:** ranked usage table + never-invoked list + high-frequency candidates cross-linked to
  the toolify bar; proposes, never auto-archives (archival stays deliberate, via `archived/` with
  its audit trail).
- **Hygiene sweep:** flag non-skill files inside `user/skills/` (the stackdump class).

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: window length + workstation/cloud
> log coverage; repo-scoped skills inclusion; whether the report feeds `/lazy-batch-retro` or a
> standalone cadence. Solutions above are directional, not locked.
