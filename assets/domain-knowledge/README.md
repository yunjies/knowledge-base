# 领域知识库

本目录承载可在领域 agent 调用中按需装配的领域知识与业务脚手架；[catalog.json](catalog.json) 登记可用领域，每个领域的 manifest 再登记其资料、源码路径和验收入口。通用 agent 行为与工具契约归[领域 agent 脚手架规范](../../.agents/domain-agents/spec.md)，不在领域目录复制。

## 领域目录约定

每个 `<领域标识>/` 目录只承载该领域的知识资料、结构化索引、业务脚手架和领域专属 lint/tests。项目源码仓库独立位于 `assets/projects/<仓库标识>/`；领域知识仅登记源码位置，不复制源码正文。项目流程和仅属于 DSH 集成的部署说明可由领域知识承载；若这些说明已在项目仓库维护，领域知识只保留定位索引。

审核统一使用[通用 audit 流程](../../.agents/knowledge-repository/notes/audit-record-loop-flow.md)及[审核视角](../../.agents/knowledge-repository/audit-perspectives.md)，领域目录不复制通用审核流程。通用资源类别、调用阅读顺序、工具授权边界及分层验收规则见[领域 agent 脚手架规范](../../.agents/domain-agents/spec.md)。各领域的索引必须把每个资源 ID 指向唯一权威源；本目录不另维护跨领域资源清单副本。

## dsh-credentials 领域

[dsh-credentials 领域索引](dsh-credentials/README.md)给出流程、DSH profile 部署入口、通用 audit 指针及独立源码仓库入口。领域资料按调用需要装配；读取源码时以登记的仓库标识和授权路径为准。