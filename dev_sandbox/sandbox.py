"""Run commands inside an ephemeral Docker container bound to the project directory."""

import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

DOCKER_TIMEOUT_SECONDS = 15
DIND_IMAGE = "docker:27-dind"
DIND_HOST = "docker"
DIND_READY_TIMEOUT_SECONDS = 60


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
    docker: bool = False
    mounts: tuple = field(default_factory=tuple)
    command: tuple = field(default_factory=tuple)


def image_repo(image: str) -> str:
    return image.rsplit("/", 1)[-1].split(":", 1)[0]


def detect_ecosystem(image: str) -> Ecosystem | None:
    repo = image_repo(image)
    for eco in ECOSYSTEMS:
        if repo.split("-", 1)[0] in eco.keywords:
            return eco
    return None


def parse_mount(spec: str) -> str:
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise SandboxError(f"--mount 格式应为 HOST:CONTAINER[:ro]，收到：{spec}")
    host, container = os.path.expanduser(parts[0]), parts[1]
    if not os.path.isabs(host):
        raise SandboxError(f"--mount 宿主机路径必须是绝对路径或 ~ 开头：{parts[0]}")
    if not os.path.exists(host):
        raise SandboxError(f"--mount 宿主机路径不存在：{host}")
    if not container.startswith("/"):
        raise SandboxError(f"--mount 容器路径必须是绝对路径：{container}")
    if len(parts) == 3 and parts[2] != "ro":
        raise SandboxError(f"--mount 只支持 ro 模式：{spec}")
    return ":".join([host, container, *parts[2:]])


def needs_docker_sidecar(options: SandboxOptions, image: str) -> bool:
    return options.docker or image_repo(image) == "docker"


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
    if needs_docker_sidecar(options, image):
        args += docker_access_args(container_name)
    elif options.network:
        args += ["--network", options.network]
    if eco is not None:
        cache_host = Path(os.path.expanduser(eco.cache_host))
        args += ["-v", f"{cache_host}:{eco.cache_container}"]
    for mount in options.mounts:
        args += ["-v", parse_mount(mount)]

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


def docker_session_names(container_name: str) -> dict:
    return {"net": f"{container_name}-net", "dind": f"{container_name}-dind",
            "certs": f"{container_name}-certs"}


def docker_access_args(container_name: str) -> list:
    names = docker_session_names(container_name)
    return ["--network", names["net"],
            "-v", f"{names['certs']}:/certs/client:ro",
            "-e", f"DOCKER_HOST=tcp://{DIND_HOST}:2376",
            "-e", "DOCKER_TLS_VERIFY=1",
            "-e", "DOCKER_CERT_PATH=/certs/client"]


def _run_docker(runner, *args) -> subprocess.CompletedProcess:
    result = runner(["docker", *args], capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "未知错误"
        raise SandboxError(f"docker {args[0]} 失败：{detail}")
    return result


def start_dind(container_name: str, runner) -> None:
    names = docker_session_names(container_name)
    _run_docker(runner, "network", "create", names["net"])
    _run_docker(runner, "run", "-d", "--privileged", "--name", names["dind"],
                "--network", names["net"], "--network-alias", DIND_HOST,
                "-e", "DOCKER_TLS_CERTDIR=/certs",
                "-v", f"{names['certs']}:/certs/client", DIND_IMAGE)
    deadline = time.monotonic() + DIND_READY_TIMEOUT_SECONDS
    while runner(["docker", "exec", names["dind"], "docker", "info"],
                 capture_output=True, text=True).returncode != 0:
        if time.monotonic() > deadline:
            raise SandboxError(f"Docker 沙箱 daemon 超过 {DIND_READY_TIMEOUT_SECONDS}s 未就绪")
        time.sleep(1)


def stop_dind(container_name: str, runner) -> None:
    names = docker_session_names(container_name)
    runner(["docker", "rm", "-f", "-v", names["dind"]], capture_output=True, text=True)
    runner(["docker", "network", "rm", names["net"]], capture_output=True, text=True)
    runner(["docker", "volume", "rm", names["certs"]], capture_output=True, text=True)


def run_in_sandbox(project_dir: Path, options: SandboxOptions, runner=subprocess.run) -> int:
    image = options.image or ECOSYSTEMS[0].image
    sidecar = needs_docker_sidecar(options, image)
    if sidecar and options.network:
        raise SandboxError("Docker 侧车模式与 --network 不能同时使用")
    container_name = safe_container_name(project_dir)
    args = build_docker_args(project_dir, options, container_name)
    check_docker(runner)
    prepare_host_caches(image)
    if not sidecar:
        return runner(args).returncode
    try:
        start_dind(container_name, runner)
        return runner(args).returncode
    finally:
        stop_dind(container_name, runner)
