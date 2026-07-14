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
# moved the shared kernel (_DIAGNOSTICS / _diag / clear_diagnostics /
# _atomic_write) into _ctx. Phase 2 WU-1 moves the queue dependency-DAG plane
# into `depdag`; later decomposition phases append entries here as more names
# move out of `_monolith` into dedicated submodules.
_SUBMODULE_BY_NAME: dict[str, str] = {
    "_DIAGNOSTICS": "_ctx",
    "_diag": "_ctx",
    "clear_diagnostics": "_ctx",
    "_atomic_write": "_ctx",
    "_SCRIPTS_DIR": "_ctx",
    "_DEP_ID_RE": "depdag",
    "_RESERVED_DEP_PREFIXES": "depdag",
    "parse_dep_block": "depdag",
    "dep_ids": "depdag",
    "detect_dep_cycle": "depdag",
    "validate_dep_id_list": "depdag",
    "validate_queue_deps": "depdag",
    "sync_deps": "depdag",
    "dep_completion_status": "depdag",
    "format_unknown_dependency_blocker": "depdag",

    # Phase 2 WU-2: the document-model (parsing) seam.
    "_FENCE": "docmodel",
    "_FLAT_SCALAR_LINE_RE": "docmodel",
    "_yaml_load_tolerant": "docmodel",
    "_yaml_fallback_scalar": "docmodel",
    "parse_sentinel": "docmodel",
    "_PIPELINE_SKIPPED_BY": "docmodel",
    "_APP_SURFACE_MARKERS": "docmodel",
    "repo_has_no_app_surface": "docmodel",
    "repo_uses_cognito_planner": "docmodel",
    "phases_mcp_runtime_not_required": "docmodel",
    "skip_waiver_refusal": "docmodel",
    "spec_status": "docmodel",
    "PROVISIONAL_SENTINEL": "docmodel",
    "_PROVISIONAL_ELIGIBLE_GRADES": "docmodel",
    "build_parked_entry": "docmodel",
    "_parse_plan_frontmatter": "docmodel",
    "_plan_status": "docmodel",
    "_VALID_PLAN_COMPLEXITIES": "docmodel",
    "_DEFAULT_PLAN_COMPLEXITY": "docmodel",
    "plan_complexity": "docmodel",
    "_plan_lowest_phase": "docmodel",
    "_PLAN_PART_RE": "docmodel",
    "_plan_series_index": "docmodel",
    "_plan_sort_key": "docmodel",
    "_plan_phase_set": "docmodel",
    "_unchecked_wus_in_plan_scope": "docmodel",
    "_all_wus_in_plan_scope": "docmodel",
    "find_implementation_plans": "docmodel",
    "_implementation_plans_exist": "docmodel",
    "_has_any_complete_plan": "docmodel",
    "find_retro_plans": "docmodel",
    "latest_retro_plan": "docmodel",
    "retro_plan_has_significant_divergences": "docmodel",
    "count_deliverables": "docmodel",
    "_VERIFICATION_ONLY_MARKER": "docmodel",
    "_VERIFICATION_SECTION_RE": "docmodel",
    "_DELIVERABLES_SECTION_RE": "docmodel",
    "_DESCOPE_STRIKETHROUGH_RE": "docmodel",
    "_DESCOPE_MARKER_RE": "docmodel",
    "_DESCOPED_MARKER": "docmodel",
    "_row_is_descoped_in_place": "docmodel",
    "remaining_unchecked_are_verification_only": "docmodel",
    "classify_blocking_unchecked_rows": "docmodel",
    "_PHASE_HEADING_RE": "docmodel",
    "_BOLD_STATUS_RE": "docmodel",
    "_PHASE_KIND_RE": "docmodel",
    "_VALID_PHASE_KINDS": "docmodel",
    "_DEFAULT_PHASE_KIND": "docmodel",
    "parse_phases": "docmodel",
    "_IMPL_NOTES_HEADING_RE": "docmodel",
    "_SIBLING_IMPL_NOTES_HEADING_RE": "docmodel",
    "_sibling_impl_notes_present": "docmodel",
    "phases_show_implementation": "docmodel",
    "retro_staleness": "docmodel",
    "_TERMINAL_PHASE_STATUSES": "docmodel",
    "_phase_completion_plan": "docmodel",
    "_coerce_evidence_count": "docmodel",
    "_FAIL_CLOSED_EVIDENCE_SENTINELS": "docmodel",
    "_EVIDENCE_GATE_KILL_SWITCHES": "docmodel",
    "_FALSY_ENV_VALUES": "docmodel",
    "_evidence_gate_killed": "docmodel",

    # Phase 2 WU-3 (Batch 3): the host-capability declaration + probe seam.
    "_HOST_CAPABILITY_ID_RE": "hostcaps",
    "_HOST_CAPABILITY_REGISTRY": "hostcaps",
    "_coerce_capability_ids": "hostcaps",
    "_REQUIRES_HOST_RE": "hostcaps",
    "parse_requires_host": "hostcaps",
    "unknown_capability_ids": "hostcaps",
    "_HOST_PROBE_CACHE_FILENAME": "hostcaps",
    "_HOST_CAPABILITY_PROBE_CONFIG": "hostcaps",
    "_default_host_probes": "hostcaps",
    "host_present_capabilities": "hostcaps",
    "utc_now_iso": "hostcaps",
    "format_unknown_host_capability_blocker": "hostcaps",
    # Phase 2 WU-4 (Batch 4): the operator-halt notify plane (shim retired).
    "_NOTIFY_CONFIG_FILENAME": "notifyplane",
    "_NOTIFY_LEDGER_FILENAME": "notifyplane",
    "_NOTIFY_ERROR_FILENAME": "notifyplane",
    "_NOTIFY_SEND_TIMEOUT_SECONDS": "notifyplane",
    "_NOTIFY_LEDGER_MAX_AGE_SECONDS": "notifyplane",
    "_NOTIFY_ATTENTION_TERMINALS": "notifyplane",
    "_NOTIFY_CLEAN_STOP_TERMINALS": "notifyplane",
    "_NOTIFY_SENTINEL_CANDIDATES": "notifyplane",
    "_load_notify_config": "notifyplane",
    "_notify_sentinel_path": "notifyplane",
    "_notify_identity": "notifyplane",
    "_load_notify_ledger": "notifyplane",
    "_record_notify_send": "notifyplane",
    "_write_notify_error": "notifyplane",
    "_notify_decisions": "notifyplane",
    "_normalize_git_remote_url": "notifyplane",
    "_github_remote_url": "notifyplane",
    "_compose_notify_payload": "notifyplane",
    "_rfc2047_header": "notifyplane",
    "_ntfy_send": "notifyplane",
    "notify_halt": "notifyplane",
    "notify_event": "notifyplane",
    # Phase 2 WU-5 (Batch 5): the hook-touched state-dir surface (D4 cut).
    "_HOOK_EVENTS_FILENAME": "statedir",
    "_LEDGER_HEAD_CHARS": "statedir",
    "_LEGACY_STATE_FILENAMES": "statedir",
    "_MARKER_FILENAME": "statedir",
    "_REGISTRY_FILENAME": "statedir",
    "_load_registry": "statedir",
    "active_repo_root": "statedir",
    "append_hook_event": "statedir",
    "claude_state_dir": "statedir",
    "migrate_legacy_state_dir": "statedir",
    "repo_key": "statedir",
    "set_active_repo_root": "statedir",
    # Phase 4: the gates seam (completion-gate plane: evidence gate, autotick, structural backstop, verify-ledger).
    "_AUTOTICK_COMMENT_PREFIX": "gates",
    "_DETAIL_MAX_ITEMS": "gates",
    "_FOREIGN_HARDEN_SUBJECT_RE": "gates",
    "_PLAN_WU_CHECKBOX_RE": "gates",
    "_UNCHECKED_ROW_RE": "gates",
    "_commit_subject_is_foreign_harden": "gates",
    "_excerpt": "gates",
    "_files_from_commits": "gates",
    "_git_diff_name_only": "gates",
    "_is_noninvalidating_drift_path": "gates",
    "_item_commit_touched_files": "gates",
    "_load_control_surface_globs": "gates",
    "_load_harness_gate_module": "gates",
    "_load_validate_plan_module": "gates",
    "_manifest_glob_match": "gates",
    "_phases_text_scoped_to": "gates",
    "_phases_unchecked_row_detail": "gates",
    "_plan_unchecked_wus_are_verification_only": "gates",
    "_plan_wu_checkbox_counts": "gates",
    "_plan_wu_unchecked_row_detail": "gates",
    "autotick_verification_rows": "gates",
    "commit_drift_verdict": "gates",
    "evaluate_completion_evidence": "gates",
    "format_plan_structural_blocker": "gates",
    "gate_verdict_ok": "gates",
    "observation_gap_promotable": "gates",
    "plan_structural_backstop": "gates",
    "summarize_failing_detail": "gates",
    "verify_ledger": "gates",
    # Phase 4: the ledgers seam (ledger plane: deny/friction/telemetry ledgers, provenance, interventions, canary).
    "CANARY_WINDOW_DAYS_CEILING": "ledgers",
    "CANARY_WINDOW_RUNS_DEFAULT": "ledgers",
    "INTERVENTION_BAND_PCT": "ledgers",
    "INTERVENTION_BASELINE_RUNS": "ledgers",
    "INTERVENTION_MIN_SAMPLE": "ledgers",
    "INTERVENTION_REVIEW_AFTER_RUNS": "ledgers",
    "TELEMETRY_HALT_TERMINAL_REASONS": "ledgers",
    "_CANARY_CLAUDE_MD_PAIRS": "ledgers",
    "_CANARY_CONTROL_SURFACES_FALLBACK": "ledgers",
    "_CANARY_CONTROL_SURFACES_FILE": "ledgers",
    "_CANARY_DEFAULT_REVERT_UNSAFE_NOTE": "ledgers",
    "_COMMIT_BRACKETS_FILENAME": "ledgers",
    "_DENY_LEDGER_FILENAME": "ledgers",
    "_EFFICACY_BREADCRUMB_FILENAME": "ledgers",
    "_GATE_REFUSAL_SIGNATURES": "ledgers",
    "_GUARD_PLANE_HEARTBEAT_MIN_CYCLES": "ledgers",
    "_INTERVENTIONS_DIRNAME": "ledgers",
    "_INTERVENTION_EVENT_VOCABULARY": "ledgers",
    "_INTERVENTION_FIELD_ORDER": "ledgers",
    "_INTERVENTION_FIELD_RE": "ledgers",
    "_INTERVENTION_HYPOTHESIS_HEADING_RE": "ledgers",
    "_INTERVENTION_INDEPENDENCE_ENUM": "ledgers",
    "_INTERVENTION_INT_FIELDS": "ledgers",
    "_INTERVENTION_SUB_SIGNAL_VOCABULARY": "ledgers",
    "_OBSERVED_FRICTION_PROBE_PLACEHOLDER": "ledgers",
    "_OBSERVED_FRICTION_REGISTRY_PLACEHOLDER": "ledgers",
    "_PROVENANCE_CHURN_DAYS": "ledgers",
    "_PROVENANCE_CHURN_THRESHOLD": "ledgers",
    "_PROVENANCE_KINDS": "ledgers",
    "_PROVENANCE_VALUES": "ledgers",
    "_TELEMETRY_LEDGER_FILENAME": "ledgers",
    "_TELEMETRY_ROTATED_SEGMENTS": "ledgers",
    "_TELEMETRY_ROTATE_BYTES": "ledgers",
    "_TELEMETRY_SCHEMA_VERSION": "ledgers",
    "_canary_control_surfaces": "ledgers",
    "_canary_glob_to_re": "ledgers",
    "_canary_intersects": "ledgers",
    "_canary_load_parity_pairs": "ledgers",
    "_canary_touched_files": "ledgers",
    "_compute_pair_scope": "ledgers",
    "_deny_entry_same_cause_key": "ledgers",
    "_git_capture_lines": "ledgers",
    "_intervention_signal_event": "ledgers",
    "_intervention_signal_signature": "ledgers",
    "_interventions_queue_flag": "ledgers",
    "_iter_receipted_item_dirs": "ledgers",
    "_maybe_arm_canary": "ledgers",
    "_normalize_index_key": "ledgers",
    "_originating_telemetry_paths": "ledgers",
    "_provenance_doc_path": "ledgers",
    "_provenance_index_path": "ledgers",
    "_raw_marker_started_at": "ledgers",
    "_render_intervention_record": "ledgers",
    "_repo_is_interventions_bearing": "ledgers",
    "_resolve_pr_range": "ledgers",
    "_resolve_provenance_item_dir": "ledgers",
    "_rotate_telemetry_segments": "ledgers",
    "_run_marker_state_dir": "ledgers",
    "_spec_summary_paragraph": "ledgers",
    "_telemetry_run_marker": "ledgers",
    "ack_all_unacked_denies": "ledgers",
    "ack_deny_by_selector": "ledgers",
    "ack_oldest_deny": "ledgers",
    "append_auto_readmit_event": "ledgers",
    "append_commit_bracket": "ledgers",
    "append_deny_ledger_entry": "ledgers",
    "append_friction_ledger_entry": "ledgers",
    "append_telemetry_event": "ledgers",
    "backfill_provenance": "ledgers",
    "build_hardening_emit_command": "ledgers",
    "clear_efficacy_breadcrumb": "ledgers",
    "derive_touched_from_brackets": "ledgers",
    "derive_touched_from_grep": "ledgers",
    "derive_touched_from_range": "ledgers",
    "drop_efficacy_breadcrumb": "ledgers",
    "efficacy_breadcrumb_present": "ledgers",
    "find_auto_readmit_entry": "ledgers",
    "find_transcription_slip_entry": "ledgers",
    "flush_cloud_telemetry_segment": "ledgers",
    "guard_plane_heartbeat": "ledgers",
    "link_provenance": "ledgers",
    "lint_provenance": "ledgers",
    "normalize_hardening_dispatch_context": "ledgers",
    "oldest_unacked_deny": "ledgers",
    "parse_intervention_hypothesis": "ledgers",
    "pending_denial_reasons": "ledgers",
    "pending_hardening": "ledgers",
    "prior_run_pending_hardening": "ledgers",
    "provenance_lookup": "ledgers",
    "read_commit_brackets": "ledgers",
    "read_deny_ledger": "ledgers",
    "read_hook_events": "ledgers",
    "read_intervention_telemetry": "ledgers",
    "read_telemetry_events": "ledgers",
    "record_cycle_commit_bracket": "ledgers",
    "record_intervention": "ledgers",
    "validate_intervention_target_signal": "ledgers",
    "write_provenance": "ledgers",
    # Phase 4: the dispatch seam (dispatch plane: cycle/dispatch prompt emission, skill-frontmatter readers, prompt registry).
    "DISPATCH_CLASSES": "dispatch",
    "DISPATCH_MODELS": "dispatch",
    "DISPATCH_STEP_NAMES": "dispatch",
    "_COMMIT_CADENCE_MULTI_FLAG_RE": "dispatch",
    "_CYCLE_COMMIT_BUDGET_DEFAULT": "dispatch",
    "_CYCLE_COMMIT_MULTI": "dispatch",
    "_CYCLE_COMMIT_NOISE_ALLOWANCE": "dispatch",
    "_CYCLE_TEMPLATE_DIRNAME": "dispatch",
    "_DISPATCH_REQUIRES_RE": "dispatch",
    "_MULTI_COMMIT_CEILING_OVERRIDE": "dispatch",
    "_MULTI_COMMIT_PSEUDO_SKILLS": "dispatch",
    "_NORM_FOLD_TABLE": "dispatch",
    "_PROMPT_RESIDUE_RE": "dispatch",
    "_SECTION_MARKER_RE": "dispatch",
    "_SUBAGENT_MODEL_FLAG_RE": "dispatch",
    "_csv_set": "dispatch",
    "_dedup_residue": "dispatch",
    "_default_cycle_template_dir": "dispatch",
    "_emit_work_branch": "dispatch",
    "_mcp_test_cycle_model": "dispatch",
    "_parse_cycle_template": "dispatch",
    "_parse_section_attrs": "dispatch",
    "_read_mcp_runtime_decision": "dispatch",
    "_save_registry": "dispatch",
    "_standard_dispatch_bindings": "dispatch",
    "_strip_loop_fence": "dispatch",
    "append_dispatch_by_reference_event": "dispatch",
    "append_worker_subdispatch_event": "dispatch",
    "consume_nonce": "dispatch",
    "consumed_emission_count": "dispatch",
    "emission_consumed_by_nonce": "dispatch",
    "emit_cycle_prompt": "dispatch",
    "emit_dispatch_prompt": "dispatch",
    "load_context_json": "dispatch",
    "lookup_emission": "dispatch",
    "normalize_prompt_for_hash": "dispatch",
    "prompt_sha256": "dispatch",
    "register_emission": "dispatch",
    "register_emission_if_marked": "dispatch",
    "registry_summary": "dispatch",
    "resolve_emission_by_nonce": "dispatch",
    "skill_declares_multi_commit": "dispatch",
    "skill_declares_subagent_model": "dispatch",
}

# Submodule consulted when a name has no explicit entry in
# _SUBMODULE_BY_NAME above.
_FALLBACK_SUBMODULE = "_monolith"

# All submodules that make up this package, in no particular order.
_ALL_SUBMODULES = ("_ctx", "_monolith", "depdag", "dispatch", "docmodel", "gates", "hostcaps", "ledgers", "notifyplane", "statedir")


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
