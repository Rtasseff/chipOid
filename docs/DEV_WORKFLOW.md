# How we work on chipOid

The playbook for taking user feedback to a shipped Windows `.exe`. It was
written after v0.10, which went from a feedback review to a delivered build in
one day (2026-10-08), and it records what worked and what tripped us up. A new
session should read this, then `CLAUDE.md` ("Current state"), then
`gh issue list`.

## Roles

| Who | Where | Does | Doesn't |
|---|---|---|---|
| **Human** (maintainer) | everywhere | Makes the decisions, starts sessions, relays "PR is up" or "report is in", talks to the lab, hands the `.exe` over | — |
| **Coordinator session** | main checkout, `main`, top model, high effort | Plans, writes issues and briefs, makes small fixes inline, reviews and merges PRs, runs the real-data validation, writes docs, bumps the version, tags, keeps this repo's records current | Write big features itself |
| **Branch sessions** | one worktree per bucket, model/effort from the brief | Implement one bucket from its brief, run tests and acceptance, push, open a PR with a review packet | Touch files outside their scope; edit README/METRICS |
| **Subagents** | spawned by the coordinator | Medium, self-contained jobs with named files (e.g. the docs pass), with the model set explicitly | Open-ended audits |
| **Windows session** | same folder via the WSL share | Builds and smoke-tests `chipOid.exe`, compares its numbers with Linux, packages it, writes a report | Run git writes or edit tracked files (see `WINDOWS_SESSION.md`) |

Rules of thumb for where work goes, and the review policy: `docs/handoffs/README.md`.

## The release cycle

1. **Intake.**
   - Turn the feedback into GitHub issues: labels `P1`/`P2`/`P3` plus an area label, and a milestone for the release.
   - Check every code pointer against the code before posting.
   - The repo is public. Names and personal paths stay out (they go in `LOCAL_SETUP.md`, which is gitignored). Sample numbers and examples are fine.
2. **Baseline, before any code changes.** Re-run the previous version on the real data with the users' own settings and confirm it reproduces their outputs (`scripts/validate_exp.py --baseline`). Every later "unchanged" claim is checked against this run.
3. **Plan and freeze the contracts.**
   - Fix up front: config keys and defaults, column names and positions, log lines, new module names, which branch owns which file, and the merge order.
   - This is what lets branches run in parallel.
   - Ask the human only for real decisions (for v0.10: the default on/off per surface, per-marker vs shared thresholds, the Excel sheets, who builds the `.exe`, delivery).
4. **Worktrees.** Run `scripts/new-worktree.sh <slug> <branch>`, then write the brief (from `docs/handoffs/TEMPLATE.md`), commit it on the branch, and add a row to the registry. Give the human the directory, the model/effort and the paste-in prompt (below).
5. **While branches work,** the coordinator drafts the Windows brief, the user guide, the release notes, and messages to the lab.
6. **Review each PR, proportionately.** The PR body is the review packet, with the acceptance evidence pasted in.
   - Read the packet.
   - Do a targeted read of the correctness-critical code only (lattice, readout, inclusion).
   - Do a trial merge (`git merge-tree --write-tree main <branch>`).
   - Squash-merge in the planned order, then run the full suite on `main`.
   - Do one end-to-end check of the contract between branches (e.g. GUI defaults → pipeline).
7. **Fix small pre-existing bugs inline.** Branches report them under "noticed, not fixed".
8. **Release candidate.**
   - Bump `__version__` (single-sourced in `src/chipoid/__init__.py`).
   - Run the real data with the shipped defaults and validate against the baseline and the hand-picked wells.
   - Post the table to the validation issue and settle the defaults.
