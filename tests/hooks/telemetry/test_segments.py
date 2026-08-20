import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

import fixtures
from telemetry_lib import segments as sg

CTX = {
    "session": "s-1",
    "default_agent": "main",
    "project": "superpowers",
    "plugin_root": None,
    "plugin_version": "1.0.0",
    "subagent_type": None,
    "parent_turn": None,
}


def run(records, state=None, ctx=None):
    return sg.build_segments(records, state or sg.new_state(), dict(ctx or CTX))


class TestSingleSkillTurn(unittest.TestCase):
    def test_one_turn_one_skill_makes_one_row(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:02Z",
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:10Z", output=500, stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        skills = [(s["skill"], s["seq"]) for s in segments]
        self.assertEqual(skills, [(None, 0), ("superpowers:brainstorming", 1)])
        self.assertEqual(segments[1]["turn"], 1)
        self.assertEqual(segments[1]["tokens"]["out"], 500)

    def test_record_carrying_the_skill_call_bills_the_previous_skill(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:02Z", output=77,
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:10Z", output=500, stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["tokens"]["out"], 77)
        self.assertEqual(segments[1]["tokens"]["out"], 500)


class TestSkillSwitchWithinOneTurn(unittest.TestCase):
    """The core requirement: coding and review must not blend together."""

    def setUp(self):
        self.records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=10,
                               tools=[("Skill", {"skill": "superpowers:test-driven-development"})]),
            fixtures.assistant("2026-08-21T04:00:31Z", output=8100,
                               cache_create_1h=10860, tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:33Z"),
            fixtures.assistant("2026-08-21T04:00:41Z", output=100,
                               tools=[("Skill", {"skill": "superpowers:requesting-code-review"})]),
            fixtures.assistant("2026-08-21T04:01:11Z", output=2400,
                               stop_reason="end_turn"),
        ]

    def test_produces_one_row_per_skill(self):
        segments, _ = run(self.records)
        self.assertEqual(
            [s["skill"] for s in segments],
            [None, "superpowers:test-driven-development", "superpowers:requesting-code-review"],
        )

    def test_all_rows_share_the_turn(self):
        segments, _ = run(self.records)
        self.assertEqual([s["turn"] for s in segments], [1, 1, 1])
        self.assertEqual([s["seq"] for s in segments], [0, 1, 2])

    def test_tokens_are_separated(self):
        segments, _ = run(self.records)
        by_skill = {s["skill"]: s for s in segments}
        self.assertEqual(by_skill["superpowers:test-driven-development"]["tokens"]["out"], 8200)
        self.assertEqual(by_skill["superpowers:requesting-code-review"]["tokens"]["out"], 2400)

    def test_time_is_separated(self):
        segments, _ = run(self.records)
        by_skill = {s["skill"]: s for s in segments}
        # TDD: 04:00:01 -> 04:00:41 = 40s
        self.assertEqual(by_skill["superpowers:test-driven-development"]["exec_ms"], 40000)
        # review: 04:00:41 -> 04:01:11 = 30s
        self.assertEqual(by_skill["superpowers:requesting-code-review"]["exec_ms"], 30000)

    def test_cache_creation_ttl_split_survives(self):
        segments, _ = run(self.records)
        by_skill = {s["skill"]: s for s in segments}
        self.assertEqual(
            by_skill["superpowers:test-driven-development"]["tokens"]["cache_create_1h"], 10860)
        self.assertEqual(
            by_skill["superpowers:test-driven-development"]["tokens"]["cache_create_5m"], 0)


class TestWaitTime(unittest.TestCase):
    def test_between_turns_lands_on_seq_zero(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:10Z", stop_reason="end_turn"),
            fixtures.prompt("2026-08-21T04:02:10Z"),
            fixtures.assistant("2026-08-21T04:02:15Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["wait_ms"], 0)
        self.assertEqual(segments[1]["turn"], 2)
        self.assertEqual(segments[1]["seq"], 0)
        self.assertEqual(segments[1]["wait_ms"], 120000)

    def test_ask_user_question_inside_a_turn_counts_as_wait(self):
        """The 718.8s problem: a question's answer time is not the skill's cost."""
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z",
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:05Z", tools=[("AskUserQuestion", {})]),
            fixtures.tool_result("2026-08-21T04:05:05Z"),
            fixtures.assistant("2026-08-21T04:05:10Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        brainstorm = [s for s in segments if s["skill"] == "superpowers:brainstorming"][0]
        self.assertEqual(brainstorm["wait_ms"], 300000)
        self.assertEqual(brainstorm["exec_ms"], 9000)

    def test_ordinary_tool_gap_counts_as_exec(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:31Z"),
            fixtures.assistant("2026-08-21T04:00:32Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["wait_ms"], 0)
        self.assertEqual(segments[0]["exec_ms"], 32000)


class TestBoundaryHandling(unittest.TestCase):
    def test_meta_records_do_not_start_a_turn(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.meta("2026-08-21T04:00:01Z"),
            fixtures.assistant("2026-08-21T04:00:02Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["turn"], 1)

    def test_tool_results_do_not_start_a_turn(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:02Z"),
            fixtures.assistant("2026-08-21T04:00:03Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(len(segments), 1)

    def test_empty_segment_is_not_emitted(self):
        """A skill called as the turn's last act carries over instead."""
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:05Z", output=50, stop_reason="end_turn",
                               tools=[("Skill", {"skill": "superpowers:writing-plans"})]),
        ]
        segments, state = run(records)
        self.assertEqual([s["skill"] for s in segments], [None])
        self.assertEqual(state["main"]["active_skill"], "superpowers:writing-plans")

    def test_open_segment_is_held_when_the_model_has_not_stopped(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=40, tools=[("Bash", {})]),
        ]
        segments, state = run(records)
        self.assertEqual(segments, [])
        self.assertIsNotNone(state["main"]["open"])

    def test_held_segment_completes_on_the_next_batch(self):
        first = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=40, tools=[("Bash", {})]),
        ]
        _, state = run(first)
        second = [
            fixtures.tool_result("2026-08-21T04:00:02Z"),
            fixtures.assistant("2026-08-21T04:00:03Z", output=60, stop_reason="end_turn"),
        ]
        segments, _ = run(second, state=state)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["tokens"]["out"], 100)
        self.assertEqual(segments[0]["turn"], 1)


class TestSkillCarryOver(unittest.TestCase):
    def test_active_skill_survives_into_the_next_turn(self):
        first = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z",
                               tools=[("Skill", {"skill": "superpowers:brainstorming"})]),
            fixtures.assistant("2026-08-21T04:00:05Z", output=10, stop_reason="end_turn"),
        ]
        _, state = run(first)
        second = [
            fixtures.prompt("2026-08-21T04:01:00Z"),
            fixtures.assistant("2026-08-21T04:01:05Z", output=20, stop_reason="end_turn"),
        ]
        segments, _ = run(second, state=state)
        self.assertEqual(segments[0]["skill"], "superpowers:brainstorming")
        self.assertEqual(segments[0]["turn"], 2)
        self.assertEqual(segments[0]["seq"], 0)


class TestSidechainIsolation(unittest.TestCase):
    def test_subagent_records_do_not_pollute_the_main_stream(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", output=10, tools=[("Bash", {})]),
            fixtures.prompt("2026-08-21T04:00:02Z", sidechain=True),
            fixtures.assistant("2026-08-21T04:00:03Z", output=999, stop_reason="end_turn",
                               sidechain=True),
            fixtures.tool_result("2026-08-21T04:00:04Z"),
            fixtures.assistant("2026-08-21T04:00:05Z", output=20, stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        main = [s for s in segments if s["agent"] == "main"]
        sub = [s for s in segments if s["agent"] == "subagent"]
        self.assertEqual(len(main), 1)
        self.assertEqual(main[0]["tokens"]["out"], 30)
        self.assertEqual(len(sub), 1)
        self.assertEqual(sub[0]["tokens"]["out"], 999)


class TestRecordShape(unittest.TestCase):
    def test_every_spec_field_is_present(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.mode("normal"),
            fixtures.permission_mode("auto"),
            fixtures.assistant("2026-08-21T04:00:05Z", uuid="u-9", output=50,
                               tools=[("Bash", {})], stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        expected = {
            "schema_version", "kind", "ts", "ts_end", "session", "turn", "seq", "agent",
            "subagent_type", "parent_turn", "first_uuid", "skill", "skill_rev", "invoked_by",
            "phase", "project", "branch", "cc_version", "plugin_version", "model", "effort",
            "mode", "permission_mode", "exec_ms", "wait_ms", "api_calls", "tokens", "tools",
            "tool_errors", "stop_reason", "compacted",
        }
        self.assertEqual(set(segments[0]), expected)
        self.assertEqual(segments[0]["schema_version"], 1)
        self.assertEqual(segments[0]["kind"], "seg")
        self.assertEqual(segments[0]["first_uuid"], "u-9")
        self.assertEqual(segments[0]["branch"], "main")
        self.assertEqual(segments[0]["cc_version"], "2.1.4")
        self.assertEqual(segments[0]["model"], "claude-opus-5")
        self.assertEqual(segments[0]["mode"], "normal")
        self.assertEqual(segments[0]["permission_mode"], "auto")
        self.assertEqual(segments[0]["tools"], {"Bash": 1})
        self.assertEqual(segments[0]["api_calls"], 1)

    def test_tool_errors_are_counted(self):
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z"),
            fixtures.assistant("2026-08-21T04:00:01Z", tools=[("Bash", {})]),
            fixtures.tool_result("2026-08-21T04:00:02Z", errors=2, ok=1),
            fixtures.assistant("2026-08-21T04:00:03Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        self.assertEqual(segments[0]["tool_errors"], 2)

    def test_no_prompt_text_leaks_into_the_record(self):
        secret = "my password is hunter2"
        records = [
            fixtures.prompt("2026-08-21T04:00:00Z", text=secret),
            fixtures.assistant("2026-08-21T04:00:01Z", stop_reason="end_turn"),
        ]
        segments, _ = run(records)
        import json as _json
        self.assertNotIn("hunter2", _json.dumps(segments))


if __name__ == "__main__":
    unittest.main()
