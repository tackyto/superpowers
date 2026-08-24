import fcntl
import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

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
        store.save_state("s-1", {"line": 42, "main": {}, "sub": {}}, self.base)
        self.assertEqual(
            store.load_state("s-1", self.base, {"line": 0}), {"line": 42, "main": {}, "sub": {}})

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

    def test_state_without_main_or_sub_key_returns_the_default(self):
        """A state file with only "line" used to be accepted, and then
        segments.py's `state["main"]` raised KeyError — wedging that
        transcript's offset in place until the 30-day prune."""
        store.save_state("s-4", {"line": 5}, self.base)
        self.assertEqual(store.load_state("s-4", self.base, {"line": 0}), {"line": 0})

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


class TestLockRetryPolicy(unittest.TestCase):
    def test_minimum_retry_attempts_prevents_batch_loss(self):
        """Lock acquire attempts >= 8 to prevent losing batches under concurrency.

        Three attempts was measured losing entire batches (25 rows) in an 8-process
        concurrent append workload. This test ensures reverting to that count fails
        loudly rather than silently re-enabling data loss.
        """
        self.assertGreaterEqual(store.LOCK_ATTEMPTS, 8)

    def test_worst_case_wait_time_inside_hook_budget(self):
        """Worst-case contention tolerance stays within hook timeout budget.

        Worst case: LOCK_ATTEMPTS - 1 sleeps (no sleep after the last attempt),
        each multiplied by the largest jitter factor (pid % 7 == 6).
        Must be > 0.8s to handle real concurrent contention,
        but < 2.0s to stay well inside the 10s hook timeout.
        """
        worst_case_sleeps = store.LOCK_ATTEMPTS - 1
        worst_case_wait = worst_case_sleeps * store._lock_wait(6)
        self.assertGreater(worst_case_wait, 0.8)
        self.assertLess(worst_case_wait, 2.0)

    def test_jitter_decorrelates_concurrent_writers(self):
        """Different process IDs produce different wait times (decorrelation).

        The jitter spreads writers that started together so they no longer wake
        in lockstep and collide with each other again immediately. This test
        verifies the jitter function produces distinct values across the range.
        """
        waits = [store._lock_wait(pid % 7) for pid in range(7)]
        self.assertEqual(len(set(waits)), 7, "Jitter must produce 7 distinct values")

    def test_retry_loop_uses_jittered_sleep(self):
        """The retry loop actually calls time.sleep with _lock_wait values.

        The prior three tests pin the constants and the jitter function itself,
        but do not verify that the live retry path wires them together. This test
        catches the regression where sleep() is called with a constant instead of
        _lock_wait(): all three guards would still pass, yet the lockstep collision
        would return and data would be lost again.

        Uses mock to observe what the loop really sleeps, without paying the
        wall-clock cost of retrying.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base = os.path.join(tmpdir, "telemetry")
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, "2026-08.jsonl")

            # Hold the file locked from a second handle to force the retry path.
            blocker = open(path, "a", encoding="utf-8")
            fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)
            try:
                # Patch sleep and getpid so we can observe the calls without delay.
                # Use a fixed pid so we can compute the expected duration.
                fixed_pid = 3
                with mock.patch.object(store.time, "sleep") as mock_sleep, \
                     mock.patch.object(store.os, "getpid", return_value=fixed_pid):
                    with self.assertRaises(OSError):
                        store.append_records([row()], base)

                    # Verify sleep was called exactly LOCK_ATTEMPTS - 1 times.
                    self.assertEqual(
                        mock_sleep.call_count,
                        store.LOCK_ATTEMPTS - 1,
                        f"Expected {store.LOCK_ATTEMPTS - 1} sleeps, got {mock_sleep.call_count}"
                    )

                    # Verify each call received the correct jittered wait time.
                    expected_wait = store._lock_wait(fixed_pid)
                    for call in mock_sleep.call_args_list:
                        actual_wait = call[0][0]
                        self.assertAlmostEqual(
                            actual_wait,
                            expected_wait,
                            places=10,
                            msg=f"Expected sleep({expected_wait}), got sleep({actual_wait})"
                        )
            finally:
                fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
                blocker.close()


class FakeMsvcrt:
    """Stand-in for the Windows-only msvcrt module.

    Records what the lock path asks for, so the Windows branch can be tested
    from Linux, where the real module cannot be imported.
    """

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self):
        self.calls = []
        self.positions = []

    def locking(self, fileno, mode, nbytes):
        self.calls.append((mode, nbytes))
        self.positions.append(os.lseek(fileno, 0, os.SEEK_CUR))


class TestLockPortability(unittest.TestCase):
    """The lock must survive on a platform without fcntl.

    On Windows `import fcntl` raises at module load, before telemetry.py's
    catch-all exists — so the hook recorded nothing and left no trace of why.
    """

    def reload_without_fcntl(self, fake):
        """Reload store as it would import on Windows, and restore afterwards."""
        self.addCleanup(importlib.reload, store)
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": fake}):
            importlib.reload(store)

    def test_import_succeeds_when_fcntl_is_unavailable(self):
        self.reload_without_fcntl(FakeMsvcrt())
        self.assertIsNone(store.fcntl)

    def handle_on_a_temporary_file(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        handle = open(os.path.join(directory.name, "2026-08.jsonl"), "a", encoding="utf-8")
        self.addCleanup(handle.close)
        return handle

    def test_lock_without_fcntl_takes_a_non_blocking_lock_on_one_byte(self):
        """Non-blocking, because the retry-with-jitter policy owns the waiting.

        A blocking lock would hold the Stop hook for as long as another writer
        wanted, and this hook must never delay the session it observes.
        """
        fake = FakeMsvcrt()
        self.reload_without_fcntl(fake)
        store._lock(self.handle_on_a_temporary_file())
        self.assertEqual(fake.calls, [(fake.LK_NBLCK, 1)])

    def test_lock_without_fcntl_locks_byte_zero_whatever_the_handle_position(self):
        """msvcrt locks a range starting at the current position.

        An append handle that has already written sits at EOF, so without a
        rewind every writer would lock a different byte, every lock would
        succeed, and there would be no mutual exclusion at all.
        """
        fake = FakeMsvcrt()
        self.reload_without_fcntl(fake)
        handle = self.handle_on_a_temporary_file()
        handle.write("x" * 100)
        handle.flush()
        store._lock(handle)
        self.assertEqual(fake.positions, [0])

    def test_unlock_without_fcntl_releases_the_byte_that_was_locked(self):
        """Releasing a different range than was locked leaves the lock held.

        The handle is at EOF by the time the write finishes, so _unlock has to
        rewind for the same reason _lock does.
        """
        fake = FakeMsvcrt()
        self.reload_without_fcntl(fake)
        handle = self.handle_on_a_temporary_file()
        handle.write("x" * 100)
        handle.flush()
        store._unlock(handle)
        self.assertEqual(fake.calls, [(fake.LK_UNLCK, 1)])
        self.assertEqual(fake.positions, [0])

    def test_append_locks_and_unlocks_through_the_helpers(self):
        """The write path must route through _lock/_unlock, not call fcntl itself.

        Inlining fcntl.flock again would leave every other test in this file
        green — on Linux — while silently removing the Windows path, which is
        exactly the regression the helpers exist to prevent.
        """
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = os.path.join(directory.name, "telemetry")
        order = []
        with mock.patch.object(store, "_lock", side_effect=lambda h: order.append("lock")), \
             mock.patch.object(store, "_unlock", side_effect=lambda h: order.append("unlock")):
            store.append_records([row()], base)
        self.assertEqual(order, ["lock", "unlock"])

    def test_appending_after_the_rewind_still_lands_at_end_of_file(self):
        """The sentinel-byte design depends on append mode ignoring the position.

        _lock rewinds to byte 0 so that every writer contends for the same byte.
        If a write then landed at the position instead of at EOF, each batch
        would overwrite the start of the month's file.
        """
        fake = FakeMsvcrt()
        self.reload_without_fcntl(fake)
        handle = self.handle_on_a_temporary_file()
        handle.write("first\n")
        handle.flush()
        store._lock(handle)
        handle.write("second\n")
        handle.flush()
        with open(handle.name, encoding="utf-8") as reader:
            self.assertEqual(reader.read(), "first\nsecond\n")


if __name__ == "__main__":
    unittest.main()
