---
name: babysit
description: Babysit a GitHub PR's CI to a terminal state — polls gh pr checks on a recurring cron, auto-resolves safe failures (lint, formatting, trivial tests), stops when required checks settle.
argument-hint: [PR number or URL] [cadence e.g. 10m] — both optional; PR is inferred from chat/branch if omitted
plan-mode: never
---

# Babysit

Watch a GitHub pull request's CI from inside this session until it is **terminal** — every required check has settled (passed or failed) — reporting status on a recurring cadence and auto-resolving failures that are safe to fix unattended.

Use this when the user wants a PR's checks monitored hands-off: "babysit this PR", "keep an eye on CI for #16734", "watch the build and fix anything trivial".

## Step 1: Resolve the PR

Determine the target PR, in priority order:

1. **Explicit argument** — a PR number (`16734`) or URL passed to the skill.
2. **Chat context** — a PR number/URL mentioned earlier in the conversation.
3. **Current branch** — run `gh pr view --json number,headRefName` in the repo to resolve the PR for the checked-out branch.

If none resolve, ask the user which PR to babysit and stop.

Record the repo as `owner/repo` (from `gh repo view --json nameWithOwner` or the PR URL). All `gh` calls should pass `--repo <owner/repo>` to be unambiguous.

## Step 2: Resolve the cadence

Default to **5 minutes** unless the user specified otherwise (e.g. "every 10 minutes", "10m"). Convert to a cron expression:

| Cadence | Cron |
|---|---|
| `Nm`, N ≤ 59 | `*/N * * * *` |
| `Nh`, N ≤ 23 | `0 */N * * *` |

If the interval doesn't cleanly divide its unit, round to the nearest clean value and tell the user.

## Step 3: Arm the loop

1. Run the **first check immediately** (Step 4) — don't wait for the first cron fire.
2. If not already terminal, call **CronCreate** (`recurring: true`) with the cron from Step 2 and a prompt that re-runs this skill's check loop against the resolved PR. Bake the PR number, repo, and the auto-resolve + stop instructions into the cron prompt so each firing is self-contained.
3. Confirm to the user: PR, cadence, cron job ID, that it auto-stops on terminal, that it's session-only and auto-expires after 7 days, and that they can cancel sooner with CronDelete.

## Step 4: Each cycle — check and classify

Run `gh pr checks <pr> --repo <owner/repo>` and classify the checks:

- **All required checks passed** → terminal-success. Report and go to Step 6 (stop).
- **A required check FAILED** → go to Step 5 (inspect + auto-resolve).
- **Required checks still pending/running** → report a one-line status (which checks are still running) and keep waiting. Do not re-arm anything — the cron handles the next cycle.

**Human-gated approval checks are not failures.** Checks like `required/architect-approval` and `optional/designer-approval` sit `pending` until a human acts. Never treat them as failures, and do not let them keep the loop alive indefinitely — once all *automated* required checks have settled, CI is terminal even if approvals are still outstanding. Report outstanding approvals as a note, not a blocker.

## Step 5: Inspect and auto-resolve a failure

**Viewing the error detail requires Azure DevOps.** Cognito CI runs on ADO pipelines — `gh pr checks` gives only pass/fail/pending plus the `dev.azure.com` build URL. To see *why* a check failed you must pull the build log from ADO:

- Prefer the Azure DevOps MCP; fall back to the `az` CLI (`az pipelines build show` / `az pipelines runs ...`) or `az devops` against the build ID in the check URL.
- Extract the failing task and its error output (compiler error, failing test name + assertion, lint rule).

Then decide:

- **Safely auto-resolvable** — lint/format violations, an obvious/simple test failure, a trivial compile error with an unambiguous fix. Fix it on the PR branch using the repo's sanctioned build/test skills (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`) to verify, commit with a clear conventional-commit message, and update `PHASES.md` if the branch has one and the fix maps to a tracked item. **Do NOT push** — push is gated in work repos (`/push` is the human-invoked path). Report what you fixed and that it's committed but unpushed.
- **Not safely auto-resolvable** — logic failures, flaky/non-deterministic failures, anything ambiguous or wide-blast-radius. Report the failure with the relevant log excerpt and **stop the loop** (Step 6). Do not guess at fixes.

## Step 6: Stop the loop

When CI is terminal (all automated required checks passed, or a non-auto-resolvable failure was hit):

1. **CronDelete** the babysit job so it stops firing (use CronList to find the ID if it's no longer in context).
2. Give a final outcome report: pass/fail per required check, any fixes committed (and that they're unpushed), and any outstanding human approvals.

## Notes

- The loop lives only in this session — it dies when Claude exits and auto-expires after 7 days.
- Commits made during auto-resolve are **local only**; the user must `/push` them.
- Keep per-cycle reports terse — this runs unattended and shouldn't flood the chat.
