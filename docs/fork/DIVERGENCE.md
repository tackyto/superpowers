# Fork Divergence Ledger

This repository is a **personal fork** of [obra/superpowers](https://github.com/obra/superpowers),
maintained at [tackyto/superpowers](https://github.com/tackyto/superpowers).

It diverges from upstream **on purpose**. Changes made here are **not** intended to be
contributed back. See [FORK-POLICY.md](FORK-POLICY.md) for the rules that follow from that.

- **Fork point:** upstream `v6.3.0` (`b36e082`), tagged locally as `fork-base/v6.3.0`
- **Fork versioning:** independent SemVer starting at `1.0.0`
- **Upstream tags:** namespaced as `upstream/vX.Y.Z` to avoid colliding with fork tags

## Why this file exists

Every upstream sync is a `git merge`, and merges only go smoothly when the person (or agent)
resolving a conflict knows **why** our side looks the way it does. This ledger is that context.

**Rule: any intentional divergence from upstream gets a row in the table below, in the same
commit that introduces it.** A conflict resolved without knowing the intent is a regression
waiting to happen.

## Intentional divergences

| Area | What we changed | Why | Conflict risk |
|---|---|---|---|
| `.claude-plugin/`, `.cursor-plugin/`, `.codex-plugin/`, `.devin-plugin/`, `.kimi-plugin/`, `.hermes-plugin/`, `gemini-extension.json`, `package.json` | `version` reset to `1.0.0`; `author` / `homepage` / `repository` / `websiteURL` / `developerName` point at this fork | Independent release numbering and fork ownership | **High** — upstream bumps `version` on every release. Resolve by taking either side, then re-running the version bump with our number. |
| `.claude-plugin/marketplace.json` | Marketplace renamed `superpowers-dev` → `superpowers-tackyto`; owner updated | Distinguish this fork's marketplace from upstream's | Low |
| `README.md`, `docs/README.kimi.md`, `docs/README.opencode.md`, `.opencode/INSTALL.md`, `docs/porting-to-a-new-harness.md` | Every install instruction points at `tackyto/superpowers`. Claude Code: `/plugin marketplace add tackyto/superpowers` + `/plugin install superpowers@superpowers-tackyto`. Upstream-curated marketplace listings (Anthropic official, Codex, Cursor, Grok, Kimi) are labelled as upstream's build rather than presented as install paths. Issue links split into fork vs upstream. Kimi's `/tree/dev` pin became `/tree/main`, and the OpenCode version-pin example uses a fork tag. | Upstream's instructions install upstream's plugin — the wrong artefact here, and it collides on the shared plugin name `superpowers`. The `@` suffix is the `name` field of `.claude-plugin/marketplace.json`, not the GitHub owner, so it had to follow the marketplace rename. Upstream has a `dev` branch and this fork does not. | **High** — upstream rewrites the install section whenever a harness is added or a marketplace moves. Keep our URLs and re-apply any genuinely new harness section with fork URLs. |
| `README.md` (Contributing section) | Upstream's "fork → `dev` branch → PR to us" steps replaced with this fork's branch / PR / divergence-ledger rules, an explicit "never PR upstream" line, and a pointer for anyone who genuinely wants to contribute to upstream. `npm test` dropped from the test instructions — this repository's `package.json` declares no `scripts` field. | Upstream's steps route contributions at `obra/superpowers` and name a `dev` branch that does not exist here — the same defect that `CLAUDE.md` was rewritten to fix, left standing in the file a human actually reads first. | **High** — upstream edits this section. Ours wins, but read their diff for real process changes worth adopting. |
| `CLAUDE.md` | Upstream's contributor/PR guidance replaced with fork policy | Upstream's `CLAUDE.md` instructs agents to open PRs against `obra/superpowers`. In this fork that is exactly the wrong behaviour. | **High** — upstream edits this file often. Ours always wins; check upstream's diff for anything worth adopting. |
| `scripts/sync-upstream.sh` | New file | Upstream sync workflow | None (new file) |
| `docs/fork/` | New directory | Fork documentation | None (new files) |
| `.github/PULL_REQUEST_TEMPLATE.md` | Shortened to a fork-internal template | Upstream's version demands disclosures aimed at an external maintainer and tells submitters to target a `dev` branch that does not exist here | Low |

> **Install paths verified:** only the Claude Code path was executed end to end
> (`/plugin marketplace add tackyto/superpowers` → `/plugin install superpowers@superpowers-tackyto`).
> The other harnesses' commands are URL substitutions on upstream's text, not tested runs. Factory
> Droid is the one genuinely ambiguous case: upstream documents `superpowers@superpowers` while its
> `marketplace.json` was named `superpowers-dev`, so Droid appears to name the marketplace after the
> repository rather than the manifest. The README keeps `@superpowers` and mentions
> `@superpowers-tackyto` as the fallback.

> Plugin name kept as `superpowers`, and skill directory names kept as-is, deliberately.
> Renaming would touch 115 `superpowers:<skill>` cross-references across 32 files and turn
> every upstream skill update into a conflict. This fork **replaces** upstream rather than
> coexisting with it.

## Skill optimisations (Claude Opus 5 / Sonnet 5)

Skills tuned for the Opus 5 / Sonnet 5 generation. One row per skill, added as the work lands.

| Skill | What changed | Rationale | Verified how |
|---|---|---|---|
| _(none yet)_ | | | |

## Custom hooks

| Hook | File | Trigger | Notes |
|---|---|---|---|
| Session telemetry | `hooks/custom/telemetry`, `hooks/custom/telemetry.py`, `hooks/custom/telemetry_lib/` | `Stop`, `SubagentStop` | Records one JSONL row per (turn × skill) under `~/.claude/superpowers/telemetry/`, for skill-improvement, cost and time analysis. New files only; `hooks/hooks.json` gains two blocks and nothing existing is touched. Python 3 standard library only, no new dependencies. See [telemetry.md](telemetry.md). |

## Upstream sync log

| Date | Upstream ref | Merge commit | Fork version after | Notes |
|---|---|---|---|---|
| 2026-08-21 | `v6.3.0` (`b36e082`) | _(fork point — no merge)_ | `1.0.0` | Baseline |

## Attribution

Upstream copyright and the MIT licence are preserved unchanged in `LICENSE`.
Original work by Jesse Vincent and the Superpowers contributors.
