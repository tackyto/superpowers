"""Split a transcript into (turn x skill) segments.

A turn is one human prompt and everything the agent does before it stops.
Within a turn the agent switches skills on its own, so a per-turn total
blends those skills together — which is exactly the comparison this data
exists to support. The unit of record is therefore the segment.

Main-agent and subagent records are accumulated separately, so interleaved
sidechain lines can never pollute the main stream.
"""

import re

from . import skills as sk
from . import transcript as tx

SCHEMA_VERSION = 1

_ZERO_TOKENS = ("in", "out", "thinking", "cache_read", "cache_create_5m", "cache_create_1h")

_COMMAND_NAME = re.compile(r"^<command-name>/[A-Za-z0-9:_-]+</command-name>")


def _command_hint(prompt):
    """Only the slash-command marker leading a prompt — never its prose.

    `invoked_by` needs to know which skill a prompt named, and nothing else.
    The marker must lead the prompt: prose that merely quotes a
    <command-name> marker elsewhere in the text — as this repo's own briefs
    do — is not an invocation, and scanning the whole prompt for one would
    misattribute it. Keeping the prose would also put human prompts in the
    state file on disk.
    """
    stripped = (prompt or "").lstrip()
    match = _COMMAND_NAME.match(stripped)
    if match:
        return match.group(0)
    if stripped.startswith("/"):
        return stripped.split(None, 1)[0]
    return ""


def _new_stream():
    return {
        "turn": 0,
        "seq": 0,
        "active_skill": None,
        "active_skill_rev": None,
        "invoked_by": "model",
        "prompt": "",
        "prev_turn_end_ms": None,
        "last_ms": None,
        "last_blocking": False,
        "mode": None,
        "permission_mode": None,
        "open": None,
    }


def new_state():
    """State carried between hook invocations, stored per session."""
    return {"line": 0, "main": _new_stream(), "sub": _new_stream()}


def _open_segment(stream, ts, wait_ms):
    stream["open"] = {
        "ts": ts,
        "ts_end": ts,
        "turn": stream["turn"],
        "seq": stream["seq"],
        "skill": stream["active_skill"],
        "skill_rev": stream["active_skill_rev"],
        "invoked_by": stream["invoked_by"],
        "first_uuid": None,
        "exec_ms": 0,
        "wait_ms": wait_ms,
        "api_calls": 0,
        "tokens": dict.fromkeys(_ZERO_TOKENS, 0),
        "tools": {},
        "tool_errors": 0,
        "stop_reason": None,
        "compacted": False,
        "model": None,
        "effort": None,
        "branch": None,
        "cc_version": None,
        "mode": stream["mode"],
        "permission_mode": stream["permission_mode"],
    }


def _advance(stream, ts):
    """Move the clock to `ts`, billing the gap to exec or wait."""
    now = tx.ts_ms(ts)
    if now is None:
        return
    segment = stream["open"]
    previous = stream["last_ms"]
    if segment is not None and previous is not None and now > previous:
        gap = now - previous
        if stream["last_blocking"]:
            segment["wait_ms"] += gap
        else:
            segment["exec_ms"] += gap
        segment["ts_end"] = ts
    stream["last_ms"] = now


def _close(stream, out, ctx):
    """Emit the open segment unless it is empty, then clear it."""
    segment = stream["open"]
    stream["open"] = None
    if segment is None:
        return
    if segment["api_calls"] == 0 and segment["exec_ms"] == 0 and segment["wait_ms"] == 0:
        return
    out.append(_finish(segment, ctx))


