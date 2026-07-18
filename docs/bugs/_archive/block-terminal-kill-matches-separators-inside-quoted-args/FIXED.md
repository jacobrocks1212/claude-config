---
kind: fixed
feature_id: block-terminal-kill-matches-separators-inside-quoted-args
date: 2026-07-18
provenance: operator-directed-interactive
validated_via: closed-by-successor (fix verified in current tree via the sibling investigation)
auto_ticked_rows: 0
---

# Completion Receipt — closed via successor investigation

This SPEC is `**Status:** Superseded` (kept as-is): its failure class was closed by the
successor investigation `block-terminal-kill-false-denies-quoted-argument-tokens`, whose
`_mask_quoted` quote-content-masking fix shipped in commit b77b5b23 (2026-07-13) and is
verified present in `user/hooks/block-terminal-kill.sh` by the 2026-07-18 backlog audit.
The successor dir was receipted + archived 2026-07-18; this receipt closes the superseded
predecessor so it can ride the same script-owned `--archive-fixed` mover (operator-directed;
see docs/bugs/CLAUDE.md "Fixing a bug OUT-OF-PIPELINE"). The sibling DEFERRED.md
(reason: superseded) is retained as the routing-history record.
