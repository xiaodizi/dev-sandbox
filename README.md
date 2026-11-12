# dev-sandbox

在 Docker Desktop 的一次性容器中运行项目命令（测试、构建、安装依赖），让 AI Coding 工具不必直接在宿主机执行项目代码。

- 项目目录挂载到容器 `/app`，命令结束后容器自动删除。
- 依赖缓存持久保存在宿主机（`~/.m2`、`~/.npm`、`~/.cache/pip`），重复运行不会重新下载。
- Docker 不可用时直接报错退出，不会退回到宿主机执行。
- 可以一键把 skill 安装到 Claude Code 和 pi，AI 工具通过 `dev-sandbox` 命令调用。

## 环境要求

- macOS（Intel 或 Apple Silicon）、Linux 或 WSL
- Docker Desktop，已启动，`docker info` 可用
- Python 3.10+
- [pipx](https://pipx.pypa.io/)（推荐用于安装命令）

## 安装

```bash
git clone https://github.com/xiaodizi/dev-sandbox.git
cd dev-sandbox
pipx install .
```

升级到新版本（本地仓库）：

```bash
pipx install --force .
```

直接从 GitHub 安装或更新，无需先 clone：

```bash
pipx install --force git+https://github.com/xiaodizi/dev-sandbox.git
dev-sandbox install
```

升级后需要再次执行 `dev-sandbox install`，把新的 SKILL.md 同步到 AI Coding 工具，并重启对应工具才会生效。

## 安装到 AI Coding 工具

```bash
dev-sandbox install                  # 安装到 Claude Code 和 pi
dev-sandbox install --target pi      # 只安装到 pi
dev-sandbox install --target claude  # 只安装到 Claude Code
```

安装的位置：

| 工具 | Skill 路径 |
| :--- | :--- |
| Claude Code | `~/.claude/skills/dev-sandbox/SKILL.md` |
| pi | `~/.pi/agent/skills/dev-sandbox/SKILL.md` |

安装后，在对应工具里直接说任务即可，例如"用 dev-sandbox 跑一下 pytest"。AI 会调用：

```bash
dev-sandbox --image python:3.11-slim -- sh -c 'pip install -q pytest && python -m pytest -q'
```

## 命令行用法

```bash
dev-sandbox [--image 镜像] [--cpus N] [--memory M] [--network 网络] -- <命令...>
```

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `--image` | 运行的镜像，默认 `maven:3.9-eclipse-temurin-11` | `--image node:20-alpine` |
| `--cpus` | CPU 上限 | `--cpus 2` |
| `--memory` | 内存上限 | `--memory 2g` |
| `--network` | 网络模式，`none` 表示断网 | `--network none` |
| `--docker` | 启动专用 Docker daemon，容器内可用 `docker` 命令，不能与 `--network` 同用 | `--docker` |
| `-- 命令...` | 容器内执行的命令，放在 `--` 之后 | `-- npm test` |

不带 `--` 命令时，按镜像自动选择默认命令：

| 镜像 | 挂载的宿主机缓存 | 默认命令 |
| :--- | :--- | :--- |
| `maven:*` | `~/.m2` | `mvn test -Dmaven.repo.local=/root/.m2/repository`（有 `settings.xml` 时自动加 `-s`） |
| `node:*` | `~/.npm` | `npm test` |
| `python:*` | `~/.cache/pip` | `python main.py` |

其他镜像不挂载缓存，需要显式给出命令。

### 示例

```bash
# Python 项目
dev-sandbox --image python:3.11-slim -- sh -c 'pip install -r requirements.txt && pytest'

# Node 项目
dev-sandbox --image node:20-alpine -- npm run build

# Maven 项目
dev-sandbox --image maven:3.9-eclipse-temurin-11 -- mvn -B test

# 断网运行，限制资源
dev-sandbox --image python:3.11-slim --network none --cpus 2 --memory 2g -- pytest
```

### 在沙箱内使用 Docker

只有命令本身需要 `docker`（如 `build`、`run`、`inspect`、`compose`、`pull/push`）时才需要。跑 Maven、npm、Python 等普通命令不要加 `--docker`。

```bash
# 使用 docker:* 镜像时自动开启
dev-sandbox --image docker:27-cli -- docker version

# 在 Python 镜像里构建并运行镜像
dev-sandbox --docker --image python:3.11-slim -- sh -c 'docker build -t app:test . && docker run --rm app:test ls -l /app'
```

- 沙箱使用独立的 `docker:27-dind` daemon，通过 TLS 访问，**不挂载宿主机的 Docker socket**，也不开放未认证的 TCP 端口。
- 沙箱 daemon 看不到宿主机镜像，基础镜像从 registry 拉取。
- 每次运行都会新建 daemon，结束后删除（包括其中的镜像）。构建和使用镜像必须放在同一条命令里完成。
- daemon 以 `--privileged` 运行，首次会拉取 `docker:27-dind`。

## 配置说明

- **Maven 缓存**：宿主机 `~/.m2/settings.xml` 若设置了 `localRepository`，容器内 Maven 会写到别处。因此默认命令固定加了 `-Dmaven.repo.local=/root/.m2/repository`。自定义 Maven 命令需要缓存时请保留这个参数。
- **依赖安装**：容器内不会带上宿主机的环境，依赖要在命令里安装（如 `pip install -r requirements.txt`）。

## 脚本版本

仓库里还有 `run-in-docker.sh`，功能与命令相同，适合不想安装 Python 包的场景：

```bash
./run-in-docker.sh python:3.11-slim python main.py
```

## 开发与测试

```bash
python3 -m unittest discover -s tests -t . -v
```

测试不需要 Docker 运行，使用假的 `docker` 命令验证参数构建和失败路径。真实容器的端到端验证需要 Docker Desktop 运行时手动执行。

## 常见问题

- **`Docker 不可用`**：确认 Docker Desktop 已启动，终端里 `docker info` 能正常返回。
- **`docker info 超过 15s 无响应`**：Docker Desktop 刚启动或负载高，稍等后重试。
- **首次运行很慢**：需要拉取镜像，之后会缓存在本地。
- **缓存目录属于 root**：若 `~/.m2` 等目录由 root 创建，需要 `sudo chown -R $USER ~/.m2` 修复。

## 项目结构

```
dev-sandbox/
├── dev_sandbox/
│   ├── cli.py          # 命令行入口与 install 子命令
│   ├── sandbox.py      # Docker 检测、参数构建、运行
│   ├── installer.py    # 安装 skill 到 AI 工具
│   └── skill/SKILL.md  # 打包进命令的 skill 内容
├── tests/              # 单元测试
├── run-in-docker.sh    # Shell 版本
├── USAGE.md            # 使用说明
├── AGENT_INTEGRATION.md
└── LICENSE
```

## 许可

[MIT](LICENSE)
