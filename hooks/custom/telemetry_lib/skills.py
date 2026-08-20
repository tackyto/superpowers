"""Map a skill name to its phase, its revision, and how it was invoked."""

import hashlib
import json
import os

# The work phase each skill represents. Adding a skill means adding one line.
# Anything absent falls through to "unknown" rather than guessing.
PHASE_BY_SKILL = {
    "brainstorming": "brainstorming",
    "writing-plans": "planning",
    "test-driven-development": "implementing",
    "executing-plans": "implementing",
    "subagent-driven-development": "implementing",
    "systematic-debugging": "debugging",
    "requesting-code-review": "reviewing",
    "receiving-code-review": "reviewing",
    "verification-before-completion": "reviewing",
    "finishing-a-development-branch": "finishing",
    "dispatching-parallel-agents": "implementing",
}

# Tools that stop and wait for a person. Time spent after one of these is
# the human's, not the skill's — see the timing rules in the design doc.
HUMAN_BLOCKING_TOOLS = frozenset({"AskUserQuestion", "ExitPlanMode"})


def short_name(skill):
    """"superpowers:brainstorming" -> "brainstorming"."""
    if not skill:
        return None
    return skill.split(":", 1)[1] if ":" in skill else skill


def phase_for(skill):
    return PHASE_BY_SKILL.get(short_name(skill) or "", "unknown")


def skill_rev(skill, plugin_root):
    """First 8 hex chars of sha256(SKILL.md). None when unresolvable.

    This is the skill's version. Skills carry no version number of their
    own, and the plugin version does not move when a SKILL.md is edited —
    so without this hash, before-and-after comparisons are impossible.
    """
    if not skill or not plugin_root or not skill.startswith("superpowers:"):
        return None
    path = os.path.join(plugin_root, "skills", short_name(skill), "SKILL.md")
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()[:8]
    except OSError:
        return None


def plugin_version(plugin_root):
    if not plugin_root:
        return None
    path = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return (json.load(handle) or {}).get("version")
    except (OSError, ValueError):
        return None


def invoked_by(skill, prompt):
    """"user" when the turn's prompt invoked this exact skill by slash command.

    Claude Code exposes a plugin skill's slash command under two names: the
    bare short name ("/brainstorming") and the full "plugin:skill" form
    ("/superpowers:brainstorming"). Both must be matched, in both the
    <command-name> marker form and the bare "/name" form, or a skill invoked
    by its plugin-qualified name reads as having fired on its own — the
    opposite of what this field exists to capture.

    The marker or slash must lead the prompt. Prose that merely quotes a
    <command-name> marker — as this repo's own briefs do — is not an
    invocation, so a substring match would misattribute it.

    A skill that only ever runs because a human typed its name is a skill
    that is failing to trigger on its own — which is the whole point of
    recording this.
    """
    name = short_name(skill)
    if not name or not prompt:
        return "model"
    candidates = [name]
    if skill and ":" in skill:
        candidates.append(skill)
    stripped = prompt.lstrip()
    for candidate in candidates:
        if stripped.startswith("<command-name>/%s</command-name>" % candidate):
            return "user"
        if stripped.startswith("/" + candidate):
            return "user"
    return "model"
