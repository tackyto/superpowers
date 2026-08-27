#!/usr/bin/env python3
"""Windows verification for the telemetry hook.

The suites in this repository run on Linux and macOS, where `fcntl` exists and
this hook has always worked. They cannot cover what actually broke on Windows:
that `store` imports at all without `fcntl`, that `msvcrt` really serialises
concurrent writers, and that a piped hook payload survives cmd.exe and Git Bash
on its way to Python.

`test_store.py` covers the Windows lock *logic* from Linux with a fake msvcrt.
This script covers the parts a fake cannot: the real module, the real
filesystem, and the real dispatch chain.

Its output stays ASCII on purpose: a Japanese Windows console is cp932, and
Python raises UnicodeEncodeError on the first character it cannot encode.

Run it from Git Bash on Windows:

    python3 tests/hooks/telemetry/verify-windows.py

Exits 0 when every check passes, 1 otherwise.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
HOOK_CUSTOM = os.path.join(REPO_ROOT, "hooks", "custom")
RUN_HOOK = os.path.join(REPO_ROOT, "hooks", "run-hook.cmd")

sys.path.insert(0, HOOK_CUSTOM)

# How hard to lean on the lock. Eight writers is well past what a real session
# produces; the point is to make a broken lock fail here rather than in the wild.
WRITERS = 8
BATCHES_PER_WRITER = 40
TYPICAL_BATCH_BYTES = 4096
STRESS_BATCH_BYTES = 65536

FAILURES = []


def check(description, condition, detail=""):
    if condition:
        print("  [PASS] %s" % description)
        return True
    print("  [FAIL] %s" % description)
    if detail:
        for line in str(detail).splitlines():
            print("         %s" % line)
    FAILURES.append(description)
    return False


def record(writer, index, line, filler):
    """One telemetry-shaped row, padded to make torn writes visible.

    Every row a writer produces is padded with that writer's own character, so
    a line mixing two characters is proof of a torn write rather than a guess.
    """
    return {
        "schema_version": 1,
        "kind": "seg",
        "ts": "2026-08-21T04:00:00Z",
        "writer": writer,
        "index": index,
        "line": line,
        "pad": filler,
    }


def batch_for(writer, index, target_bytes):
    """A batch of rows whose JSON is about `target_bytes` long in total."""
    filler = writer[-1]
    rows, total, line = [], 0, 0
    while total < target_bytes:
        row = record(writer, index, line, filler * 200)
        rows.append(row)
        total += len(json.dumps(row, ensure_ascii=False)) + 1
        line += 1
    return rows


def rows_per_batch(target_bytes):
    return len(batch_for("w0", 0, target_bytes))


# --------------------------------------------------------------------------
# child mode: one concurrent writer, driving the real production code path
# --------------------------------------------------------------------------

def run_as_writer(base, writer, target_bytes):
    from telemetry_lib import store

    for index in range(BATCHES_PER_WRITER):
        try:
            store.append_records(batch_for(writer, index, target_bytes), base)
        except OSError:
            # Losing a batch to sustained contention is the documented
            # behaviour on every platform: the hook logs and moves on rather
            # than delaying the session. The parent counts what arrived.
            pass


def spawn_writers(base, target_bytes):
    children = [
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--writer",
                          base, "w%d" % i, str(target_bytes)])
        for i in range(WRITERS)
    ]
    for child in children:
        child.wait()


def inspect(base):
    """Read back the month file: how many rows arrived, how many are torn."""
    path = os.path.join(base, "2026-08.jsonl")
    if not os.path.exists(path):
        return 0, 0
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", "replace")
    intact, torn = 0, 0
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            torn += 1
            continue
        # A row written whole carries exactly one filler character throughout.
        if "pad" not in row or len(set(row["pad"])) != 1:
            torn += 1
        else:
            intact += 1
    return intact, torn


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_platform():
    print("Platform")
    check("running on native Windows", sys.platform == "win32",
          "sys.platform is %r - run this from Git Bash on Windows, not WSL" % sys.platform)
    try:
        import fcntl  # noqa: F401
        check("fcntl is absent, as it is on every Windows Python", False,
              "fcntl imported - this is not the environment the script exists to cover")
    except ImportError:
        check("fcntl is absent, as it is on every Windows Python", True)
    try:
        import msvcrt  # noqa: F401
        check("msvcrt is available from the standard library", True)
    except ImportError as error:
        check("msvcrt is available from the standard library", False, error)


def check_import():
    print("Import")
    try:
        from telemetry_lib import store
    except Exception as error:  # noqa: BLE001 - reporting is the whole point
        check("telemetry_lib.store imports without fcntl", False, repr(error))
        return None
    check("telemetry_lib.store imports without fcntl", True)
    check("store selected the msvcrt lock path", store.fcntl is None,
          "store.fcntl is %r, expected None" % (store.fcntl,))
    return store


def check_concurrency(label, target_bytes, require_no_loss):
    print("Concurrency - %s batches (%d writers x %d batches)"
          % (label, WRITERS, BATCHES_PER_WRITER))
    with tempfile.TemporaryDirectory() as tmpdir:
        base = os.path.join(tmpdir, "telemetry")
        spawn_writers(base, target_bytes)
        intact, torn = inspect(base)
        expected = WRITERS * BATCHES_PER_WRITER * rows_per_batch(target_bytes)

        check("no torn rows", torn == 0,
              "%d of %d rows were torn - the lock is not serialising writers"
              % (torn, intact + torn))
        if require_no_loss:
            check("every row arrived", intact == expected,
                  "%d rows arrived, expected %d" % (intact, expected))
        else:
            lost = expected - intact
            print("         %d of %d rows arrived (%d dropped to lock contention)"
                  % (intact, expected, lost))


def check_dispatch():
    """The hook payload has to reach Python through cmd.exe and Git Bash."""
    print("Dispatch")
    with tempfile.TemporaryDirectory() as tmpdir:
        transcript = os.path.join(tmpdir, "transcript.jsonl")
        out = os.path.join(tmpdir, "out")
        write_transcript(transcript)
        # ensure_ascii=False on purpose: the payload has to reach Python as real
        # UTF-8 bytes. "\u65e5\u672c\u8a9e" is Japanese text sitting immediately
        # before an escaped quote -- the pattern that cp932 breaks, because 52 of
        # its 60 lead bytes swallow the backslash that follows them. Escaped here
        # so this file stays ASCII for a cp932 console to print.
        payload = json.dumps({
            "session_id": "verify-windows",
            "hook_event_name": "Stop",
            "transcript_path": transcript,
            "cwd": REPO_ROOT,
            "note": "\u65e5\u672c\u8a9e\"x\"",
        }, ensure_ascii=False)

        environment = dict(os.environ)
        environment["SUPERPOWERS_TELEMETRY_DIR"] = out
        environment["CLAUDE_PLUGIN_ROOT"] = REPO_ROOT
        completed = subprocess.run(
            ["cmd", "/c", RUN_HOOK, "custom/telemetry"],
            input=payload.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment,
        )

        check("hook exits 0", completed.returncode == 0,
              "exit=%d stderr=%s" % (completed.returncode,
                                     completed.stderr.decode("utf-8", "replace")))
        check("hook writes nothing to stdout", completed.stdout == b"",
              completed.stdout.decode("utf-8", "replace"))

        month = os.path.join(out, "2026-08.jsonl")
        wrote = os.path.exists(month)
        errors = os.path.join(out, "errors.log")
        detail = ""
        if not wrote and os.path.exists(errors):
            with open(errors, encoding="utf-8") as handle:
                detail = handle.read()
        elif not wrote:
            detail = "no records and no errors.log - the payload never reached Python"
        if check("piped payload produced records", wrote, detail):
            with open(month, encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            check("records carry this session", bool(rows) and
                  all(r.get("session") == "verify-windows" for r in rows),
                  "sessions seen: %s" % sorted({r.get("session") for r in rows}))
        check("errors.log is empty or absent", not os.path.exists(errors),
              detail or "see %s" % errors)


def write_transcript(path):
    """The smallest transcript that yields a segment: one turn, one skill."""
    def assistant(ts, uuid, out_tokens, tools=(), stop="tool_use"):
        return {
            "type": "assistant", "uuid": uuid, "timestamp": ts,
            "gitBranch": "fix/telemetry-windows-support", "version": "2.1.4",
            "effort": "high",
            "message": {
                "model": "claude-opus-5", "stop_reason": stop,
                "content": [{"type": "tool_use", "name": name, "input": value, "id": "t"}
                            for name, value in tools],
                "usage": {"input_tokens": 2, "output_tokens": out_tokens,
                          "output_tokens_details": {"thinking_tokens": 0},
                          "cache_read_input_tokens": 0,
                          "cache_creation": {"ephemeral_1h_input_tokens": 0,
                                             "ephemeral_5m_input_tokens": 0}},
            },
        }

    records = [
        {"type": "mode", "mode": "normal"},
        {"type": "user", "timestamp": "2026-08-21T04:00:00Z", "message": {"content": "go"}},
        assistant("2026-08-21T04:00:01Z", "u1", 10,
                  tools=[("Skill", {"skill": "superpowers:test-driven-development"})]),
        assistant("2026-08-21T04:00:31Z", "u2", 2400, stop="end_turn"),
    ]
    with open(path, "w", encoding="utf-8") as handle:
        for entry in records:
            handle.write(json.dumps(entry) + "\n")


def main():
    print("verify-windows.py - telemetry hook on native Windows")
    print()
    check_platform()
    print()
    if check_import() is not None:
        print()
        check_concurrency("typical", TYPICAL_BATCH_BYTES, require_no_loss=True)
        print()
        check_concurrency("stress", STRESS_BATCH_BYTES, require_no_loss=False)
    print()
    check_dispatch()
    print()
    if FAILURES:
        print("%d check(s) failed." % len(FAILURES))
        return 1
    print("All Windows telemetry checks passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--writer":
        run_as_writer(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        sys.exit(0)
    sys.exit(main())
