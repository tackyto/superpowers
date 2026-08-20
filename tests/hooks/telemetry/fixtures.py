"""Builders for synthetic Claude Code transcript records.

Kept in one place so every test speaks the same dialect of the transcript
format. Field names mirror what real transcripts carry, verified against
live sessions on 2026-08-21.
"""

import json


def assistant(
    timestamp,
    uuid="u-assistant",
    output=100,
    thinking=0,
    cache_read=0,
    cache_create_1h=0,
    cache_create_5m=0,
    tools=(),
    stop_reason="tool_use",
    model="claude-opus-5",
    effort="high",
    branch="main",
    version="2.1.4",
    sidechain=False,
):
    """One assistant record. `tools` is a sequence of (name, input_dict)."""
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "gitBranch": branch,
        "version": version,
        "effort": effort,
        "message": {
            "model": model,
            "stop_reason": stop_reason,
            "content": [
                {"type": "tool_use", "name": name, "input": params, "id": "t-%d" % index}
                for index, (name, params) in enumerate(tools)
            ],
            "usage": {
                "input_tokens": 2,
                "output_tokens": output,
                "output_tokens_details": {"thinking_tokens": thinking},
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create_1h + cache_create_5m,
                "cache_creation": {
                    "ephemeral_1h_input_tokens": cache_create_1h,
                    "ephemeral_5m_input_tokens": cache_create_5m,
                },
            },
        },
    }


def prompt(timestamp, text="do the thing", sidechain=False):
    """A real human prompt: string content, no isMeta flag."""
    return {
        "type": "user",
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "message": {"content": text},
    }


def meta(timestamp, text="injected"):
    """A system-injected user record. Never a turn boundary."""
    return {"type": "user", "timestamp": timestamp, "isMeta": True, "message": {"content": text}}


def tool_result(timestamp, errors=0, ok=1, sidechain=False):
    """A tool_result carrier record. Never a turn boundary."""
    blocks = [{"type": "tool_result", "is_error": True} for _ in range(errors)]
    blocks += [{"type": "tool_result", "is_error": False} for _ in range(ok)]
    return {
        "type": "user",
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "message": {"content": blocks},
    }


def mode(value="normal"):
    return {"type": "mode", "mode": value}


def permission_mode(value="auto"):
    return {"type": "permission-mode", "permissionMode": value}


def write_jsonl(path, records, garbage_after=None):
    """Write records as JSONL. `garbage_after` inserts an unparseable line."""
    with open(path, "w", encoding="utf-8") as handle:
        for index, record in enumerate(records):
            handle.write(json.dumps(record) + "\n")
            if garbage_after is not None and index == garbage_after:
                handle.write("{not json at all\n")
