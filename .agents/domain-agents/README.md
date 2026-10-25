# 领域 agent 脚手架

本目录定义跨领域复用的 agent 脚手架、工具契约与脚本实现。维护约束见 [`AGENTS.md`](AGENTS.md)，唯一规范源为 [`spec.md`](spec.md)，通用脚手架清单与验收边界见 [`template/README.md`](template/README.md)。

领域 agent 不按知识条目或领域持久化为独立实例。每次调用由通用脚手架、调用方选定的领域知识和工具能力共同组装；知识与源码仓库分开存放。agent 通过受限工具按需读取知识和登记项目的源码，不直接遍历或盲读存储目录。源码开发授权、开发 child 分工、受限测试与证据交付入口见 [`template/README.md`](template/README.md#源码开发链路)。
