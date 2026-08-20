#!/usr/bin/env python3
"""Session telemetry hook: Stop and SubagentStop.

Folds the new part of the session transcript into (turn x skill) segments
and appends them as JSONL.

This hook never writes to stdout and never exits non-zero. A Stop hook that
says anything can change what the harness does, and one that fails would
break the session it exists only to observe.
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telemetry_lib import segments as sg  # noqa: E402
from telemetry_lib import skills as sk  # noqa: E402
from telemetry_lib import store  # noqa: E402
from telemetry_lib import transcript as tx  # noqa: E402


def transcript_digest(transcript_path):
    """8 hex chars identifying one transcript file.

    Used both as the suffix of the state key (see `state_key`) and, emitted
    as the `agent_id` schema field, to distinguish concurrent subagents of
    one parent: they share the parent's session id and each number their
    turns from 1, so without this nothing in the record tells them apart.
    """
    return hashlib.sha1((transcript_path or "").encode("utf-8")).hexdigest()[:8]


def state_key(session, transcript_path):
    """A key unique to one transcript, not merely to one session.

    A subagent's transcript is a separate file carrying its parent's session
    id. Keying on the session alone would make parent and subagent share one
    read offset and skip each other's records.
    """
    return "%s-%s" % (session, transcript_digest(transcript_path))


def subagent_type_for(transcript_path):
    """The agent type recorded beside a subagent transcript, or None.

    Claude Code writes `<name>.meta.json` next to `<name>.jsonl` for
    subagents; without it this schema field would always be null.
    """
    if not transcript_path:
        return None
    meta = os.path.splitext(transcript_path)[0] + ".meta.json"
    try:
        with open(meta, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded.get("agentType")


def project_of(cwd):
    """Repository name for `cwd`, by walking up to a .git — no git process.

    Shelling out to git would add a subprocess to every turn for a value the
    filesystem already answers.
    """
    if not cwd:
        return None
    start = os.path.abspath(cwd)
    path = start
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return os.path.basename(path)
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.basename(start)
        path = parent


def plugin_root():
    """The installed plugin directory: hooks/custom/telemetry.py is two down."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return root
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def run(payload, base):
    """Process one hook invocation. Returns how many segments were written."""
    session = payload.get("session_id") or "unknown"
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0

    digest = transcript_digest(path)
    key = state_key(session, path)
    state = store.load_state(key, base, sg.new_state())
    records, total = tx.read_new_records(path, state.get("line", 0))
    state["line"] = total
    if not records:
        store.save_state(key, state, base)
        return 0

    root = plugin_root()
    ctx = {
        "session": session,
        "agent_id": digest,
        "project": project_of(payload.get("cwd")),
        "plugin_root": root,
        "plugin_version": sk.plugin_version(root),
        "subagent_type": subagent_type_for(path),
        "parent_turn": None,
    }

    rows, state = sg.build_segments(records, state, ctx)
    store.append_records(rows, base)
    store.save_state(key, state, base)
    store.prune_states(base)
    return len(rows)


def main():
    base = store.base_dir()
    session = "unknown"
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        session = payload.get("session_id") or "unknown"
        run(payload, base)
    except Exception as error:
        store.log_error(base, session, "%s: %s" % (type(error).__name__, error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
