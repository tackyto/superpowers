#!/usr/bin/env bash
#
# AGENTS.md has to survive a native Windows clone.
#
# It used to be a symlink to CLAUDE.md, which git on Windows cannot reproduce
# without Developer Mode. The default clone silently writes a 9-byte regular
# file containing the string "CLAUDE.md" and reports a clean worktree, so the
# file that tells an agent never to open a PR against upstream degrades into a
# path with no instruction in it. Forcing core.symlinks=true without Developer
# Mode is worse: the file is not created at all.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENTS="$REPO_ROOT/AGENTS.md"

FAILURES=0

pass() {
    echo "  [PASS] $1"
}

fail() {
    echo "  [FAIL] $1"
    if [[ -n "${2:-}" ]]; then
        echo "         $2"
    fi
    FAILURES=$((FAILURES + 1))
}

echo "AGENTS.md portability"

if [[ -L "$AGENTS" ]]; then
    fail "AGENTS.md is a regular file, not a symlink" \
         "it is a symlink to $(readlink "$AGENTS")"
elif [[ -f "$AGENTS" ]]; then
    pass "AGENTS.md is a regular file, not a symlink"
else
    fail "AGENTS.md is a regular file, not a symlink" "it does not exist"
fi

# The index mode is what a clone materialises, so it is the mode that decides
# what a Windows checkout gets. A working tree can look right while the index
# still says 120000.
index_mode="$(git -C "$REPO_ROOT" ls-files -s -- AGENTS.md | awk '{print $1}')"
if [[ "$index_mode" == "100644" ]]; then
    pass "git records AGENTS.md as a regular file (100644)"
else
    fail "git records AGENTS.md as a regular file (100644)" \
         "index mode is ${index_mode:-<not tracked>}"
fi

if [[ -f "$AGENTS" ]] && grep -q 'CLAUDE\.md' "$AGENTS"; then
    pass "AGENTS.md points the reader at CLAUDE.md"
else
    fail "AGENTS.md points the reader at CLAUDE.md"
fi

# A reader that stops here must still get the one rule that cannot be wrong.
if [[ -f "$AGENTS" ]] && grep -q 'obra/superpowers' "$AGENTS"; then
    pass "AGENTS.md carries the never-PR-upstream rule"
else
    fail "AGENTS.md carries the never-PR-upstream rule"
fi

# It is a pointer, not a copy: duplicated policy is policy that drifts.
if [[ -f "$AGENTS" ]] && grep -q '^## Versioning' "$AGENTS"; then
    fail "AGENTS.md stays a pointer rather than a copy of CLAUDE.md" \
         "it has grown CLAUDE.md's own sections"
else
    pass "AGENTS.md stays a pointer rather than a copy of CLAUDE.md"
fi

# Same failure, any other file: nothing tracked may be a symlink.
symlinks="$(git -C "$REPO_ROOT" ls-files -s | awk '$1 == "120000" {print $4}')"
if [[ -z "$symlinks" ]]; then
    pass "no tracked file is a symlink"
else
    fail "no tracked file is a symlink" "$(echo "$symlinks" | tr '\n' ' ')"
fi

echo ""
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES check(s) failed."
    exit 1
fi
echo "Agent-instructions tests passed"
