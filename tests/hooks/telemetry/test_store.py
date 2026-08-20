import fcntl
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

from telemetry_lib import store


def row(ts="2026-08-21T04:00:00Z", **extra):
    record = {"schema_version": 1, "kind": "seg", "ts": ts, "skill": None}
    record.update(extra)
    return record


class TestBaseDir(unittest.TestCase):
    def test_env_override_wins(self):
        os.environ["SUPERPOWERS_TELEMETRY_DIR"] = "/tmp/telemetry-override"
        self.addCleanup(os.environ.pop, "SUPERPOWERS_TELEMETRY_DIR", None)
        self.assertEqual(store.base_dir(), "/tmp/telemetry-override")

    def test_default_lives_under_claude_config(self):
        os.environ.pop("SUPERPOWERS_TELEMETRY_DIR", None)
        os.environ["CLAUDE_CONFIG_DIR"] = "/tmp/cfg"
        self.addCleanup(os.environ.pop, "CLAUDE_CONFIG_DIR", None)
        self.assertEqual(store.base_dir(), "/tmp/cfg/superpowers/telemetry")


class TestAppend(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_writes_one_line_per_record(self):
        store.append_records([row(), row()], self.base)
        with open(os.path.join(self.base, "2026-08.jsonl"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["kind"], "seg")

    def test_appends_rather_than_truncates(self):
        store.append_records([row()], self.base)
        store.append_records([row()], self.base)
        with open(os.path.join(self.base, "2026-08.jsonl"), encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 2)

    def test_rotates_by_month(self):
        store.append_records([row("2026-08-31T23:59:59Z"), row("2026-09-01T00:00:01Z")], self.base)
        self.assertTrue(os.path.exists(os.path.join(self.base, "2026-08.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(self.base, "2026-09.jsonl")))

    def test_empty_batch_creates_nothing(self):
        store.append_records([], self.base)
        self.assertFalse(os.path.exists(self.base))

    def test_non_ascii_is_written_unescaped(self):
        store.append_records([row(project="日本語")], self.base)
        with open(os.path.join(self.base, "2026-08.jsonl"), encoding="utf-8") as handle:
            self.assertIn("日本語", handle.read())

    def test_gives_up_when_the_file_stays_locked(self):
        os.makedirs(self.base, exist_ok=True)
        path = os.path.join(self.base, "2026-08.jsonl")
        blocker = open(path, "a", encoding="utf-8")
        fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)
        try:
            with self.assertRaises(OSError):
                store.append_records([row()], self.base)
        finally:
            fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
            blocker.close()


class TestState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_round_trip(self):
        store.save_state("s-1", {"line": 42, "main": {}}, self.base)
        self.assertEqual(store.load_state("s-1", self.base, {"line": 0}), {"line": 42, "main": {}})

    def test_missing_state_returns_the_default(self):
        self.assertEqual(store.load_state("nope", self.base, {"line": 0}), {"line": 0})

    def test_corrupt_state_returns_the_default(self):
        os.makedirs(os.path.join(self.base, ".state"), exist_ok=True)
        with open(os.path.join(self.base, ".state", "s-2.json"), "w", encoding="utf-8") as handle:
            handle.write("{ broken")
        self.assertEqual(store.load_state("s-2", self.base, {"line": 0}), {"line": 0})

    def test_state_without_line_key_returns_the_default(self):
        store.save_state("s-3", {"unexpected": True}, self.base)
        self.assertEqual(store.load_state("s-3", self.base, {"line": 0}), {"line": 0})

    def test_session_id_cannot_escape_the_state_directory(self):
        store.save_state("../../escape", {"line": 1}, self.base)
        entries = os.listdir(os.path.join(self.base, ".state"))
        self.assertEqual(len(entries), 1)
        self.assertNotIn("..", entries[0])


class TestPrune(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_removes_only_stale_state(self):
        store.save_state("fresh", {"line": 1}, self.base)
        store.save_state("stale", {"line": 1}, self.base)
        stale = os.path.join(self.base, ".state", "stale.json")
        old = time.time() - 31 * 86400
        os.utime(stale, (old, old))
        self.assertEqual(store.prune_states(self.base), 1)
        remaining = os.listdir(os.path.join(self.base, ".state"))
        self.assertEqual(remaining, ["fresh.json"])

    def test_missing_directory_is_not_an_error(self):
        self.assertEqual(store.prune_states(self.base), 0)


class TestErrorLog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = os.path.join(self.dir.name, "telemetry")

    def test_writes_one_json_line(self):
        store.log_error(self.base, "s-1", "ValueError: boom")
        with open(os.path.join(self.base, "errors.log"), encoding="utf-8") as handle:
            entry = json.loads(handle.read().splitlines()[0])
        self.assertEqual(entry["session"], "s-1")
        self.assertIn("boom", entry["error"])

    def test_never_raises(self):
        store.log_error("/proc/cannot/write/here", "s-1", "boom")


if __name__ == "__main__":
    unittest.main()
