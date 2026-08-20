"""Where telemetry lands: the monthly JSONL, the state files, the error log.

The only module that writes to the filesystem. It deliberately knows nothing
about the shape of a segment or of the state — callers supply both — so the
segmentation logic stays testable without touching a disk.
"""

import fcntl
import json
import os
import time
from datetime import datetime, timezone

STATE_MAX_AGE_DAYS = 30
LOCK_ATTEMPTS = 12
LOCK_WAIT_SECONDS = 0.05


def base_dir():
    """Directory holding the telemetry. SUPERPOWERS_TELEMETRY_DIR overrides it."""
    override = os.environ.get("SUPERPOWERS_TELEMETRY_DIR")
    if override:
        return override
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(config, "superpowers", "telemetry")


def _safe(name):
    """A filename component that cannot escape its directory."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in (name or "unknown"))


def _state_dir(base):
    return os.path.join(base, ".state")


def _month_of(record):
    stamp = record.get("ts") or ""
    if len(stamp) >= 7 and stamp[4] == "-":
        return stamp[:7]
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _lock_wait(pid):
    """How long to wait before one retry, spread out per process.

    Without the per-process spread, writers that started together keep
    waking in lockstep and colliding with each other again — which is how
    whole batches were being lost.
    """
    return LOCK_WAIT_SECONDS * (1 + (pid % 7) / 7.0)


def _append_locked(path, payload):
    """Append `payload` under an exclusive lock, or raise after retrying.

    Several sessions and subagents append to the same monthly file. Losing a
    batch matters far less than blocking the session, so this gives up quickly
    and lets the caller log the failure. Jitter keeps concurrent processes
    from waking in lockstep and colliding again immediately.
    """
    last_error = None
    for attempt in range(LOCK_ATTEMPTS):
        handle = open(path, "a", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            last_error = error
            if attempt < LOCK_ATTEMPTS - 1:
                time.sleep(_lock_wait(os.getpid()))
            continue
        try:
            handle.write(payload)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        return
    raise last_error


def append_records(records, base):
    """Append records to their month's file. One lock per file."""
    if not records:
        return
    os.makedirs(base, exist_ok=True)
    grouped = {}
    for record in records:
        grouped.setdefault(_month_of(record), []).append(record)
    for month, rows in sorted(grouped.items()):
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        _append_locked(os.path.join(base, month + ".jsonl"), payload)


def load_state(session, base, default):
    """Stored state for a session, or `default` when absent or unusable."""
    path = os.path.join(_state_dir(base), _safe(session) + ".json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return default
    if not isinstance(loaded, dict) or "line" not in loaded or "main" not in loaded or "sub" not in loaded:
        return default
    return loaded


def save_state(session, state, base):
    """Write state atomically, so a killed hook cannot leave a torn file."""
    directory = _state_dir(base)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _safe(session) + ".json")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(temporary, path)


def prune_states(base, max_age_days=STATE_MAX_AGE_DAYS):
    """Delete state files untouched for `max_age_days`. Returns the count."""
    directory = _state_dir(base)
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


def log_error(base, session, message):
    """Record a failure without ever raising one of its own."""
    try:
        os.makedirs(base, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        entry = json.dumps(
            {"ts": stamp, "session": session, "error": str(message)[:500]}, ensure_ascii=False)
        with open(os.path.join(base, "errors.log"), "a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
    except Exception:
        pass
