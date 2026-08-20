"""Classify and read Claude Code transcript records.

This is the only module that knows the transcript's field names. Everything
here is a pure function over an already-parsed record, except the one
incremental reader.
"""

import json
from datetime import datetime

USER_PROMPT = "user_prompt"
TOOL_RESULT = "tool_result"
META = "meta"
ASSISTANT = "assistant"
MODE = "mode"
PERMISSION_MODE = "permission_mode"
SESSION_START_HOOK = "session_start_hook"
OTHER = "other"


def classify(record):
    """Which kind of transcript line this is.

    A `type: "user"` record is three different things depending on its
    content: a real human prompt (a turn boundary), a system-injected note,
    or a carrier for tool results. Only the first starts a turn.
    """
    kind = record.get("type")

    if kind == "assistant":
        return ASSISTANT

    if kind == "user":
        if record.get("isMeta"):
            return META
        content = (record.get("message") or {}).get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return TOOL_RESULT
        if prompt_text(record).lstrip().startswith("<local-command-stdout>"):
            # Command *output* echoed back into the conversation, not human
            # input. Left as USER_PROMPT it manufactures a fake turn boundary.
            return META
        return USER_PROMPT

    if kind == "mode":
        return MODE

    if kind == "permission-mode":
        return PERMISSION_MODE

    if kind == "attachment":
        if (record.get("attachment") or {}).get("hookEvent") == "SessionStart":
            return SESSION_START_HOOK

    return OTHER


def read_new_records(path, start_line):
    """Parse lines after `start_line`.

    Returns (records, total_lines). Unparseable lines are skipped but still
    counted, so the offset stays aligned with the file even when a line is
    truncated mid-write.
    """
    records = []
    total = 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            total = index + 1
            if index < start_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records, total


def usage_of(record):
    """Token counts from an assistant record, normalised and zero-filled.

    The 5-minute and 1-hour cache writes are kept apart because they are
    priced differently; a single combined number cannot be un-mixed later.
    """
    usage = (record.get("message") or {}).get("usage") or {}
    created = usage.get("cache_creation") or {}
    details = usage.get("output_tokens_details") or {}
    return {
        "in": usage.get("input_tokens") or 0,
        "out": usage.get("output_tokens") or 0,
        "thinking": details.get("thinking_tokens") or 0,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
        "cache_create_5m": created.get("ephemeral_5m_input_tokens") or 0,
        "cache_create_1h": created.get("ephemeral_1h_input_tokens") or 0,
    }


def tool_uses(record):
    """[(tool_name, tool_input)] for every tool_use block, in order."""
    found = []
    for block in (record.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            found.append((block.get("name"), block.get("input") or {}))
    return found


def tool_error_count(record):
    """How many tool_result blocks in this record are flagged is_error."""
    count = 0
    for block in (record.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
            count += 1
    return count


def prompt_text(record):
    """The plain text of a user record. Empty string when there is none.

    Only used to decide whether a slash command invoked a skill. The text is
    never written to the telemetry output.
    """
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def ts_ms(value):
    """ISO-8601 timestamp to epoch milliseconds. None when unparseable."""
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, AttributeError):
        return None
