import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../hooks/custom")))

from telemetry_lib import skills as sk


class TestPhaseMapping(unittest.TestCase):
    def test_known_skills(self):
        cases = {
            "superpowers:brainstorming": "brainstorming",
            "superpowers:writing-plans": "planning",
            "superpowers:test-driven-development": "implementing",
            "superpowers:executing-plans": "implementing",
            "superpowers:subagent-driven-development": "implementing",
            "superpowers:systematic-debugging": "debugging",
            "superpowers:requesting-code-review": "reviewing",
            "superpowers:receiving-code-review": "reviewing",
            "superpowers:verification-before-completion": "reviewing",
            "superpowers:finishing-a-development-branch": "finishing",
            "superpowers:dispatching-parallel-agents": "implementing",
        }
        for skill, expected in cases.items():
            self.assertEqual(sk.phase_for(skill), expected, skill)

    def test_unknown_skill_and_none(self):
        self.assertEqual(sk.phase_for("superpowers:writing-skills"), "unknown")
        self.assertEqual(sk.phase_for("other-plugin:whatever"), "unknown")
        self.assertEqual(sk.phase_for(None), "unknown")

    def test_bare_name_without_plugin_prefix(self):
        self.assertEqual(sk.phase_for("brainstorming"), "brainstorming")


class TestSkillRev(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name
        skill_dir = os.path.join(self.root, "skills", "brainstorming")
        os.makedirs(skill_dir)
        self.body = b"---\nname: brainstorming\n---\nbody\n"
        with open(os.path.join(skill_dir, "SKILL.md"), "wb") as handle:
            handle.write(self.body)

    def test_hashes_skill_md(self):
        self.assertEqual(
            sk.skill_rev("superpowers:brainstorming", self.root),
            hashlib.sha256(self.body).hexdigest()[:8],
        )

    def test_changes_when_the_skill_changes(self):
        before = sk.skill_rev("superpowers:brainstorming", self.root)
        with open(os.path.join(self.root, "skills", "brainstorming", "SKILL.md"), "ab") as handle:
            handle.write(b"more\n")
        self.assertNotEqual(before, sk.skill_rev("superpowers:brainstorming", self.root))

    def test_unresolvable_returns_none(self):
        self.assertIsNone(sk.skill_rev("superpowers:nonexistent", self.root))
        self.assertIsNone(sk.skill_rev("other-plugin:thing", self.root))
        self.assertIsNone(sk.skill_rev(None, self.root))
        self.assertIsNone(sk.skill_rev("superpowers:brainstorming", None))


class TestPluginVersion(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        os.makedirs(os.path.join(self.dir.name, ".claude-plugin"))

    def test_reads_version(self):
        path = os.path.join(self.dir.name, ".claude-plugin", "plugin.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"name": "superpowers", "version": "1.0.0"}, handle)
        self.assertEqual(sk.plugin_version(self.dir.name), "1.0.0")

    def test_missing_file_returns_none(self):
        self.assertIsNone(sk.plugin_version(self.dir.name))
        self.assertIsNone(sk.plugin_version(None))


class TestInvokedBy(unittest.TestCase):
    def test_slash_command_is_user(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", "/brainstorming let's go"), "user")

    def test_command_name_block_is_user(self):
        text = "<command-name>/brainstorming</command-name>\n<command-args>x</command-args>"
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", text), "user")

    def test_plain_prompt_is_model(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", "help me design a hook"), "model")

    def test_different_skill_named_in_prompt_is_model(self):
        self.assertEqual(sk.invoked_by("superpowers:writing-plans", "/brainstorming go"), "model")

    def test_no_prompt_or_no_skill(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", ""), "model")
        self.assertEqual(sk.invoked_by(None, "/brainstorming"), "model")

    # Namespaced plugin skills ("plugin:skill") must be matched under both
    # their bare short name and their full plugin-qualified name, in both
    # the <command-name> marker form and the bare "/prefix" form Claude Code
    # actually emits. Matching only the bare form inverts the signal: a
    # skill invoked by its qualified name reads as having fired on its own.
    def test_bare_command_name_marker_is_user(self):
        text = "<command-name>/brainstorming</command-name>"
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", text), "user")

    def test_plugin_qualified_command_name_marker_is_user(self):
        text = "<command-name>/superpowers:brainstorming</command-name>"
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", text), "user")

    def test_bare_slash_prefix_is_user(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", "/brainstorming go"), "user")

    def test_plugin_qualified_slash_prefix_is_user(self):
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", "/superpowers:brainstorming go"), "user")

    def test_marker_quoted_in_prose_is_not_an_invocation(self):
        """A prompt that merely quotes a <command-name> marker — as this
        repo's own briefs do — is prose, not a real command record. Real
        command records begin with the marker; this one doesn't."""
        text = ("The brief shows "
                "<command-name>/brainstorming</command-name> as an example.")
        self.assertEqual(sk.invoked_by("superpowers:brainstorming", text), "model")


class TestBlockingTools(unittest.TestCase):
    def test_human_blocking_tools(self):
        self.assertIn("AskUserQuestion", sk.HUMAN_BLOCKING_TOOLS)
        self.assertIn("ExitPlanMode", sk.HUMAN_BLOCKING_TOOLS)
        self.assertNotIn("Bash", sk.HUMAN_BLOCKING_TOOLS)


if __name__ == "__main__":
    unittest.main()
