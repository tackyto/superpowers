"""Tests for the hook entry point's two measured-defect fixes.

Both cover behaviour the brief for this task got wrong (see rulings T1-1 and
T1-2 in the task-6 brief): the state key must be unique per transcript, not
merely per session, and `subagent_type` must come from the sibling
`.meta.json` file rather than a hook-payload field that does not exist.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

import telemetry  # noqa: E402


class TestStateKey(unittest.TestCase):
    def test_differs_for_same_session_different_transcript(self):
        parent = telemetry.state_key("sess-1", "/proj/sess-1.jsonl")
        sub = telemetry.state_key("sess-1", "/proj/sess-1/subagents/agent-abc.jsonl")
        self.assertNotEqual(parent, sub)

    def test_stable_for_the_same_session_and_transcript(self):
        first = telemetry.state_key("sess-1", "/proj/sess-1.jsonl")
        second = telemetry.state_key("sess-1", "/proj/sess-1.jsonl")
        self.assertEqual(first, second)

    def test_two_subagents_of_the_same_parent_get_different_keys(self):
        one = telemetry.state_key("sess-1", "/proj/sess-1/subagents/agent-a.jsonl")
        two = telemetry.state_key("sess-1", "/proj/sess-1/subagents/agent-b.jsonl")
        self.assertNotEqual(one, two)

    def test_key_carries_the_session_id_as_a_readable_prefix(self):
        key = telemetry.state_key("sess-1", "/proj/sess-1.jsonl")
        self.assertTrue(key.startswith("sess-1-"))

    def test_missing_transcript_path_does_not_raise(self):
        # load_state/save_state must still receive a usable string key.
        key = telemetry.state_key("sess-1", None)
        self.assertTrue(key.startswith("sess-1-"))


class TestSubagentTypeFor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _write(self, name, content):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_reads_agent_type_from_sibling_meta_json(self):
        transcript = os.path.join(self.dir.name, "agent-abc123.jsonl")
        open(transcript, "w", encoding="utf-8").close()
        self._write(
            "agent-abc123.meta.json",
            json.dumps({"agentType": "general-purpose", "description": "x",
                        "toolUseId": "toolu_01", "spawnDepth": 1, "model": "sonnet"}),
        )
        self.assertEqual(telemetry.subagent_type_for(transcript), "general-purpose")

    def test_none_when_path_is_none(self):
        self.assertIsNone(telemetry.subagent_type_for(None))

    def test_none_when_path_is_empty_string(self):
        self.assertIsNone(telemetry.subagent_type_for(""))

    def test_none_when_meta_file_is_absent(self):
        transcript = os.path.join(self.dir.name, "agent-missing.jsonl")
        open(transcript, "w", encoding="utf-8").close()
        self.assertIsNone(telemetry.subagent_type_for(transcript))

    def test_none_when_meta_file_is_malformed_json(self):
        transcript = os.path.join(self.dir.name, "agent-bad.jsonl")
        open(transcript, "w", encoding="utf-8").close()
        self._write("agent-bad.meta.json", "{not valid json")
        self.assertIsNone(telemetry.subagent_type_for(transcript))

    def test_none_when_meta_file_is_unreadable(self):
        transcript = os.path.join(self.dir.name, "agent-noperm.jsonl")
        open(transcript, "w", encoding="utf-8").close()
        meta = self._write("agent-noperm.meta.json", json.dumps({"agentType": "general-purpose"}))
        os.chmod(meta, 0)
        self.addCleanup(os.chmod, meta, 0o644)
        if os.geteuid() == 0:
            self.skipTest("running as root: permission bits have no effect")
        self.assertIsNone(telemetry.subagent_type_for(transcript))

    def test_none_when_meta_json_lacks_agent_type(self):
        transcript = os.path.join(self.dir.name, "agent-notype.jsonl")
        open(transcript, "w", encoding="utf-8").close()
        self._write("agent-notype.meta.json", json.dumps({"description": "no agentType key"}))
        self.assertIsNone(telemetry.subagent_type_for(transcript))

    def test_only_the_jsonl_extension_is_swapped_for_meta_json(self):
        # A main-session transcript at .../sess-1.jsonl must look for
        # .../sess-1.meta.json, not something derived from a subagents path.
        transcript = os.path.join(self.dir.name, "sess-1.jsonl")
        open(transcript, "w", encoding="utf-8").close()
        self._write("sess-1.meta.json", json.dumps({"agentType": "main-would-not-have-this"}))
        self.assertEqual(telemetry.subagent_type_for(transcript), "main-would-not-have-this")


if __name__ == "__main__":
    unittest.main()
