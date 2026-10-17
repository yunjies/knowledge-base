# 领域 agent 脚手架

本目录定义可复用的领域 agent 规范与脚本优先的宿主工具模板。维护约束见 [`AGENTS.md`](AGENTS.md)，唯一规范源为 [`spec.md`](spec.md)，模板入口为 [`template/README.md`](template/README.md)。

每个实例只服务一个领域。agent 通过当前 preset 注册的 host tools 取得结构化策略和按需知识；工具实现位于 `scripts/`，数据契约位于 `data/`。agent 不直接遍历或盲读领域知识目录。
