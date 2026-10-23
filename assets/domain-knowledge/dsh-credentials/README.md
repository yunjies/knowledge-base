# dsh-credentials 领域知识索引

本目录承载 dsh-credentials 项目的已实现流程，以及仅属于 DSH profile 集成的部署入口；源码仓库独立位于 [`assets/projects/dsh-credentials/`](../../projects/dsh-credentials/)。领域 agent 先由通用脚手架加载本次调用指令，再按任务读取本目录知识，最后才通过授权工具读取源码。

## 资源入口

- [`data/manifest.json`](data/manifest.json) — 结构化登记资源、源码根、读取范围、操作方式枚举与领域测试类别；工具只按其中的 ID 查询，不从任务措辞猜路径或方法。
- [feature-flow.md](feature-flow.md) — 已实现行为、流程分支和失败出口。
- [deploy.md](deploy.md) — DSH profile 安装入口；项目构建细节转到源码仓库 README，测试入口转到仓库的 `tests/README.md`。
- 通用审核使用[审核事实记录流程](../../../.agents/knowledge-repository/notes/audit-record-loop-flow.md)和[审核视角](../../../.agents/knowledge-repository/audit-perspectives.md)；本领域不重复维护审核流程。
- [领域知识测试](tests/README.md) — 验证本领域索引与 DSH 部署入口，不测试源码实现。
- 源码实现、项目测试和 package 配置 — 以 [`dsh-credentials 源码仓库`](../../projects/dsh-credentials/) 内的文件为准。

资源路径是定位信息，不是源码或权威文档的副本。仓库分支、提交、远端和文件内容按调用时实际 checkout 读取；本索引不固定会漂移的仓库状态。