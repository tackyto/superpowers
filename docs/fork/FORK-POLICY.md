# Fork Policy

`tackyto/superpowers` is a personal fork of [obra/superpowers](https://github.com/obra/superpowers).

## The one rule

**Nothing from this fork goes upstream.** Do not open pull requests, issues, or discussions
against `obra/superpowers` from this repository's work. The `upstream` remote exists to *pull
in* their changes, never to push out ours. Its push URL is deliberately set to an invalid
value so an accidental `git push upstream` fails loudly.

Upstream has a ~94% PR rejection rate and an explicit policy against fork-specific changes,
personal configuration, and agent-generated contributions. Every reason they reject those
applies to this fork by design — that is what a fork is for.

If you find a genuine, general-purpose bug in upstream code while working here, that is worth
reporting *as a fresh, upstream-shaped contribution* made deliberately and separately — not as
a PR carrying this fork's branches or customisations. Ask the human partner first.

## The `gh` trap

GitHub knows this repository is a fork, so **`gh` resolves the parent as the base repository by
default**. A bare `gh pr create` here targets `obra/superpowers`, not this fork — it fails with a
confusing "No commits between main and <branch>" rather than an obvious error, and on a branch
name that happened to exist upstream it would succeed and open a PR at them.

This repository pins the default:

```bash
gh repo set-default tackyto/superpowers     # stored as remote.origin.gh-resolved = base
```

Verify with `gh repo set-default --view` after any fresh clone. Passing `--repo
tackyto/superpowers` explicitly on `gh pr` / `gh issue` commands costs nothing and removes the
question entirely.

## Branch model

```
upstream/main   upstream tracking ref (read-only, automatic)
   │
   └─ sync/upstream-<version>   throwaway branch for resolving each upstream merge
        │
main    the fork's release branch — this is what gets installed
   ↑
feat/*  fix/*  chore/*          topic branches, one concern each
```

- `main` holds only verified-working state. A broken skill on `main` degrades your own sessions.
- Topic branches merge into `main` with `--no-ff` so each change stays reviewable in history.
- Upstream is always **merged**, never rebased onto. Rebasing would replay every fork commit
  on each sync and force re-resolution of conflicts already settled once.

## Versioning

Independent SemVer, started at `1.0.0` from upstream's `v6.3.0`.

- Fork releases are tagged `vX.Y.Z`.
- Upstream tags are fetched into the `upstream/` tag namespace (`upstream/v6.3.0`).
- The fork point is tagged `fork-base/v6.3.0`.
- Nine manifest files carry the version. `scripts/bump-version.sh <version>` updates all of
  them at once — it needs `jq` and **mikefarah/yq** (the Go one; the Python `yq` is a `jq`
  wrapper and cannot run its filters) on PATH. Doing this from Windows Git Bash:
  [windows-maintenance.md](windows-maintenance.md).

## Syncing from upstream

```bash
scripts/sync-upstream.sh --check          # what's new upstream?
scripts/sync-upstream.sh                  # fetch, branch, merge
# resolve conflicts, then:
scripts/bump-version.sh <fork-version>    # re-assert fork version numbers
git switch main && git merge --no-ff sync/upstream-<version>
```

Version-field conflicts across the nine manifests are expected on every upstream release.
Take either side; `bump-version.sh` overwrites them all afterwards. Do **not** add a
`merge=ours` driver for those files — it would silently drop genuine new fields upstream adds.

After every sync, add a row to the sync log in [DIVERGENCE.md](DIVERGENCE.md).

## Keeping the conflict surface small

- **Custom hooks** go in `hooks/custom/` as new files. Touch `hooks/hooks.json` as little as
  possible — that file is the only shared conflict point.
- **Skill edits** land one skill per commit, with the reasoning in the commit message.
  A future conflict resolver needs to know what we were optimising for.
- **New capability** prefers a new file over an edit to an upstream file.
- **Every intentional divergence** gets a row in [DIVERGENCE.md](DIVERGENCE.md) in the same
  commit that creates it.
