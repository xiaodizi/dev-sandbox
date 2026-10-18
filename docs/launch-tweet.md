# dev-sandbox：让 AI 在 Docker 沙箱里跑代码

做了个小工具 **dev-sandbox**：让 AI Coding 工具（Claude Code、pi）跑测试、装依赖时，全部在 Docker 一次性容器里执行，不碰宿主机。

- 项目挂载进容器，跑完即删
- Maven / npm / pip 缓存持久保存在本机，不用反复下载
- Docker 没启动就直接报错，不会偷偷退回裸跑
- `dev-sandbox install` 一键装 skill，AI 直接调用

GitHub：https://github.com/xiaodizi/dev-sandbox （MIT）
