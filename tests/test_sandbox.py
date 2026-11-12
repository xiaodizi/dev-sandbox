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

    def test_cli_passes_docker_flag(self):
        with mock.patch("dev_sandbox.cli.run_in_sandbox", return_value=0) as run:
            main(["--docker", "--image", "docker:27-cli", "--", "docker", "version"], project_dir=Path("/tmp"))
        self.assertTrue(run.call_args.args[1].docker)


class DockerSidecarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_docker_mode_wires_tls_endpoint_without_socket(self):
        opts = SandboxOptions(image="docker:27-cli", docker=True, command=("docker", "version"))
        args = build_docker_args(self.project, opts, "sandbox-p-1")
        self.assertIn("sandbox-p-1-net", args)
        self.assertIn("DOCKER_HOST=tcp://docker:2376", args)
        self.assertIn("DOCKER_TLS_VERIFY=1", args)
        self.assertIn("sandbox-p-1-certs:/certs/client:ro", args)
        self.assertFalse(any("docker.sock" in a for a in args))
        self.assertEqual(args[-2:], ["docker", "version"])

    def test_docker_image_enables_sidecar_without_flag(self):
        args = build_docker_args(self.project, SandboxOptions(image="docker:27-cli"), "sandbox-p-1")
        self.assertIn("DOCKER_HOST=tcp://docker:2376", args)

    def test_docker_and_network_are_mutually_exclusive(self):
        opts = SandboxOptions(image="python:3.11-slim", docker=True, network="none")
        with self.assertRaises(SandboxError):
            run_in_sandbox(self.project, opts, runner=lambda *a, **k: completed(0))

    def test_sidecar_started_before_run_and_cleaned_up_after(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            if args[:2] == ["docker", "run"] and "--privileged" not in args:
                return subprocess.CompletedProcess(args, 7)
            return completed(0)

        code = run_in_sandbox(self.project, SandboxOptions(image="docker:27-cli", docker=True),
                              runner=runner)
        self.assertEqual(code, 7)
        joined = [" ".join(c) for c in calls]
        dind_start = next(i for i, c in enumerate(joined) if "--privileged" in c)
        app_run = next(i for i, c in enumerate(joined) if c.startswith("docker run --rm"))
        self.assertLess(dind_start, app_run)
        self.assertTrue(any(c.startswith("docker rm -f -v sandbox-") for c in joined))
        self.assertTrue(any(c.startswith("docker network rm sandbox-") for c in joined))
        self.assertTrue(any(c.startswith("docker volume rm sandbox-") for c in joined))

    def test_sidecar_cleaned_up_when_start_fails(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            if "--privileged" in args:
                return completed(1, "no privileges")
            return completed(0)

        with self.assertRaises(SandboxError):
            run_in_sandbox(self.project, SandboxOptions(image="docker:27-cli", docker=True),
                           runner=runner)
        self.assertTrue(any(c[:3] == ["docker", "rm", "-f"] for c in calls))


if __name__ == "__main__":
    unittest.main()
