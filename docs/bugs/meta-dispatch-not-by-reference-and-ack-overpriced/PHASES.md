# Implementation Phases — Meta-Dispatch By-Reference

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Fixed

**MCP runtime:** not-required — pure claude-config harness mechanics (the `--emit-dispatch`
prompt registry + `lazy_guard.py` by-reference resolution). No Tauri app, no MCP-reachable
surface. This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md`.

## Reproduction Steps

Original symptom: a script-emitted dispatch could only be dispatched by pasting the full prompt
text verbatim; there was no by-reference token, so long dispatch prompts risked transcription
drift, and the ack path was over-priced. Reproduction: emit a dispatch and confirm a resolvable
`@@lazy-ref nonce=<hex>` token is returned AND that the guard resolves it to the registered prompt.

## Symptom-gone evidence (SEAM B)

FIXED in current code: every `--emit-dispatch` class emits `dispatch_prompt_ref`
(`@@lazy-ref nonce=<hex>`), and `lazy_guard.py` resolves the token (`_REF_RE`, F2a by-reference
path) to the registered prompt. Runtime-verified THIS session: the harden Round-36 cycle was
dispatched via the by-reference token alone (`@@lazy-ref nonce=edc60656…`) and the guard ALLOWED
it (resolved to the registered prompt) rather than denying an unregistered dispatch. Regression
coverage lives in `test_lazy_core.py` (guard by-reference allow-path tests).

---

### Phase 1: By-reference dispatch token (already in current code; receipt backfill 2026-07-13)

**Phase kind:** bugfix

**Deliverables:**
- [x] Every `--emit-dispatch` class returns a resolvable `dispatch_prompt_ref`
  (`@@lazy-ref nonce=<hex>`).
- [x] `lazy_guard.py` resolves the by-reference token to the registered prompt on the ALLOW
  paths (`_REF_RE`, F2a) — a fresh nonce dispatches without full-text paste.
- [x] Symptom reproduced-gone verified at runtime this session (harden Round-36 by-ref dispatch
  allowed) + regression coverage in `test_lazy_core.py`.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (MCP runtime not-required).
