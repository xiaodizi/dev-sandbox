# dev-sandbox 使用文档

在 Docker Desktop 中运行项目命令的隔离沙箱。命令在一次性容器中执行，项目目录挂载到 `/app`，依赖缓存持久保存在宿主机上。

## 前置条件

- macOS（Intel 或 Apple Silicon）、Linux 或 WSL
- 已安装并启动 Docker Desktop，`docker info` 能正常返回
- Python 3.10+（运行 `dev_sandbox` 模块）

Docker 不可用时直接报错退出，不会退回到宿主机裸跑。

## 快速开始

```bash
cd /path/to/your/project
PYTHONPATH=/Users/lei.fu/LLM/claude_code/dev-sandbox python3 -m dev_sandbox --image python:3.11-slim -- python main.py
```

或使用 Shell 包装脚本：

```bash
/Users/lei.fu/LLM/claude_code/dev-sandbox/run-in-docker.sh                     # 默认 Maven 镜像，执行 mvn test
/Users/lei.fu/LLM/claude_code/dev-sandbox/run-in-docker.sh python:3.11-slim python main.py
/Users/lei.fu/LLM/claude_code/dev-sandbox/run-in-docker.sh node:20-alpine npm run build
```

## 命令行参数（`python3 -m dev_sandbox`）

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `--image` | 镜像，默认 `maven:3.9-eclipse-temurin-11` | `--image node:20-alpine` |
| `--cpus` | CPU 上限 | `--cpus 2` |
| `--memory` | 内存上限 | `--memory 2g` |
| `--network` | 网络模式，`none` 表示断网 | `--network none` |
| `-- 命令...` | 容器内执行的命令，放在 `--` 之后 | `-- pytest -q` |

## 生态自动识别

根据镜像名识别语言生态，并挂载对应的宿主机缓存：

| 镜像前缀 | 宿主机缓存 | 容器内路径 | 默认命令 |
| :--- | :--- | :--- | :--- |
| `maven` | `~/.m2` | `/root/.m2` | `mvn test -Dmaven.repo.local=/root/.m2/repository`（项目有 `settings.xml` 时自动加 `-s`） |
| `node` / `bun` | `~/.npm` | `/root/.npm` | `npm test` |
| `python` | `~/.cache/pip` | `/root/.cache/pip` | `python main.py` |

其他镜像不挂载缓存，需要显式给出命令。

## Python 与 Shell 两种入口的差异

| 项目 | `dev_sandbox` 模块 | `run-in-docker.sh` |
| :--- | :--- | :--- |
| Docker 检测 | 执行前 `docker info`，超时 15 秒 | 无检测，依赖 `docker run` 自身报错 |
| 参数传递 | 参数数组，无 shell 拼接 | 参数数组 |
| 容器名 | 随机后缀，避免冲突 | 进程号后缀 |
| TTY | 不分配，适合 Agent 非交互调用 | 终端中自动分配 `-t` |

## 测试

```bash
cd /Users/lei.fu/LLM/claude_code/dev-sandbox
python3 -m unittest discover -s tests -t . -v
```

20 个用例覆盖镜像识别、参数构建、Docker 不可用时的失败路径、CLI 参数解析，以及 `run-in-docker.sh` 的各生态默认命令与缓存挂载（用假的 `docker` 命令记录参数）。这些测试不需要 Docker 运行。

真实容器的端到端验证（Python、Node、Maven 均已通过）不在单元测试内，需要 Docker Desktop 运行时手动执行。

## Maven 缓存说明

宿主机 `~/.m2/settings.xml` 若设置了 `localRepository`，容器内 Maven 会写到那个路径，挂载的缓存就不生效。因此默认命令固定加了 `-Dmaven.repo.local=/root/.m2/repository`，保证依赖始终落在宿主机 `~/.m2/repository`。自定义命令时若需要缓存，也要带上这个参数。

## 常见问题

- **`Docker 不可用：...`**：确认 Docker Desktop 已启动，`docker info` 可用。
- **`docker info 超过 15s 无响应`**：Docker Desktop 刚启动或负载高，等待就绪后重试。
- **首次运行很慢**：需要拉取镜像，之后镜像会缓存在本地。
- **缓存目录权限**：缓存目录由程序在宿主机上创建，若已存在且属于 root，需要 `sudo chown` 修复。

## 文件结构

```
dev-sandbox/
├── dev_sandbox/
│   ├── __init__.py
│   ├── __main__.py     # python3 -m dev_sandbox 入口
│   ├── cli.py          # 命令行参数解析
│   └── sandbox.py      # Docker 检测、参数构建、运行
├── tests/
│   └── test_sandbox.py
├── run-in-docker.sh    # Shell 包装脚本
└── USAGE.md
```
