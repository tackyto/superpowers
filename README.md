# Superpowers

Superpowers is a complete software development methodology for your coding agents, built on top of a set of composable skills and some initial instructions that make sure your agent uses them.

## Table of Contents

- [How it works](#how-it-works)
- [Commercial Services](#commercial-services)
- [Getting Started](#installation)
  - [Claude Code](#claude-code)
  - [Antigravity](#antigravity)
  - [Codex App](#codex-app)
  - [Codex CLI](#codex-cli)
  - [Cursor](#cursor)
  - [Devin CLI](#devin-cli)
  - [Factory Droid](#factory-droid)
  - [Gemini CLI](#gemini-cli)
  - [GitHub Copilot CLI](#github-copilot-cli)
  - [Grok Build CLI](#grok-build-cli)
  - [Kimi Code](#kimi-code)
  - [OpenCode](#opencode)
  - [Pi](#pi)
  - [Hermes Agent](#hermes-agent)
- [The Basic Workflow](#the-basic-workflow)
- [Community](#community)
- [What's Inside](#whats-inside)
- [Philosophy](#philosophy)
- [Contributing](#contributing)
- [Updating](#updating)
- [License](#license)
- [Visual companion telemetry](#visual-companion-telemetry)

## How it works

It starts from the moment you fire up your coding agent. As soon as it sees that you're building something, it *doesn't* just jump into trying to write code. Instead, it steps back and asks you what you're really trying to do. 

Once it's teased a spec out of the conversation, it shows it to you in chunks short enough to actually read and digest. 

After you've signed off on the design, your agent puts together an implementation plan that's clear enough for an enthusiastic junior engineer with poor taste, no judgement, no project context, and an aversion to testing to follow. It emphasizes true red/green TDD, YAGNI (You Aren't Gonna Need It), and DRY. 

Next up, once you say "go", it launches a *subagent-driven-development* process, having agents work through each engineering task, inspecting and reviewing their work, and continuing forward. It's not uncommon for your agent to work autonomously for a couple hours at a time without deviating from the plan you put together.

There's a bunch more to it, but that's the core of the system. And because the skills trigger automatically, you don't need to do anything special. Your coding agent just has Superpowers.

## Commercial Services

If you're using Superpowers in enterprise and could benefit from commercial support, additional tooling, or managed spending, please don't hesitate to drop us a line at sales@primeradiant.com.

## Installation

Installation differs by harness. If you use more than one, install Superpowers separately for each one.

> **This is a fork.** Every command below installs
> [`tackyto/superpowers`](https://github.com/tackyto/superpowers), not upstream
> [`obra/superpowers`](https://github.com/obra/superpowers). Where a harness ships Superpowers
> through its own curated marketplace — Codex, Cursor, Grok Build CLI, Kimi Code — that listing is
> upstream's build. Install from this repository instead to get the fork, and enable only one of the
> two: they share the plugin name `superpowers`.

### Claude Code

This repository doubles as its own plugin marketplace, so there is no separate marketplace
repository to register.

- Register the marketplace:

  ```bash
  /plugin marketplace add tackyto/superpowers
  ```

- Install the plugin. The name after `@` is the marketplace name declared in
  `.claude-plugin/marketplace.json` — `superpowers-tackyto` — not the GitHub owner:

  ```bash
  /plugin install superpowers@superpowers-tackyto
  ```

Upstream Superpowers is also published on Anthropic's [official plugin
marketplace](https://claude.com/plugins/superpowers) as `superpowers@claude-plugins-official`. That
is upstream's build, not this fork — install one or the other.

### Antigravity

Install Superpowers as a plugin from this repository:

```bash
agy plugin install https://github.com/tackyto/superpowers
```

Antigravity runs the plugin's session-start hook, so Superpowers is active from
the first message. Reinstall with the same command to update.

### Codex App

Superpowers is available via the [official Codex plugin marketplace](https://github.com/openai/plugins).
_That listing is upstream's build, not this fork._

- In the Codex app, click on Plugins in the sidebar.
- You should see `Superpowers` in the Coding section.
- Click the `+` next to Superpowers and follow the prompts.

### Codex CLI

Superpowers is available via the [official Codex plugin marketplace](https://github.com/openai/plugins).
_That listing is upstream's build, not this fork._

- Open the plugin search interface:

  ```bash
  /plugins
  ```

- Search for Superpowers:

  ```bash
  superpowers
  ```

- Select `Install Plugin`.

### Cursor

_Cursor's marketplace lists upstream's build, not this fork._

- In Cursor Agent chat, install from marketplace:

  ```text
  /add-plugin superpowers
  ```

- Or search for "superpowers" in the plugin marketplace.

### Devin CLI

- Install the plugin from this repository:

  ```bash
  devin plugins install tackyto/superpowers
  ```

- Update to the latest version with:

  ```bash
  devin plugins update superpowers
  ```

### Factory Droid

- Register the marketplace:

  ```bash
  droid plugin marketplace add https://github.com/tackyto/superpowers
  ```

- Install the plugin:

  ```bash
  droid plugin install superpowers@superpowers
  ```

  If Droid reports an unknown marketplace, use `superpowers@superpowers-tackyto` instead: the
  suffix is the marketplace name, and this fork renamed it in `.claude-plugin/marketplace.json`.

### Gemini CLI

- Install the extension:

  ```bash
  gemini extensions install https://github.com/tackyto/superpowers
  ```

- Update later:

  ```bash
  gemini extensions update superpowers
  ```

### GitHub Copilot CLI

- Register the marketplace:

  ```bash
  copilot plugin marketplace add tackyto/superpowers
  ```

- Install the plugin:

  ```bash
  copilot plugin install superpowers@superpowers-tackyto
  ```

### Grok Build CLI

Superpowers is available via the [official Grok plugin marketplace](https://github.com/xai-org/plugin-marketplace).
_That listing is upstream's build, not this fork._

- Install the plugin from xAI's official marketplace:

  ```bash
  grok plugin install superpowers@xai-official --trust
  ```

- Or open the marketplace in the TUI, search for Superpowers, and install it:

  ```text
  /marketplace
  ```

### Kimi Code

Kimi Code's plugin marketplace lists upstream Superpowers, not this fork.

- Install directly from this repository:

  ```text
  /plugins install https://github.com/tackyto/superpowers
  ```

- Detailed docs: [docs/README.kimi.md](docs/README.kimi.md)

### OpenCode

OpenCode uses its own plugin install; install Superpowers separately even if you
already use it in another harness.

- Tell OpenCode:

  ```
  Fetch and follow instructions from https://raw.githubusercontent.com/tackyto/superpowers/refs/heads/main/.opencode/INSTALL.md
  ```

- Detailed docs: [docs/README.opencode.md](docs/README.opencode.md)

### Pi

Install Superpowers as a Pi package from this repository:

```bash
pi install git:github.com/tackyto/superpowers
```

For local development, run Pi with this checkout loaded as a temporary package:

```bash
pi -e /path/to/superpowers
```

The Pi package loads the Superpowers skills and a small extension that injects the `using-superpowers` bootstrap at session startup and again after compaction. Pi has native skills, so no compatibility `Skill` tool is required. Subagent and task-list tools remain optional Pi companion packages.

### Hermes Agent

Install Superpowers as a Hermes plugin from this repository:

```bash
hermes plugins install tackyto/superpowers --enable
```

Restart any active Hermes sessions after installing. Note: Hermes has no
post-compaction hook, so a very long session that compacts over its first
turn loses the bootstrap — start a fresh session if skills stop triggering.

## The Basic Workflow

1. **brainstorming** - Activates before writing code. Refines rough ideas through questions, explores alternatives, presents design in sections for validation. Saves design document.

2. **using-git-worktrees** - Activates after design approval. Creates isolated workspace on new branch, runs project setup, verifies clean test baseline.

3. **writing-plans** - Activates with approved design. Breaks work into bite-sized tasks (2-5 minutes each). Every task has exact file paths, complete code, verification steps.

4. **subagent-driven-development** or **executing-plans** - Activates with plan. Dispatches fresh subagent per task with two-stage review (spec compliance, then code quality), or executes in batches with human checkpoints.

5. **test-driven-development** - Activates during implementation. Enforces RED-GREEN-REFACTOR: write failing test, watch it fail, write minimal code, watch it pass, commit. Deletes code written before tests.

6. **requesting-code-review** - Activates between tasks. Reviews against plan, reports issues by severity. Critical issues block progress.

7. **finishing-a-development-branch** - Activates when tasks complete. Verifies tests, presents options (merge/PR/keep/discard), cleans up worktree.

**The agent checks for relevant skills before any task.** Mandatory workflows, not suggestions.

## Community

Superpowers is built by [Jesse Vincent](https://blog.fsck.com) and the rest of the folks at [Prime Radiant](https://primeradiant.com).
This fork is maintained separately at [tackyto/superpowers](https://github.com/tackyto/superpowers)
and is not affiliated with them, so send fork-specific reports here rather than upstream.

- **Issues with this fork**: https://github.com/tackyto/superpowers/issues
- **Issues with upstream Superpowers**: https://github.com/obra/superpowers/issues
- **Discord** (upstream community): [Join us](https://discord.gg/35wsABTejz) for community support, questions, and sharing what you're building with Superpowers
- **Release announcements** (upstream): [Sign up](https://primeradiant.com/superpowers/) to get notified about new versions

## What's Inside

### Skills Library

**Testing**
- **test-driven-development** - RED-GREEN-REFACTOR cycle (includes testing anti-patterns reference)

**Debugging**
- **systematic-debugging** - 4-phase root cause process (includes root-cause-tracing, defense-in-depth, condition-based-waiting techniques)
- **verification-before-completion** - Ensure it's actually fixed

**Collaboration** 
- **brainstorming** - Socratic design refinement
- **writing-plans** - Detailed implementation plans
- **executing-plans** - Batch execution with checkpoints
- **dispatching-parallel-agents** - Concurrent subagent workflows
- **requesting-code-review** - Pre-review checklist
- **receiving-code-review** - Responding to feedback
- **using-git-worktrees** - Parallel development branches
- **finishing-a-development-branch** - Merge/PR decision workflow
- **subagent-driven-development** - Fast iteration with two-stage review (spec compliance, then code quality)

**Meta**
- **writing-skills** - Create new skills following best practices (includes testing methodology)
- **using-superpowers** - Introduction to the skills system

## Philosophy

- **Test-Driven Development** - Write tests first, always
- **Systematic over ad-hoc** - Process over guessing
- **Complexity reduction** - Simplicity as primary goal
- **Evidence over claims** - Verify before declaring success

Read [the original release announcement](https://blog.fsck.com/2025/10/09/superpowers/).

## Contributing

This is a personal fork, and work done here stays here. **Do not open pull requests, issues, or
discussions against [obra/superpowers](https://github.com/obra/superpowers).** The `upstream` remote
exists to pull their changes in, not to push ours out — its push URL is deliberately invalid so an
accidental push fails loudly. See [docs/fork/FORK-POLICY.md](docs/fork/FORK-POLICY.md).

To change something in this fork:

1. Branch off `main` — `feat/*`, `fix/*`, or `chore/*`, one concern each.
2. Follow the `writing-skills` skill for creating and testing new and modified skills.
3. If you touched anything upstream also maintains (a skill, a hook, a manifest), add a row to
   [docs/fork/DIVERGENCE.md](docs/fork/DIVERGENCE.md) **in the same commit**. The next upstream merge
   puts your change side by side with theirs, and whoever resolves that conflict needs to know what
   you were optimising for.
4. Open the PR against **this** repository, filling in the pull request template:

   ```bash
   gh pr create --repo tackyto/superpowers --base main
   ```

   GitHub resolves the parent as the default base repository, so a bare `gh pr create` aims at
   upstream.
5. Merge into `main` with `--no-ff`.

To contribute to Superpowers itself, work from a fresh clone of upstream and follow upstream's own
process (fork, the `dev` branch, their pull request template) rather than carrying this fork's
branches over. Upstream doesn't generally accept contributions of new skills, and any update to a
skill must work across all of the coding agents they support.

Skill-behavior tests use the drill eval harness from [superpowers-evals](https://github.com/prime-radiant-inc/superpowers-evals/), cloned into `evals/` — see `evals/README.md` for setup. Plugin-infrastructure tests live at `tests/` and run via the relevant `run-*.sh`; this repository's `package.json` declares no `test` script.

See `skills/writing-skills/SKILL.md` for the complete guide.

## Updating

Superpowers updates are somewhat coding-agent dependent, but are often automatic.

## License

MIT License - see LICENSE file for details

## Visual companion telemetry

Because skills and plugins don't provide any feedback to creators, we have no idea how many of you are using Superpowers. By default, the Prime Radiant logo on brainstorming's optional visual companion feature is loaded from our website. It includes the version of Superpowers in use. It does not include any details about your project, prompt, or coding agent. We don't see your clicks or anything about what you're building. This helps us have a rough idea of how many folks are using Superpowers and which version of Superpowers they're using. It's 100% optional. To disable this, set the environment variable `SUPERPOWERS_DISABLE_TELEMETRY` to any true value. Superpowers also honors Claude Code's `DISABLE_TELEMETRY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` opt-outs.
