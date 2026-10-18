#!/bin/bash
# Multi-language Docker sandbox wrapper (macOS Intel/Apple Silicon, Linux, WSL).
# Usage: run-in-docker.sh [image] [command...]
set -o errexit
set -o nounset

if ! timeout_out=$(docker info 2>&1 >/dev/null); then
    echo "[Sandbox] 错误：Docker 不可用，请确认 Docker Desktop 已启动" >&2
    echo "$timeout_out" | tail -1 >&2
    exit 1
fi

PROJECT_NAME=$(basename "$(pwd)")
IMAGE_NAME="${1:-maven:3.9-eclipse-temurin-11}"
if [ $# -gt 0 ]; then
    shift
fi

CACHE_ARGS=()
DEFAULT_CMD=()
TTY_ARGS=()
if [ -t 0 ] && [ -t 1 ]; then
    TTY_ARGS=(-t)
fi

if [[ "$IMAGE_NAME" == maven* ]]; then
    mkdir -p "$HOME/.m2"
    CACHE_ARGS=(-v "$HOME/.m2:/root/.m2")
    REPO_FLAG="-Dmaven.repo.local=/root/.m2/repository"
    if [ -f "settings.xml" ]; then
        DEFAULT_CMD=(mvn test -s settings.xml "$REPO_FLAG")
    elif [ -f ".mvn/settings.xml" ]; then
        DEFAULT_CMD=(mvn test -s .mvn/settings.xml "$REPO_FLAG")
    else
        DEFAULT_CMD=(mvn test "$REPO_FLAG")
    fi
elif [[ "$IMAGE_NAME" == node* ]] || [[ "$IMAGE_NAME" == *bun* ]]; then
    mkdir -p "$HOME/.npm"
    CACHE_ARGS=(-v "$HOME/.npm:/root/.npm")
    DEFAULT_CMD=(npm test)
elif [[ "$IMAGE_NAME" == python* ]]; then
    mkdir -p "$HOME/.cache/pip"
    CACHE_ARGS=(-v "$HOME/.cache/pip:/root/.cache/pip")
    DEFAULT_CMD=(python main.py)
fi

if [ $# -gt 0 ]; then
    EXEC_CMD=("$@")
else
    EXEC_CMD=("${DEFAULT_CMD[@]}")
fi

echo "[Sandbox] project=$PROJECT_NAME image=$IMAGE_NAME cmd=${EXEC_CMD[*]:-<image default>}"

docker run --rm ${TTY_ARGS[@]+"${TTY_ARGS[@]}"} -i \
    --name "sandbox-${PROJECT_NAME}-$$" \
    -v "$(pwd):/app" \
    -w /app \
    ${CACHE_ARGS[@]+"${CACHE_ARGS[@]}"} \
    "$IMAGE_NAME" \
    ${EXEC_CMD[@]+"${EXEC_CMD[@]}"}
