"""Command line entry: dev-sandbox [--image IMG] [--cpus N] [--memory M] [--network NET] [-- cmd...]"""

import argparse
import sys
from pathlib import Path

from dev_sandbox.installer import install_skills
from dev_sandbox.sandbox import SandboxError, SandboxOptions, run_in_sandbox


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-sandbox", description="在 Docker 沙箱中运行项目命令")
    parser.add_argument("--image", help="镜像名，默认 maven:3.9-eclipse-temurin-11")
    parser.add_argument("--cpus", help="CPU 上限，例如 2")
    parser.add_argument("--memory", help="内存上限，例如 2g")
    parser.add_argument("--network", help="网络模式，例如 none；默认 Docker 网络")
    parser.add_argument("--docker", action="store_true",
                        help="启动专用 Docker daemon 侧车，容器内可用 docker 命令（不能与 --network 同用）")
    parser.add_argument("--mount", action="append", default=[], metavar="HOST:CONTAINER[:ro]",
                        help="额外挂载宿主机文件或目录到容器，可重复；例如 --mount ~/cfg/jhpt.xml:/config/jhpt.xml:ro")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="容器内执行的命令，放在 -- 之后")
    return parser


def install_main(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="dev-sandbox install", description="把 skill 安装到 AI Coding 工具")
    parser.add_argument("--target", action="append", default=[],
                        help="claude、pi 或 all（默认 all），可重复指定")
    args = parser.parse_args(argv)
    try:
        written = install_skills(args.target)
    except ValueError as exc:
        print(f"[dev-sandbox] 错误：{exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"已安装：{path}")
    return 0


def main(argv=None, project_dir: Path | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "install":
        return install_main(argv[1:])
    args = build_parser().parse_args(argv)
    command = tuple(c for c in args.command if c != "--")
    options = SandboxOptions(image=args.image, cpus=args.cpus, memory=args.memory,
                             network=args.network, docker=args.docker, mounts=tuple(args.mount),
                             command=command)
    try:
        return run_in_sandbox(project_dir or Path.cwd(), options)
    except SandboxError as exc:
        print(f"[dev-sandbox] 错误：{exc}", file=sys.stderr)
        return 1


def console_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    console_main()