def _finish(segment, ctx):
    """Turn an accumulator into a complete telemetry record."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "seg",
        "ts": segment["ts"],
        "ts_end": segment["ts_end"],
        "session": ctx.get("session"),
        "turn": segment["turn"],
        "seq": segment["seq"],
        "agent": ctx.get("agent"),
        "agent_id": ctx.get("agent_id"),
        "subagent_type": ctx.get("subagent_type"),
        "parent_turn": ctx.get("parent_turn"),
        "first_uuid": segment["first_uuid"],
        "skill": segment["skill"],
        "skill_rev": segment["skill_rev"],
        "invoked_by": segment["invoked_by"],
        "phase": sk.phase_for(segment["skill"]),
        "project": ctx.get("project"),
        "branch": segment["branch"],
        "cc_version": segment["cc_version"],
        "plugin_version": ctx.get("plugin_version"),
        "model": segment["model"],
        "effort": segment["effort"],
        "mode": segment["mode"],
        "permission_mode": segment["permission_mode"],
        "exec_ms": segment["exec_ms"],
        "wait_ms": segment["wait_ms"],
        "api_calls": segment["api_calls"],
        "tokens": segment["tokens"],
        "tools": segment["tools"],
        "tool_errors": segment["tool_errors"],
        "stop_reason": segment["stop_reason"],
        "compacted": segment["compacted"],
    }


def _feed(stream, records, out, ctx):
    for record in records:
        kind = tx.classify(record)
        ts = record.get("timestamp")

        if kind == tx.MODE:
            stream["mode"] = record.get("mode")
            continue

        if kind == tx.PERMISSION_MODE:
            stream["permission_mode"] = record.get("permissionMode")
            continue

        if kind == tx.USER_PROMPT:
            _close(stream, out, ctx)
            now = tx.ts_ms(ts)
            wait = 0
            if now is not None and stream["prev_turn_end_ms"] is not None:
                wait = max(0, now - stream["prev_turn_end_ms"])
            stream["turn"] += 1
            stream["seq"] = 0
            stream["prompt"] = _command_hint(tx.prompt_text(record))
            stream["invoked_by"] = sk.invoked_by(stream["active_skill"], stream["prompt"])
            stream["last_ms"] = now
            stream["last_blocking"] = False
            _open_segment(stream, ts, wait)
            continue

        if kind == tx.META or kind == tx.OTHER or kind == tx.SESSION_START_HOOK:
            continue

        if kind == tx.TOOL_RESULT:
            _advance(stream, ts)
            if stream["open"] is not None:
                stream["open"]["tool_errors"] += tx.tool_error_count(record)
            stream["last_blocking"] = False
            continue

        # kind == tx.ASSISTANT
        if stream["open"] is None:
            stream["last_ms"] = tx.ts_ms(ts)
            _open_segment(stream, ts, 0)
        _advance(stream, ts)

        segment = stream["open"]
        segment["api_calls"] += 1
        segment["ts_end"] = ts
        if segment["first_uuid"] is None:
            segment["first_uuid"] = record.get("uuid")
        segment["branch"] = record.get("gitBranch") or segment["branch"]
        segment["cc_version"] = record.get("version") or segment["cc_version"]
        segment["effort"] = record.get("effort") or segment["effort"]
        segment["mode"] = stream["mode"]
        segment["permission_mode"] = stream["permission_mode"]
        message = record.get("message") or {}
        segment["model"] = message.get("model") or segment["model"]
        segment["stop_reason"] = message.get("stop_reason")

        usage = tx.usage_of(record)
        for key in _ZERO_TOKENS:
            segment["tokens"][key] += usage[key]

        uses = tx.tool_uses(record)
        for name, _params in uses:
            segment["tools"][name] = segment["tools"].get(name, 0) + 1

        for name, params in uses:
            if name != "Skill":
                continue
            _close(stream, out, ctx)
            stream["active_skill"] = params.get("skill")
            stream["active_skill_rev"] = sk.skill_rev(
                stream["active_skill"], ctx.get("plugin_root"))
            stream["invoked_by"] = sk.invoked_by(stream["active_skill"], stream["prompt"])
            stream["seq"] += 1
            _open_segment(stream, ts, 0)

        stream["last_blocking"] = any(
            name in sk.HUMAN_BLOCKING_TOOLS for name, _params in uses)

        stream["prev_turn_end_ms"] = tx.ts_ms(ts)


def _flush_if_stopped(stream, records, out, ctx):
    """Close the open segment only when the model actually stopped.

    The Stop hook may fire before the last assistant line reaches the file.
    Holding the segment open until a non-tool_use stop_reason appears means
    the tail arrives in the next batch instead of being lost or double-counted.
    """
    last_assistant = None
    for record in records:
        if tx.classify(record) == tx.ASSISTANT:
            last_assistant = record
    if last_assistant is None:
        return
    stop_reason = (last_assistant.get("message") or {}).get("stop_reason")
    if stop_reason not in (None, "tool_use"):
        _close(stream, out, ctx)


def build_segments(records, state, ctx):
    """Fold a batch of transcript records into finished segment records."""
    main_records = [r for r in records if not r.get("isSidechain")]
    sub_records = [r for r in records if r.get("isSidechain")]

    out = []

    main_ctx = dict(ctx)
    main_ctx["agent"] = "main"
    main_ctx["subagent_type"] = None
    _feed(state["main"], main_records, out, main_ctx)
    _flush_if_stopped(state["main"], main_records, out, main_ctx)

    if sub_records:
        sub_ctx = dict(ctx)
        sub_ctx["agent"] = "subagent"
        _feed(state["sub"], sub_records, out, sub_ctx)
        _flush_if_stopped(state["sub"], sub_records, out, sub_ctx)

    out.sort(key=lambda record: (record["ts"] or "", record["turn"], record["seq"]))
    return out, state
