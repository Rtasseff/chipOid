#!/bin/bash
# ============================================================================
# chipOid - create a git worktree for a bucket of work
# ============================================================================
# Usage (from the main checkout):
#   scripts/new-worktree.sh <slug> [branch-name] [base-ref]
#
#   slug         dir name under $WT_ROOT and the handoff doc name
#                (docs/handoffs/<slug>.md). Lowercase, digits, hyphens.
#   branch-name  default: feature/<slug>. An existing branch is checked out
#                as-is; otherwise it is created from base-ref.
#   base-ref     default: main.
#
# What it does:
#   1. git worktree add  $WT_ROOT/<slug>  <branch>
#   2. recreates the gitignored data/ output/ dist/ build/ symlinks (same
#      D-drive targets as the main checkout) and copies LOCAL_SETUP.md
#   3. builds .venv and installs the package editable with dev extras
#   4. seeds docs/handoffs/<slug>.md from docs/handoffs/TEMPLATE.md if the
#      branch doesn't already have one
#   5. runs the test suite once and prints the baseline count
#
# Conventions: docs/handoffs/README.md
# ============================================================================
set -euo pipefail

SLUG="${1:-}"
BRANCH="${2:-}"
BASE_REF="${3:-main}"
WT_ROOT="${WT_ROOT:-$HOME/projects/miniProjects/202605_chipOid-wt}"

usage() { sed -n '2,24p' "$0"; exit 1; }
[[ -z "$SLUG" ]] && usage
[[ "$SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "ERROR: slug must be lowercase letters/digits/hyphens: '$SLUG'"; exit 1; }
[[ -z "$BRANCH" ]] && BRANCH="feature/$SLUG"

MAIN_DIR="$(git rev-parse --show-toplevel)"
DEST="$WT_ROOT/$SLUG"
TEMPLATE="$MAIN_DIR/docs/handoffs/TEMPLATE.md"

cd "$MAIN_DIR"
[[ -e "$DEST" ]] && { echo "ERROR: $DEST already exists"; exit 1; }
[[ -f "$TEMPLATE" ]] || { echo "ERROR: missing $TEMPLATE"; exit 1; }
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "WARNING: main checkout has uncommitted changes; the branch is cut from '$BASE_REF', not the working tree."
fi

mkdir -p "$WT_ROOT"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "==> Branch $BRANCH exists; adding worktree at $DEST"
  git worktree add "$DEST" "$BRANCH"
else
  echo "==> Creating $BRANCH from $BASE_REF at $DEST"
  git worktree add -b "$BRANCH" "$DEST" "$BASE_REF"
fi
BASE_SHA="$(git -C "$DEST" rev-parse --short HEAD)"

echo "==> Linking data/ output/ dist/ build/ and copying LOCAL_SETUP.md"
for d in data output dist build; do
  if [[ -L "$MAIN_DIR/$d" ]]; then
    ln -s "$(readlink "$MAIN_DIR/$d")" "$DEST/$d"
  fi
done
[[ -f LOCAL_SETUP.md ]] && cp LOCAL_SETUP.md "$DEST/LOCAL_SETUP.md"

echo "==> Creating .venv and installing chipoid[dev] (takes a minute)"
python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install --quiet --upgrade pip
"$DEST/.venv/bin/pip" install --quiet -e "$DEST[dev]"

HANDOFF="$DEST/docs/handoffs/$SLUG.md"
if [[ -f "$HANDOFF" ]]; then
  echo "==> Handoff doc already on branch: docs/handoffs/$SLUG.md (left untouched)"
else
  echo "==> Seeding docs/handoffs/$SLUG.md from template"
  sed -e "s|{{SLUG}}|$SLUG|g" \
      -e "s|{{BRANCH}}|$BRANCH|g" \
      -e "s|{{BASE_REF}}|$BASE_REF|g" \
      -e "s|{{BASE_SHA}}|$BASE_SHA|g" \
      -e "s|{{DATE}}|$(date +%Y-%m-%d)|g" \
      "$TEMPLATE" > "$HANDOFF"
fi

echo "==> Baseline test run"
( cd "$DEST" && ./.venv/bin/python -m pytest tests/ -q 2>&1 | tail -1 )

cat <<EOF

Done.
  Worktree : $DEST
  Branch   : $BRANCH  (base $BASE_REF @ $BASE_SHA)
  Handoff  : docs/handoffs/$SLUG.md

Next (coordinator session):
  1. Fill in the handoff doc, then commit it ON THE BRANCH:
       git -C $DEST add docs/handoffs/$SLUG.md && git -C $DEST commit -m "handoff: $SLUG"
  2. Add a row to the registry in docs/handoffs/README.md (on main).
  3. Open a new agent session in $DEST.
EOF
