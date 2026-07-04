# Research — Operator Paging on Pipeline Halts

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The terminal-emission chokepoint already exists and already composes the message.** Every halt
  either state script detects funnels through the `_state()` output helper
  (`user/scripts/lazy-state.py` ~line 111; `user/scripts/bug-state.py` ~line 260) with a
  `terminal_reason` and a human-readable `notify_message` (e.g. Step 3's
  `BLOCKED: {feature_name} — {phase}. Awaiting input.`, Step 3.5's
  `NEEDS INPUT: {feature_name} — {writer} halted on an ambiguous decision.`). The in-file `--test`
  harness even asserts terminal notify messages name the feature (`lazy-state.py` ~line 6231). The
  field's NAME says it was always meant to be pushed somewhere; today it is only printed as JSON.
- **The existing notification surface is prose, and says so.** `/lazy-batch`,
  `/lazy-batch-cloud`, and `/lazy-bug-batch` carry a §1c.6 `PushNotification` policy (five named
  event points: park, halt, flush, run-end, budget-guard trip) with the explicit rule
  "`PushNotification` is always called by the orchestrator — state scripts never call it"
  (`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` ~line 386). Its structural gaps are
  the feature's motivation: manual `/lazy` stepping never fires it (`user/skills/lazy/SKILL.md`
  contains no notification step and no run marker), a crashed/reclaimed orchestrator never reaches
  it, and prose adherence is graded by retro rather than guaranteed.
- **Sentinel-write is NOT a chokepoint.** `NEEDS_INPUT.md`/`BLOCKED.md` are written by cycle
  subagents via skill prose (Write tool), by the Step 1d.5 input-audit, by completion gates, AND by
  the scripts themselves (`compute_state` writes the `unknown-host-capability` `BLOCKED.md` and
  `DEFERRED_REQUIRES_HOST.md`; `--apply-pseudo` writes others). This multiplicity is why the SPEC's
  D2 rejects the sentinel-write moment and anchors on terminal emission.
- **Read-only consumers re-run the state scripts.** `/lazy-status`, `lazy-queue-doc.py` (via
  `pipeline_visualizer.probe.probe_state`), and the visualizer's `/api/state` all shell the
  scripts, so a naive notify-at-emission would page on every dashboard refresh — dedup by sentinel
  identity is mandatory, not a nicety.
- **State-dir machinery to reuse:** `lazy_core.claude_state_dir()` resolves the per-repo keyed
  `~/.claude/state/<repo_key>/` and honors the `LAZY_STATE_DIR` hermetic-test override;
  `_atomic_write` is the mandated write primitive; `_diag()` is the breadcrumb channel; the
  `hook-error.json` breadcrumb pattern (from `long-build-ownership-guard.sh`) models the
  fail-OPEN error trail; `urllib` with `timeout=5` is the established HTTP-probe convention
  (`_default_sidecar_probe`, `_default_frontend_probe`, `_default_health_probe`).
- **Neutralization gives dedup a free lifecycle.** `--neutralize-sentinel` renames a resolved
  sentinel to `*_RESOLVED_<date>*` — the identity `(item, reason, mtime, size)` dies with the
  rename, and any subsequent halt writes a fresh sentinel with a fresh identity. No explicit
  "clear the ledger" step is ever needed.
- **Coupled-pair discipline:** any change touching both state scripts must pass
  `lazy_parity_audit.py --repo-root .`; shared logic belongs in `lazy_core.py`
  (`user/scripts/CLAUDE.md` contributor conventions). Hence one helper, two one-line call sites.
- **Siblings:** `mobile-queue-control` (Complete) supplies the GitHub-mobile read surface the
  payload deep-links into; `native-android-pipeline-steering` (Draft) owns the mobile WRITE path
  (structured resolution commits) — the SPEC's D6 deliberately leaves the answer path there.

## External prior art & concepts

(Training-knowledge, not live research — stated honestly.)

- **ntfy** (ntfy.sh / self-hosted): pub-sub push over plain HTTP PUT/POST to a topic URL; no
  account; Android/iOS apps; supports title, priority, tags, and a click-through URL; message body
  practical limit ~4 KB. The topic URL is a capability secret on the public instance. Widely used
  for exactly this shape of "my long-running script finished / needs me" notification.
- **Pushover**: one-time purchase per platform, token + user key, ~10k messages/month, mature
  delivery and quiet-hours semantics. The classic reliable-hobbyist pager.
- **GitHub notifications as a channel**: issue creation/mentions trigger GitHub-mobile push;
  durable and composes with in-repo docs, but noisy, permission-heavy (a PAT everywhere), and
  creates artifact-lifecycle overhead — generally considered a poor interactive pager.
- **Paging hygiene (SRE practice)**: page only on actionable states; non-actionable notifications
  train operators to ignore the channel (alert fatigue). This is the backbone of the SPEC's D3
  attention-set default and clean-stop opt-in.
