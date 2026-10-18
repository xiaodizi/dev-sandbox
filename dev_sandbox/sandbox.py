"""Run commands inside an ephemeral Docker container bound to the project directory."""

import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

DOCKER_TIMEOUT_SECONDS = 15


class SandboxError(RuntimeError):
    """Raised when the sandbox cannot be used. Never falls back to running on the host."""


@dataclass(frozen=True)
class Ecosystem:
    name: str
    image: str
    cache_host: str
    cache_container: str
    default_cmd: tuple
    keywords: tuple


ECOSYSTEMS = (
    Ecosystem("maven", "maven:3.9-eclipse-temurin-11", "~/.m2", "/root/.m2",
              ("mvn", "test"), ("maven",)),
    Ecosystem("node", "node:20-alpine", "~/.npm", "/root/.npm",
              ("npm", "test"), ("node", "bun")),
    Ecosystem("python", "python:3.11-slim", "~/.cache/pip", "/root/.cache/pip",
              ("python", "main.py"), ("python",)),
)


@dataclass(frozen=True)
class SandboxOptions:
    image: str | None = None
    cpus: str | None = None
    memory: str | None = None
    network: str | None = None
    command: tuple = field(default_factory=tuple)


def detect_ecosystem(image: str) -> Ecosystem | None:
    repo = image.rsplit("/", 1)[-1].split(":", 1)[0]
    for eco in ECOSYSTEMS:
        if repo.split("-", 1)[0] in eco.keywords:
            return eco
    return None


def safe_container_name(project_dir: Path) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]", "-", project_dir.name) or "project"
    return f"sandbox-{base}-{uuid.uuid4().hex[:8]}"


MAVEN_REPO_FLAG = "-Dmaven.repo.local=/root/.m2/repository"


def default_command(project_dir: Path, eco: Ecosystem) -> tuple:
    if eco.name == "maven":
        for settings in ("settings.xml", ".mvn/settings.xml"):
            if (project_dir / settings).is_file():
                return ("mvn", "test", "-s", settings, MAVEN_REPO_FLAG)
        return ("mvn", "test", MAVEN_REPO_FLAG)
    return eco.default_cmd


def build_docker_args(project_dir: Path, options: SandboxOptions, container_name: str) -> list:
    """Build the docker run argument list. Host cache dirs are created by prepare_host_caches."""
    project_dir = project_dir.resolve()
    image = options.image or ECOSYSTEMS[0].image
    eco = detect_ecosystem(image)

    args = ["docker", "run", "--rm", "--name", container_name,
            "-v", f"{project_dir}:/app", "-w", "/app"]
    if options.cpus:
        args += ["--cpus", options.cpus]
    if options.memory:
        args += ["--memory", options.memory]
    if options.network:
        args += ["--network", options.network]
    if eco is not None:
        cache_host = Path(os.path.expanduser(eco.cache_host))
        args += ["-v", f"{cache_host}:{eco.cache_container}"]

    args.append(image)
    command = tuple(options.command) or (default_command(project_dir, eco) if eco else ())
    args += list(command)
    return args


def prepare_host_caches(image: str) -> None:
    eco = detect_ecosystem(image)
    if eco is not None:
        Path(os.path.expanduser(eco.cache_host)).mkdir(parents=True, exist_ok=True)


def check_docker(runner=subprocess.run) -> None:
    try:
        result = runner(["docker", "info"], capture_output=True, text=True,
                        timeout=DOCKER_TIMEOUT_SECONDS)
    except FileNotFoundError as exc:
        raise SandboxError("未找到 docker 命令，请确认已安装 Docker Desktop") from exc
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"docker info 超过 {DOCKER_TIMEOUT_SECONDS}s 无响应，Docker Desktop 可能未就绪") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["未知错误"]
        raise SandboxError(f"Docker 不可用：{detail[0]}")


def run_in_sandbox(project_dir: Path, options: SandboxOptions, runner=subprocess.run) -> int:
    check_docker(runner)
    image = options.image or ECOSYSTEMS[0].image
    prepare_host_caches(image)
    args = build_docker_args(project_dir, options, safe_container_name(project_dir))
    return runner(args).returncode
