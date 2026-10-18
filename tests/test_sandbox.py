import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dev_sandbox.cli import main
from dev_sandbox.sandbox import (
    SandboxError,
    SandboxOptions,
    build_docker_args,
    check_docker,
    detect_ecosystem,
    run_in_sandbox,
)


def completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class DetectEcosystemTest(unittest.TestCase):
    def test_matches_known_images(self):
        self.assertEqual(detect_ecosystem("maven:3.9-eclipse-temurin-11").name, "maven")
        self.assertEqual(detect_ecosystem("node:20-alpine").name, "node")
        self.assertEqual(detect_ecosystem("oven/bun:1").name, "node")
        self.assertEqual(detect_ecosystem("maven:3.9").name, "maven")
        self.assertEqual(detect_ecosystem("python:3.11-slim").name, "python")

    def test_unknown_image_has_no_ecosystem(self):
        self.assertIsNone(detect_ecosystem("ubuntu:24.04"))


class BuildDockerArgsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_mounts_project_and_uses_argument_array_without_tty(self):
        args = build_docker_args(self.project, SandboxOptions(image="python:3.11-slim",
                                 command=("python", "a b.py")), "sandbox-x")
        self.assertEqual(args[:2], ["docker", "run"])
        self.assertIn("--rm", args)
        self.assertNotIn("-t", args)
        self.assertNotIn("-it", args)
        self.assertIn(f"{self.project}:/app", args)
        self.assertEqual(args[args.index("-w") + 1], "/app")
        self.assertEqual(args[-2:], ["python", "a b.py"])

    def test_python_cache_mounted(self):
        args = build_docker_args(self.project, SandboxOptions(image="python:3.11-slim"), "n")
        cache = str(Path("~/.cache/pip").expanduser())
        self.assertIn(f"{cache}:/root/.cache/pip", args)

    def test_maven_uses_project_settings_when_present(self):
        (self.project / "settings.xml").write_text("<settings/>")
        args = build_docker_args(self.project, SandboxOptions(image="maven:3.9-eclipse-temurin-11"), "n")
        self.assertEqual(args[-5:], ["mvn", "test", "-s", "settings.xml", "-Dmaven.repo.local=/root/.m2/repository"])
        self.assertIn(f"{Path('~/.m2').expanduser()}:/root/.m2", args)

    def test_resource_and_network_flags(self):
        opts = SandboxOptions(image="node:20-alpine", cpus="2", memory="2g", network="none")
        args = build_docker_args(self.project, opts, "n")
        self.assertEqual(args[args.index("--cpus") + 1], "2")
        self.assertEqual(args[args.index("--memory") + 1], "2g")
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertEqual(args[-2:], ["npm", "test"])

    def test_unknown_image_without_command_has_no_cache_mount(self):
        args = build_docker_args(self.project, SandboxOptions(image="ubuntu:24.04"), "n")
        self.assertEqual(args[-1], "ubuntu:24.04")
        self.assertEqual(args.count("-v"), 1)


class CheckDockerTest(unittest.TestCase):
    def test_passes_when_docker_info_succeeds(self):
        check_docker(runner=lambda *a, **k: completed(0))

    def test_fails_loudly_on_nonzero_exit(self):
        with self.assertRaises(SandboxError):
            check_docker(runner=lambda *a, **k: completed(1, "Cannot connect to the Docker daemon"))

    def test_fails_loudly_when_docker_missing(self):
        def missing(*a, **k):
            raise FileNotFoundError
        with self.assertRaises(SandboxError):
            check_docker(runner=missing)

    def test_fails_loudly_on_timeout(self):
        def slow(*a, **k):
            raise subprocess.TimeoutExpired(cmd="docker info", timeout=15)
        with self.assertRaises(SandboxError):
            check_docker(runner=slow)


class RunInSandboxTest(unittest.TestCase):
    def test_never_runs_container_when_docker_unavailable(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return completed(1, "daemon down")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SandboxError):
                run_in_sandbox(Path(tmp), SandboxOptions(image="python:3.11-slim"), runner=runner)
        self.assertEqual(calls, [["docker", "info"]])

    def test_runs_container_and_returns_exit_code(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return completed(0) if args == ["docker", "info"] else subprocess.CompletedProcess(args, 3)

        with tempfile.TemporaryDirectory() as tmp:
            code = run_in_sandbox(Path(tmp), SandboxOptions(image="python:3.11-slim"), runner=runner)
        self.assertEqual(code, 3)
        self.assertEqual(calls[1][0:2], ["docker", "run"])


class CliTest(unittest.TestCase):
    def test_cli_reports_error_and_returns_1(self):
        with mock.patch("dev_sandbox.cli.run_in_sandbox", side_effect=SandboxError("no docker")):
            self.assertEqual(main([], project_dir=Path.cwd()), 1)

    def test_cli_passes_command_after_double_dash(self):
        with mock.patch("dev_sandbox.cli.run_in_sandbox", return_value=0) as run:
            main(["--image", "python:3.11-slim", "--", "python", "t.py"], project_dir=Path("/tmp"))
        options = run.call_args.args[1]
        self.assertEqual(options.command, ("python", "t.py"))
        self.assertEqual(options.image, "python:3.11-slim")


if __name__ == "__main__":
    unittest.main()
