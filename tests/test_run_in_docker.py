import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "run-in-docker.sh"
REPO_FLAG = "-Dmaven.repo.local=/root/.m2/repository"


class RunInDockerScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "docker.log"
        fake = self.bin / "docker"
        fake.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > "{self.log}"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.project = self.root / "proj"
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}"}
        result = subprocess.run(["bash", str(SCRIPT), *args], cwd=self.project,
                                env=env, capture_output=True, text=True)
        docker_args = self.log.read_text().splitlines() if self.log.exists() else []
        return result, docker_args

    def test_python_default_mounts_pip_cache_and_runs_given_command(self):
        result, args = self.run_script("python:3.11-slim", "python", "app.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{self.home}/.cache/pip:/root/.cache/pip", args)
        self.assertEqual(args[-3:], ["python:3.11-slim", "python", "app.py"])
        self.assertNotIn("-t", args)

    def test_node_default_command_when_none_given(self):
        result, args = self.run_script("node:20-alpine")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{self.home}/.npm:/root/.npm", args)
        self.assertEqual(args[-3:], ["node:20-alpine", "npm", "test"])

    def test_maven_default_pins_local_repo_to_mount(self):
        result, args = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{self.home}/.m2:/root/.m2", args)
        self.assertEqual(args[-3:], ["mvn", "test", REPO_FLAG])

    def test_maven_uses_project_settings_before_repo_flag(self):
        (self.project / "settings.xml").write_text("<settings/>")
        result, args = self.run_script("maven:3.9-eclipse-temurin-11")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[-5:], ["mvn", "test", "-s", "settings.xml", REPO_FLAG])

    def test_fails_without_running_container_when_docker_info_fails(self):
        fake = self.bin / "docker"
        fake.write_text('#!/bin/bash\nif [ "$1" = "info" ]; then echo "daemon down" >&2; exit 1; fi\n'
                        f'printf "%s\\n" "$@" > "{self.log}"\n')
        result, args = self.run_script("python:3.11-slim", "python", "app.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Docker 不可用", result.stderr)
        self.assertEqual(args, [])

    def test_arguments_with_spaces_stay_single_argument(self):
        result, args = self.run_script("python:3.11-slim", "python", "my app.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[-1], "my app.py")


if __name__ == "__main__":
    unittest.main()
