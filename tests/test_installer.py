import tempfile
import unittest
from pathlib import Path

from dev_sandbox.installer import expand_targets, install_skills


class InstallSkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_installs_to_all_targets_by_default(self):
        written = install_skills([], home=self.home)
        self.assertEqual(
            sorted(p.relative_to(self.home).as_posix() for p in written),
            [".claude/skills/dev-sandbox/SKILL.md", ".pi/agent/skills/dev-sandbox/SKILL.md"],
        )
        for path in written:
            self.assertIn("name: dev-sandbox", path.read_text(encoding="utf-8"))

    def test_installs_only_requested_target(self):
        written = install_skills(["pi"], home=self.home)
        self.assertEqual(len(written), 1)
        self.assertTrue((self.home / ".pi/agent/skills/dev-sandbox/SKILL.md").is_file())
        self.assertFalse((self.home / ".claude").exists())

    def test_unknown_target_is_rejected(self):
        with self.assertRaises(ValueError):
            expand_targets(["vscode"])


if __name__ == "__main__":
    unittest.main()
