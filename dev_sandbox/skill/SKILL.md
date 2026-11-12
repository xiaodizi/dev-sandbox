---
name: dev-sandbox
description: Run project tests, builds, dependency installs and other project commands inside a Docker sandbox instead of on the host. Use when running tests, builds, package installs (pip, npm, mvn), or any command that executes project code.
---

# dev-sandbox

在 Docker Desktop 的一次性容器中执行项目命令。项目目录挂载到容器 `/app`，依赖缓存保存在宿主机（`~/.m2`、`~/.npm`、`~/.cache/pip`）。

## 何时使用

- 运行测试、构建、lint、安装依赖
- 执行任何会运行项目代码的命令

不需要沙箱的情况：读文件、编辑代码、git 操作。

## 调用方式

```bash
dev-sandbox --image <镜像> -- <命令>
```

按项目语言选择镜像：

| 项目 | `--image` | 默认命令（不带 `--` 时） |
| :--- | :--- | :--- |
| Python | `python:3.11-slim` | `python main.py` |
| Node | `node:20-alpine` | `npm test` |
| Maven | `maven:3.9-eclipse-temurin-11` | `mvn test` |

示例：

```bash
dev-sandbox --image python:3.11-slim -- sh -c 'pip install -q pytest && python -m pytest -q'
dev-sandbox --image node:20-alpine -- npm test
dev-sandbox --image maven:3.9-eclipse-temurin-11 -- mvn -B test
```

## 在沙箱内操作 Docker

仅当命令本身需要 docker（`docker build`、`docker run`、`docker inspect`、`docker compose`、`docker pull/push`）时使用。

```bash
dev-sandbox --image docker:27-cli -- docker build -t app:test .
dev-sandbox --docker --image python:3.11-slim -- sh -c 'docker build -t app:test . && docker run --rm app:test ls -l /app'
```

- 跑 Maven、npm、Python、Nginx 等不需要 docker 的命令，不要加 `--docker`。
- `--docker` 不能与 `--network` 同时使用。
- 沙箱内的 daemon 是独立的，看不到宿主机镜像，需要的基础镜像会从 registry 拉取。
- 每次运行都会新建并在结束后删除 daemon，其中的镜像不会保留。构建和使用镜像要放在同一条命令里完成。

## 规则

- 不要直接在宿主机运行 `python`、`pytest`、`npm`、`mvn` 执行项目代码，统一走上面的命令。
- 需要断网时加 `--network none`；限制资源时加 `--cpus 2 --memory 2g`。
- Docker 不可用时命令退出码为 `1` 并输出错误，应把错误报告给用户，不要改为宿主机执行。
- Maven 命令若要使用缓存，带上 `-Dmaven.repo.local=/root/.m2/repository`。
