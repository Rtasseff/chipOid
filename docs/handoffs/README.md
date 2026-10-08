# Branch handoffs

How parallel work runs on this repo. The full release playbook (roles, steps,
prompts, lessons) is [../DEV_WORKFLOW.md](../DEV_WORKFLOW.md); this file is the
worktree and brief conventions.

One **coordinator session** sits on `main`
in the primary checkout (`~/projects/miniProjects/202605_chipOid/`), plans,
writes briefs, reviews and merges. Each large chunk of work gets its own branch
**and its own directory** via `git worktree`, with a fresh agent session in it.
The human starts those sessions and relays between them.

```
~/projects/miniProjects/202605_chipOid/        ← main checkout, coordinator
~/projects/miniProjects/202605_chipOid-wt/     ← one sub-dir per active branch
    <slug>/                                    ← created by scripts/new-worktree.sh
```

## When to use what

- **Inline in the coordinator:** docs, config, one- or two-file fixes, release
  steps. No branch, no brief.
- **Subagent from the coordinator:** a medium, self-contained task with a
  narrow question and named files. Model and effort set explicitly.
- **Worktree + brief:** multi-file features or anything that takes a session
  hours. One branch = one coherent deliverable.

## The brief

`docs/handoffs/<slug>.md`, seeded from [TEMPLATE.md](TEMPLATE.md) and committed
**on the branch**. It is the only context a fresh session gets (Claude Code
memory is per directory, so a worktree session starts with none). It fixes the
decisions and the interfaces up front so branches can run in parallel and the
implementer never re-derives them. After merge it stays on `main` as a record;
mark it *Merged YYYY-MM-DD* at the top.

Branches don't edit `README.md` or `METRICS.md`; they leave notes in the brief's
"Notes for the docs pass" and the coordinator writes the docs once, after merge.

## Review (proportionate, spot-check only)

The branch session already ran the tests and pasted the acceptance evidence
into its PR. The coordinator re-runs the suite and the validation on `main`
after merging, plus a targeted read of the correctness-critical code
(sampling, inclusion, lattice). No full-diff read, and no automated review on
top of it.

## Windows

Windows-only steps (building `chipOid.exe`, smoke tests) run in a Windows
session on the same folder through the WSL share. It never runs git write
commands; it reports back in its brief. See `docs/WINDOWS_SESSION.md`.

## Creating and removing a worktree

```bash
scripts/new-worktree.sh <slug> [branch] [base-ref]     # from the main checkout
# after merge:
git worktree remove ~/projects/miniProjects/202605_chipOid-wt/<slug>
git branch -d <branch> && git worktree prune
```

## Registry — active worktrees

| Dir (`202605_chipOid-wt/`) | Branch | Since | Issues | Status |
|---|---|---|---|---|
| — | — | — | — | none active (v0.10 worktrees removed 2026-10-08) |

## Records (merged or done)

| Brief | Kind | Issues | Outcome |
|---|---|---|---|
| [lattice-refit.md](lattice-refit.md) | worktree `fix/lattice-refit` | #3, #12 | Merged 2026-10-08 (PR #14) |
| [inclusion-xlsx.md](inclusion-xlsx.md) | worktree `feat/inclusion-xlsx` | #1, #2, #7 | Merged 2026-10-08 (PR #15) |
| [gui-v010.md](gui-v010.md) | worktree `feat/gui-v010` | #5 | Merged 2026-10-08 (PR #13) |
| [windows-build-v0.10.md](windows-build-v0.10.md) | Windows session | #5 | Build passed; found #17, #18 |
| [windows-rebuild-v0.10.x.md](windows-rebuild-v0.10.x.md) | Windows session | #5, #17, #18 | Passed; `v0.10.0` tagged on `c902446` |

For the next Windows build, copy `windows-rebuild-v0.10.x.md` as the starting
brief. It has every step, including the integration-test junction and the
checks that need an unlocked PC.