- **Dedup-by-identity + re-notify-after-interval** is the standard alerting pattern
  (Alertmanager's group/repeat_interval); the SPEC's D4 maps it onto a daemonless world honestly
  (re-ping is opportunistic on next observation).

## Alternatives analysis

- **Channel (D1).** ntfy vs Pushover vs GitHub. Deciding axis was secret provisioning across three
  host classes (Windows workstation, WSL, cloud container): ntfy's whole configuration is one URL
  (env var or one untracked JSON line), Pushover needs an account plus two secrets, GitHub needs a
  scoped token everywhere plus artifact cleanup. Payload richness is comparable (all carry a title,
  body, link). Reliability favors Pushover slightly; cost and reversibility favor ntfy. The
  channel seam (one `send(title, body, link)` indirection) makes the loser recoverable at config
  cost, which is why the seam itself is auto-accepted while the channel is OPEN.
- **Trigger point (D2).** Script-owned vs orchestrator-owned was pre-decided by the stub; the real
  analysis was WITHIN the scripts: sentinel-write moment (rejected — no single writer; prose
  writers exist) vs terminal emission (chosen — verified single funnel through `_state()`), with
  the terminal-emission's re-fire-on-every-probe cost paid by the D4 ledger, which any option
  needed anyway for long-lived halts.
- **Dedup state residency (D8).** Marker-next-to-sentinel would be visible in `git status`, risks
  the `BLOCKED*`-name write hook's blast radius and doc lints, and commits ephemeral bookkeeping
  into the work tree. The per-repo keyed state dir already exists, is atomic-write-served, and is
  hermetically overridable — a strictly dominant choice.
- **Payload (D5).** The `decisions:` frontmatter list is the highest-value few bytes available: it
  is schema-capped at 4 one-liners, parseable without the load-bearing body, and is literally the
  question the operator must answer. Omitting it (option B) re-adds an open-the-laptop round trip.
- **Answer path (D6).** Building any v1 write path would duplicate
  `native-android-pipeline-steering` scope and invite hand-edited malformed sentinels — the exact
  corruption class the file contracts and write hooks exist to prevent.

## Pitfalls & risks

- **Pager storm via read-only probes.** The visualizer polls; `lazy-queue-doc.py` runs per cycle.
  Without identity dedup the feature is unshippable. Mitigated structurally (ledger checked before
  send; validated by the repeated-probe test).
- **Notification failure contaminating the halt.** Any raise, hang, or nonzero exit from
  `notify_halt()` would corrupt the state machine's contract. Mitigated: whole-body try/except,
  `timeout=5`, no exit-code path, breadcrumb-only failure surface — and a dedicated fail-OPEN test.
- **Silent no-page ambiguity.** "No page" must be distinguishable between not-configured,
  deduped, and send-failed. Mitigated: `_diag()` lines on attempted sends + `notify-error.json`
  on failure; not-configured is the documented default.
- **Cloud proxy block.** A cloud container's egress proxy may refuse the channel host; assuming
  reachability would make cloud paging silently dead. Mitigated: Phase 3 explicitly verifies or
  documents the degrade; §1c.6 PushNotification remains the cloud run-level fallback.
- **Double-notification fatigue.** Claude-app pings (§1c.6) and ntfy pages can both fire for the
  same run-level event. Bounded: different event sets mostly (per-halt vs run-level), and D3 keeps
  the script-side set attention-only. If fatigue emerges, retiring/trimming §1c.6 is the vN lever
  (flagged in D3 option C, deliberately not taken in v1).
- **Secret leakage.** The topic URL must never land in a tracked file, a committed breadcrumb, or
  a diagnostics line. Contract: breadcrumbs and diags record channel KIND and error class only,
  never the URL. Worth a dedicated test (grep the ledger/breadcrumb fixtures for the fixture URL).
- **Measurement/falsifiability.** The feature's claim is time-to-notice reduction. Cheap proxy:
  the ledger's `notified_at` vs the sentinel's resolution-rename date gives halt-dwell-time
  before/after; a retro can compare pre-feature halt dwell (git history of `*_RESOLVED_*` renames)
  against post-feature dwell. If dwell does not move, the feature is dead weight and should say so.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 channel | ntfy behind a one-function channel seam | medium-high (OPEN — operator call) |
| D2 chokepoint | `lazy_core.notify_halt()` at both scripts' terminal emission in `main()` | high (auto-accepted) |
| D3 event scope | attention terminals default; clean stops opt-in; §1c.6 untouched | high (OPEN — operator call) |
| D4 dedup/re-ping | notify-once per sentinel identity; re-ping as later config key | medium-high (OPEN — operator call) |
| D5 payload | rich: notify_message + decisions + GitHub deep link + LAZY_QUEUE.md pointer | high (OPEN — operator call) |
| D6 answer path | v1 notice-only; write path stays in native-android-pipeline-steering | high (OPEN — operator call) |
| D7 secrets | untracked `~/.claude/notify.json` + `LAZY_NOTIFY_URL` env override | high (auto-accepted) |
| D8 ledger | `notify-ledger.json` in per-repo keyed state dir via `_atomic_write` | high (auto-accepted) |
| D9 failure | fail-OPEN, timeout=5, breadcrumb + `_diag`, ledger only on success | high (auto-accepted) |
| D10 cloud parity | identical path, env-provisioned secret, verified-or-documented degrade | high (auto-accepted) |
