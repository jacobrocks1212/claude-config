#!/usr/bin/env python3
"""lazy_core._monolith — EMPTY SHELL, deleted in Phase-5 WU-4.

Phase 5 WU-3 (residue sweep) distributed every remaining top-level name to its
owning seam module; nothing is defined here any more. This shell survives ONE
work unit solely because two test surfaces still pin identity THROUGH it (the
``lazy_core._monolith._DIAGNOSTICS`` mutate-through-facade views and the
kernel-direct ``lazy_core._monolith._atomic_write`` calls) — WU-4 re-points
those pins to ``lazy_core._ctx`` (the owner) and ``git rm``s this file,
removing the facade's ``_FALLBACK_SUBMODULE`` with it.
"""

from ._ctx import _DIAGNOSTICS, _atomic_write  # noqa: F401 — WU-4-scheduled test identity pins
