# Superpowers (tackyto fork) — Agent Instructions

The working guidelines for this repository are in [CLAUDE.md](CLAUDE.md). Read that file
before doing anything here — it applies whatever harness you are running under, and it is
the authority whenever this file and it disagree.

One rule should not wait for that hop:

**This repository is a personal fork of [obra/superpowers](https://github.com/obra/superpowers).
Never open a pull request, issue, or discussion against `obra/superpowers`.** The `upstream`
remote exists to pull their changes in, not to push ours out. If you were about to follow
upstream's contributor rules — the PR template, the `dev` branch targeting, the "search for
existing PRs" checklist — those govern *their* repository, not this one.

<!--
This file was a symlink to CLAUDE.md until 2026-08-24. Git on Windows cannot reproduce a
symlink without Developer Mode: a default clone writes a 9-byte regular file containing the
path "CLAUDE.md" and reports a clean worktree, and forcing core.symlinks=true without
Developer Mode leaves the file missing altogether. Either way the fork policy stopped being
readable on the platform, silently. Keeping this a real file is what fixes that -- keep it a
pointer rather than a copy, so it cannot drift from CLAUDE.md. See docs/fork/DIVERGENCE.md.
-->