9. **Docs pass.** A subagent (Sonnet) updates README, METRICS.md and CLAUDE.md from each brief's "Notes for the docs pass" plus the code. The coordinator reads the diff.
10. **Windows build.**
    - Write a brief naming the build commit, plus a `git diff --stat <commit> HEAD -- src chipoid_gui.spec requirements.txt pyproject.toml` check that must print nothing.
    - The human starts the Windows session.
    - The `.exe`'s numbers must be **identical** to the Linux release-candidate run. Since v0.10 any difference is a bug.
    - Problems become issues → fixes on `main` → a rebuild brief.
    - Commit each report as a record, with `C:\Users\<you>\` in paths.
11. **Ship.**
    - Create an annotated tag on the commit the `.exe` was built from, with the `.exe`'s SHA-256 in the tag message.
    - Close the issues and the milestone.
    - Open a follow-up issue for anything deferred.
    - The human hands over the `.exe` + `RELEASE_NOTES_v<x>.md` + `LIVE_DEAD_GUIDE.md`. There is no GitHub Release asset.
12. **Clean up right away.**
    - Remove each worktree and its branch (local and remote) as soon as its PR merges. Each is ~550 MB with its venv.
    - Mark the briefs *Merged* / *Done*.
    - Update "Current state" in `CLAUDE.md`.

## Paste-in prompts

Branch session (after `cd ~/projects/miniProjects/202605_chipOid-wt/<slug>` and `claude`; set the model/effort from the brief with `/model`):

> Read `docs/handoffs/<slug>.md` and carry out the brief. It is your only context. Follow its return protocol (push the branch and open a PR) and tell me when the PR is up.

Windows session (PowerShell: `cd \\wsl.localhost\Ubuntu\home\<user>\projects\miniProjects\202605_chipOid`, then `claude`):

> You are the Windows session for chipOid. Read `docs/WINDOWS_SESSION.md`, then `docs/handoffs/<windows brief>.md`, and carry out that brief. Report in the brief's Report section. Do not run git commands that change anything, and do not edit tracked source files.

## Lessons from v0.10

- **WSL has no Tk.** GUI widget code can only be compile-checked in WSL. The Windows smoke test is its first real run, so say so in the Windows brief.
- **Windows tests need an unlocked PC for anything mouse-driven.** On a locked PC the session can only drive the GUI by keyboard (Tk ignores posted mouse clicks). Tell the human beforehand which steps need them at the desk.
- **The Windows session runs git read-only through `wsl.exe git -C <repo> …`.** That avoids Git-for-Windows file-mode and line-ending noise on the share.
- **The `data/` symlink doesn't resolve from Windows,** so `tests/test_pipeline_in_memory.py` skips there. To run it, use a scratch folder with `data` as a junction to `D:\projects\chipOid\data`.
- **Building over the share takes 10–12 min** (2–4 min from a native path).
- **matplotlib:** without `matplotlib.use("Agg")`, Windows picks TkAgg and figures built on the GUI worker thread can crash (#17). Agg is now forced in `viz.py`.
- **Platform-identical numbers.** v0.9 outputs differed between Linux and Windows through float round-off (rotate/de-rotate of Hough centres). Detected wells now keep their exact Hough centre, so Linux and Windows agree exactly.
- **The lab's hand-picked wells are a brightfield judgement.** Disagreements with the threshold are findings to discuss with the lab, not automatically bugs (e.g. EXP24 TX100 r00c02, which v0.9 had misread).
- **GitHub CLI quirks:**
  - Squash-merged branches need `git branch -D` (not `-d`).
  - `gh issue edit` here has no `--remove-milestone`; use `gh api -X PATCH repos/Rtasseff/chipOid/issues/<n> -F milestone=null`.
  - `Fixes #n` in a pushed commit can take a few seconds to close the issue; check before closing it by hand.
- **The worktree script seeds the brief from the template.** Overwrite that copy with the real brief (and read it first if your tools require it) before committing it on the branch.

## Where things live

| What | Where |
|---|---|
| Plan, backlog, decisions | GitHub issues and milestones (`gh issue list`) |
| Briefs and Windows reports (records) | `docs/handoffs/` |
| Validation tool | `scripts/validate_exp.py` (paths are arguments) |
| Lab data, reference runs, machine paths | `LOCAL_SETUP.md` (gitignored) → `output/v010_validation/` on D drive |
| Windows build | `docs/WINDOWS_SESSION.md` (workflow), `docs/WINDOWS_DESKTOP_BUNDLE.md` (procedure + smoke tests) |
| User-facing docs that ship with the `.exe` | `docs/RELEASE_NOTES_v<x>.md`, `docs/LIVE_DEAD_GUIDE.md` |
