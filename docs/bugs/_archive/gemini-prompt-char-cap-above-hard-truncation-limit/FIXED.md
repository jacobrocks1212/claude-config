---
kind: fixed
feature_id: gemini-prompt-char-cap-above-hard-truncation-limit
date: 2026-07-18
provenance: operator-directed-interactive
validated_via: code-audit (fix verified present in current tree)
auto_ticked_rows: 0
---

# Completion Receipt

Fix shipped in commit d5e9bb22 (harden(skill-prose): lower GEMINI_PROMPT_CHAR_CAP
24,000 -> 18,000 — below the true ~20k hard truncation limit). Verified present in the
current tree by the 2026-07-18 bug-backlog audit (read-only verification agents confirmed
the fix site in current code; SPEC root cause matched against the shipped change).

Receipt + archive performed OUT-OF-PIPELINE per the docs/bugs/CLAUDE.md reconciliation
contract ("Fixing a bug OUT-OF-PIPELINE"): the fix landed via a harden round that never
ran the __mark_fixed__ -> --archive-fixed tail, leaving a Concluded SPEC with a shipped fix.
