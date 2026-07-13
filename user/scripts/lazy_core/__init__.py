"""lazy_core — PEP 562 lazy facade over the decomposed lazy_core package.

Phase 1 of `lazy-core-package-decomposition` moved the entire former
`user/scripts/lazy_core.py` monolith body into `lazy_core/_monolith.py`
unmodified. This `__init__.py` is the facade that keeps every existing
import site working byte-compatibly:

    import lazy_core
    from lazy_core import _atomic_write
    lazy_core.notify_halt(...)
    lazy_core.time = fake_time            # module-attribute monkeypatching

Every public AND used-private name that used to live directly on the
`lazy_core` module is now resolved lazily via `__getattr__` below, forwarding
to whichever submodule owns it (today: only `_monolith`; later decomposition
phases will register additional submodules in `_SUBMODULE_BY_NAME`).

This facade is PERMANENT, not a transitional shim slated for removal — later
decomposition phases split `_monolith` into further submodules, but the
lazy-forwarding facade shape stays.

CRITICAL — patchability contract: a forwarded attribute is NEVER memoized
into this module's globals. Tests patch `lazy_core._monolith.<name>` (the
module where the name actually resolves); if `__getattr__` cached the
forwarded value here, a later `_monolith.X = fake` patch would be invisible
to the next `lazy_core.X` read. Only the submodule import itself is cached
(automatically, via `sys.modules`) — never the attribute lookup.
"""

import importlib

from ._ctx import _DIAGNOSTICS

# Explicit name -> submodule overrides. WU-2 of lazy-core-package-decomposition
# moves the shared kernel (_DIAGNOSTICS / _diag / clear_diagnostics /
# _atomic_write) into _ctx; later decomposition phases append entries here as
# more names move out of `_monolith` into dedicated submodules.
_SUBMODULE_BY_NAME: dict[str, str] = {
    "_DIAGNOSTICS": "_ctx",
    "_diag": "_ctx",
    "clear_diagnostics": "_ctx",
    "_atomic_write": "_ctx",
    "_SCRIPTS_DIR": "_ctx",
}

# Submodule consulted when a name has no explicit entry in
# _SUBMODULE_BY_NAME above.
_FALLBACK_SUBMODULE = "_monolith"

# All submodules that make up this package, in no particular order.
_ALL_SUBMODULES = ("_ctx", "_monolith")


def __getattr__(name):
    # Attribute access to a submodule name itself (e.g. `lazy_core._monolith`)
    # must return the submodule object — `getattr(submodule, "_monolith")`
    # would raise AttributeError since a submodule doesn't have itself as an
    # attribute.
    if name in _ALL_SUBMODULES:
        return importlib.import_module(f".{name}", __name__)

    modname = _SUBMODULE_BY_NAME.get(name, _FALLBACK_SUBMODULE)
    mod = importlib.import_module(f".{modname}", __name__)
    try:
        return getattr(mod, name)
    except AttributeError:
        raise AttributeError(f"module 'lazy_core' has no attribute {name!r}") from None


def __dir__():
    fallback_mod = importlib.import_module(f".{_FALLBACK_SUBMODULE}", __name__)
    names = set(globals().keys()) | set(_SUBMODULE_BY_NAME.keys()) | set(dir(fallback_mod))
    return sorted(names)


def load_all():
    """Eagerly import every submodule in this package.

    For consumers that want ImportError timing pinned to process start
    rather than first attribute access. Not wired into any state script in
    this WU — a later WU wires this into lazy-state.py / bug-state.py.
    """
    for submodule in _ALL_SUBMODULES:
        importlib.import_module(f".{submodule}", __name__)
