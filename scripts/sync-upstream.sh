#!/usr/bin/env bash
#
# sync-upstream.sh — pull obra/superpowers changes into this fork.
#
# Usage:
#   sync-upstream.sh [--check] [--ref <ref>] [--branch <name>]
#
#   --check          Show what is new upstream and exit without changing anything.
#   --ref <ref>      Upstream ref to merge (default: upstream/main).
#   --branch <name>  Name for the sync branch (default: sync/upstream-<ref-slug>).
#
# Merges — never rebases. See docs/fork/FORK-POLICY.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UPSTREAM_REMOTE="upstream"
BASE_BRANCH="main"

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
  echo "error: $*" >&2
  exit 1
}

check_only=0
ref="${UPSTREAM_REMOTE}/main"
branch=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) check_only=1; shift ;;
    --ref) [[ $# -ge 2 ]] || die "--ref needs a value"; ref="$2"; shift 2 ;;
    --branch) [[ $# -ge 2 ]] || die "--branch needs a value"; branch="$2"; shift 2 ;;
    --help | -h) usage; exit 0 ;;
    *) die "unknown argument '$1' (see --help)" ;;
  esac
done

cd "$REPO_ROOT"

git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1 ||
  die "remote '$UPSTREAM_REMOTE' is not configured — see docs/fork/FORK-POLICY.md"

echo "Fetching $UPSTREAM_REMOTE..."
git fetch "$UPSTREAM_REMOTE"

git rev-parse --verify --quiet "$ref" >/dev/null ||
  die "ref '$ref' not found after fetch"

merge_base="$(git merge-base "$BASE_BRANCH" "$ref")"
ahead="$(git rev-list --count "${merge_base}..${ref}")"

echo ""
echo "Fork base branch : $BASE_BRANCH ($(git rev-parse --short "$BASE_BRANCH"))"
echo "Upstream ref     : $ref ($(git rev-parse --short "$ref"))"
echo "Last common      : $(git rev-parse --short "$merge_base")"
echo "New upstream commits: $ahead"

if [[ "$ahead" -eq 0 ]]; then
  echo ""
  echo "Already up to date with $ref. Nothing to merge."
  exit 0
fi

echo ""
echo "Upstream commits not yet in $BASE_BRANCH:"
git log --oneline --no-decorate "${merge_base}..${ref}" | sed 's/^/  /'

echo ""
echo "Files upstream touched that this fork has also modified (expect conflicts):"
overlap="$(comm -12 \
  <(git diff --name-only "${merge_base}..${ref}" | sort) \
  <(git diff --name-only "${merge_base}..${BASE_BRANCH}" | sort))"
if [[ -n "$overlap" ]]; then
  echo "$overlap" | sed 's/^/  /'
else
  echo "  (none)"
fi

if [[ "$check_only" -eq 1 ]]; then
  echo ""
  echo "--check: stopping here."
  exit 0
fi

[[ -z "$(git status --porcelain)" ]] ||
  die "working tree is dirty — commit or stash before syncing"

if [[ -z "$branch" ]]; then
  slug="$(echo "$ref" | tr '/' '-')"
  branch="sync/${slug}-$(git rev-parse --short "$ref")"
fi

echo ""
echo "Creating sync branch '$branch' from $BASE_BRANCH..."
git switch -c "$branch" "$BASE_BRANCH"

echo "Merging $ref (no fast-forward)..."
if git merge --no-ff --no-edit "$ref"; then
  merge_status="clean"
else
  merge_status="conflicted"
fi

cat <<NEXT

--------------------------------------------------------------------
Merge result: $merge_status
Branch:       $branch

Next steps:
NEXT

if [[ "$merge_status" == "conflicted" ]]; then
  cat <<'NEXT'
  1. Resolve conflicts. Consult docs/fork/DIVERGENCE.md for why our side
     looks the way it does before overwriting anything.
  2. git add -A && git commit
NEXT
else
  echo "  1. Review the merge: git diff HEAD~1"
fi

cat <<'NEXT'
  3. scripts/bump-version.sh <fork-version>   # re-assert fork version numbers
  4. Run the test suite / evals for any skill upstream touched
  5. Add a row to the sync log in docs/fork/DIVERGENCE.md
  6. git switch main && git merge --no-ff <branch>
--------------------------------------------------------------------
NEXT
