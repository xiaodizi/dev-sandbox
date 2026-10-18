# Agent 接入规范

dev-sandbox 通过命令行调用，任何能执行 shell 命令的 Agent（Claude Code、pi 等）都可以用同一接口接入。

## 调用约定

```bash
python3 -m dev_sandbox [--image IMG] [--cpus N] [--memory M] [--network NET] -- <命令...>
```

- 退出码：容器内命令的退出码原样返回；Docker 不可用时返回 `1`，错误信息写到 stderr。
- 不分配 TTY，适合 Agent 非交互调用。
- 工作目录即项目根目录，挂载到容器 `/app`。
- 不会在 Docker 不可用时退回到宿主机执行。

## 在 Agent 中的配置示例

Claude Code（项目 `.claude/settings.json` 或 Bash 工具中）：

```bash
PYTHONPATH=/Users/lei.fu/LLM/claude_code/dev-sandbox python3 -m dev_sandbox --image python:3.11-slim -- python -m pytest -q
```

pi 或其他 Agent：把同一条命令配置为其"运行测试"或"执行命令"的工具，`--image` 按项目语言选择。

## 推荐做法

- 让 Agent 只通过该命令执行项目代码，不直接调用宿主机 `python`、`mvn`、`npm`。
- 需要断网的任务加 `--network none`，依赖已缓存时可用。
- 限制资源时加 `--cpus` 与 `--memory`，防止失控进程占满 Mac。

## 已验证

| 生态 | 镜像 | 验证内容 | 结果 |
| :--- | :--- | :--- | :--- |
| Python | `python:3.11-slim` | 运行 `main.py` | 输出正常 |
| Node | `node:20-alpine` | `npm test` | 输出正常 |
| Maven | `maven:3.9-eclipse-temurin-11` | 下载依赖并写入宿主机 `~/.m2` | 构建成功，jar 已缓存 |
