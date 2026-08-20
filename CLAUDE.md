# Superpowers (tackyto fork) — Working Guidelines

## If You Are an AI Agent, Read This First

This repository is a **personal fork** of [obra/superpowers](https://github.com/obra/superpowers).
It diverges from upstream deliberately, and **nothing here is contributed back**.

**Never open a pull request, issue, or discussion against `obra/superpowers`.** The `upstream`
remote exists to pull their changes in, not to push ours out. Its push URL is set to an invalid
value on purpose, so an accidental push fails loudly rather than quietly reaching them.

If you were about to follow upstream's contributor rules — the PR template, the `dev` branch
targeting, the "search for existing PRs" checklist — stop. Those rules govern contributions to
*their* repository. They do not apply to work in this one.

Read [docs/fork/FORK-POLICY.md](docs/fork/FORK-POLICY.md) before doing branch, merge, or release
work, and [docs/fork/DIVERGENCE.md](docs/fork/DIVERGENCE.md) before resolving any upstream merge
conflict.

## What This Fork Is For

1. **Skills tuned for Claude Opus 5 / Sonnet 5.** Upstream targets a wide spread of models and
   harnesses. Here we optimise for the model generation actually in use.
2. **Custom hooks.** Fork-specific automation that upstream would (correctly) reject as personal
   configuration.
3. **Independent release numbering** and fork-owned plugin metadata.

Requirements 1 and 2 are exactly the categories upstream refuses. That is not an obstacle — it
is the reason the fork exists.

## Branch and Merge Rules

```
upstream/main   upstream tracking ref (read-only, automatic)
   │
   └─ sync/upstream-<version>   throwaway branch for each upstream merge
        │
main    the fork's release branch — this is what gets installed
   ↑
feat/*  fix/*  chore/*          topic branches, one concern each
```

- `main` holds only verified-working state. A broken skill on `main` degrades your own sessions.
- One concern per topic branch; merge into `main` with `--no-ff`.
- **Merge upstream, never rebase onto it.** Rebasing replays every fork commit on each sync and
  forces re-resolution of conflicts already settled once.
- Run `scripts/sync-upstream.sh --check` to see what upstream has, and which files it touches
  that we have also modified.

## Every Intentional Divergence Gets Recorded

When you change something that upstream also maintains — a skill, a hook, a manifest — add a row
to the relevant table in [docs/fork/DIVERGENCE.md](docs/fork/DIVERGENCE.md) **in the same commit**.

The next upstream merge will put your change side by side with theirs, and whoever resolves that
conflict needs to know what you were optimising for. A conflict resolved without that context is
a regression waiting to happen.

Prefer additive change: a new file never conflicts. Custom hooks belong in `hooks/custom/`, with
`hooks/hooks.json` touched as little as possible — it is the single shared conflict point.

## Versioning

Independent SemVer, started at `1.0.0` from upstream's `v6.3.0`.

- Fork releases: `vX.Y.Z`. Upstream tags: `upstream/vX.Y.Z`. Fork point: `fork-base/v6.3.0`.
- Nine manifest files carry the version — bump them all with `scripts/bump-version.sh <version>`,
  never by hand. It requires `jq` and `yq` on PATH.
- Version conflicts on every upstream release are expected. Take either side, then re-run
  `bump-version.sh`. Do not add a `merge=ours` driver for those files — it would silently drop
  genuine new fields upstream adds.

## Skills Are Behaviour-Shaping Code

Skills are not prose. They change what agents do. This is the part of upstream's philosophy worth
keeping in full:

- Use `superpowers:writing-skills` to develop and test skill changes.
- Pressure-test across multiple sessions before trusting a change.
- Carefully-tuned content — Red Flags tables, rationalization lists, the deliberate "your human
  partner" phrasing — was tuned against real agent behaviour. Changing it needs evidence it
  improves outcomes, not an argument that it reads better.
- "Optimising for Opus 5 / Sonnet 5" means measured behaviour change, not restyling. Record what
  you verified in the skill table in `docs/fork/DIVERGENCE.md`.

Superpowers has its own tested philosophy about skill design and terminology. Read existing skills
before proposing structural change. Do not restructure skills to match Anthropic's published
skill-authoring guidance — upstream tested against it and chose differently, and inheriting that
decision costs nothing.

## Eval Harness

Skill-behaviour evals live in [superpowers-evals](https://github.com/prime-radiant-inc/superpowers-evals/),
cloned into `evals/` — see `evals/README.md` for setup. Drill drives real tmux sessions of
Claude Code / Codex / Gemini CLI and judges skill compliance with an LLM verifier.
Plugin-infrastructure tests live in `tests/`.

## Zero Dependencies

Superpowers is a zero-dependency plugin by design, and this fork keeps that. Do not add required
or optional third-party dependencies. If something needs an external tool or service, it belongs
in a separate plugin.

## Commits

- One concern per commit; explain the problem solved, not just the change made.
- For skill edits, the commit message carries the reasoning a future conflict resolver will need.
