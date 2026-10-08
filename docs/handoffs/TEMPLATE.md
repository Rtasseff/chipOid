# Handoff — `{{BRANCH}}`

| | |
|---|---|
| Branch | `{{BRANCH}}` |
| Worktree dir | `~/projects/miniProjects/202605_chipOid-wt/{{SLUG}}/` |
| Base | `{{BASE_REF}}` @ `{{BASE_SHA}}` |
| Created | {{DATE}} |
| Suggested model / effort | |
| Coordinator session | `main` checkout at `~/projects/miniProjects/202605_chipOid/` |

Read this first, then `CLAUDE.md`. This directory is a git worktree: it *is*
this branch. Do not `git checkout` another branch here. Machine-specific paths
(test data, baseline outputs) are in `LOCAL_SETUP.md` (gitignored, copied in).

## Goal

## Scope

**In:**
-

**Out** (belongs to another branch or to the coordinator):
-

## Contract (fixed; do not change without asking)

## Acceptance

-

## Conflict watchlist

-

## Status

<!-- Keep current as you work: checklist + short dated notes. -->
- [ ]

## Notes for the docs pass

<!-- Column definitions, config keys, log lines, anything the README /
     METRICS.md pass after merge needs. Branches don't edit README.md or
     METRICS.md themselves. -->

## Questions for the coordinator

<!-- Anything that needs the human or main. Don't guess: park it here and
     carry on with what doesn't depend on it. -->
-

## Return protocol

1. Keep **Status** current; note any deviation from this brief.
2. `pytest tests/` passes; record the count against the baseline above.
3. `git fetch origin && git rebase origin/main` (other v0.10 branches may
   have merged), re-run the tests.
4. Push the branch and open a PR against `main`. PR body = the review packet:
   what changed and why, deviations from the brief, test counts, the
   acceptance evidence (paste the `scripts/validate_exp.py` tables), and any
   pre-existing bug you noticed but did not fix.
5. Tell the human the PR is up. The coordinator spot-checks and merges.
