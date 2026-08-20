import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

import fixtures
from telemetry_lib import transcript as tx


class TestClassify(unittest.TestCase):
    def test_assistant_record(self):
        self.assertEqual(tx.classify(fixtures.assistant("2026-08-21T04:00:00Z")), tx.ASSISTANT)

    def test_human_prompt_is_a_turn_boundary(self):
        self.assertEqual(tx.classify(fixtures.prompt("2026-08-21T04:00:00Z")), tx.USER_PROMPT)

    def test_injected_meta_is_not_a_turn_boundary(self):
        self.assertEqual(tx.classify(fixtures.meta("2026-08-21T04:00:00Z")), tx.META)

    def test_tool_result_is_not_a_turn_boundary(self):
        self.assertEqual(tx.classify(fixtures.tool_result("2026-08-21T04:00:00Z")), tx.TOOL_RESULT)

    def test_mode_records(self):
        self.assertEqual(tx.classify(fixtures.mode()), tx.MODE)
        self.assertEqual(tx.classify(fixtures.permission_mode()), tx.PERMISSION_MODE)

    def test_session_start_attachment(self):
        record = {"type": "attachment", "attachment": {"hookEvent": "SessionStart", "stdout": "x"}}
        self.assertEqual(tx.classify(record), tx.SESSION_START_HOOK)

    def test_unknown_type(self):
        self.assertEqual(tx.classify({"type": "ai-title"}), tx.OTHER)


class TestUsage(unittest.TestCase):
    def test_splits_cache_creation_by_ttl(self):
        record = fixtures.assistant(
            "2026-08-21T04:00:00Z", output=555, thinking=221,
            cache_read=22625, cache_create_1h=10860, cache_create_5m=40,
        )
        self.assertEqual(
            tx.usage_of(record),
            {"in": 2, "out": 555, "thinking": 221, "cache_read": 22625,
             "cache_create_5m": 40, "cache_create_1h": 10860},
        )

    def test_missing_usage_is_all_zero(self):
        self.assertEqual(
            tx.usage_of({"type": "assistant", "message": {}}),
            {"in": 0, "out": 0, "thinking": 0, "cache_read": 0,
             "cache_create_5m": 0, "cache_create_1h": 0},
        )


class TestExtraction(unittest.TestCase):
    def test_tool_uses_returns_name_and_input(self):
        record = fixtures.assistant(
            "2026-08-21T04:00:00Z",
            tools=[("Skill", {"skill": "superpowers:brainstorming"}), ("Bash", {"command": "ls"})],
        )
        self.assertEqual(
            tx.tool_uses(record),
            [("Skill", {"skill": "superpowers:brainstorming"}), ("Bash", {"command": "ls"})],
        )

    def test_tool_error_count(self):
        self.assertEqual(tx.tool_error_count(fixtures.tool_result("t", errors=2, ok=3)), 2)

    def test_prompt_text_from_string_content(self):
        self.assertEqual(tx.prompt_text(fixtures.prompt("t", text="hello")), "hello")

    def test_prompt_text_from_text_blocks(self):
        record = {"message": {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}}
        self.assertEqual(tx.prompt_text(record), "ab")


class TestIncrementalRead(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "t.jsonl")

    def test_reads_everything_from_zero(self):
        fixtures.write_jsonl(self.path, [fixtures.mode(), fixtures.prompt("t1")])
        records, total = tx.read_new_records(self.path, 0)
        self.assertEqual(len(records), 2)
        self.assertEqual(total, 2)

    def test_resumes_from_offset(self):
        fixtures.write_jsonl(self.path, [fixtures.mode(), fixtures.prompt("t1"), fixtures.prompt("t2")])
        records, total = tx.read_new_records(self.path, 2)
        self.assertEqual(len(records), 1)
        self.assertEqual(total, 3)

    def test_garbage_line_is_skipped_but_counted(self):
        fixtures.write_jsonl(self.path, [fixtures.prompt("t1"), fixtures.prompt("t2")], garbage_after=0)
        records, total = tx.read_new_records(self.path, 0)
        self.assertEqual(len(records), 2)
        self.assertEqual(total, 3)

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            tx.read_new_records(os.path.join(self.dir.name, "nope.jsonl"), 0)


class TestTimestamps(unittest.TestCase):
    def test_parses_zulu(self):
        self.assertEqual(tx.ts_ms("2026-08-21T04:00:00.500Z") - tx.ts_ms("2026-08-21T04:00:00Z"), 500)

    def test_none_and_garbage(self):
        self.assertIsNone(tx.ts_ms(None))
        self.assertIsNone(tx.ts_ms("not a time"))


if __name__ == "__main__":
    unittest.main()
