# knowledge-repository 索引

本目录承载本知识库专有的执行规范、目录边界与撰写样本；条目脱离本知识库即无所指。本文档是索引层，说明各文档的性质与加载时机；不要因为进入本目录就通读全部内容。

跨项目可复用的规则与流程住 [.agents/knowledge-repository/](../.agents/knowledge-repository/AGENTS.md)，随 `.agents/` 移植；本目录只收本知识库专有内容。两处按复用范围分工，同一条规则只保留一份。

## 文档一览与加载时机

| 文档 | 性质 | 何时读 |
|---|---|---|
| [directory-structure.md](directory-structure.md) | 地图 | 需要确认工程根目录、资产目录边界或项目内容阅读顺序时；根 [AGENTS.md](../AGENTS.md)「目录结构」节的完整内容以此为准 |
| [domain-agent-architecture.md](domain-agent-architecture.md) | 架构提案 | 设计领域知识库配置、领域 agent 工具边界或 KB agent 编排时 |
| [deploy.md](deploy.md) | 操作手册 | 执行知识库环境部署、验收与排查时 |
| [notes/doc-writing-standards/samples/](notes/doc-writing-standards/samples/) | 样本 | 依开发交付形态或测试层选择对应流程样本时 |

## 边界与修订

本目录不复制 `.agents/skills/*/reference/` 的规范条款；随 skill 分发的判据以 `.agents/skills/` 为权威源。新增或修订本目录文档时，先按根 [AGENTS.md](../AGENTS.md)「目录结构」判断内容归属，再按对应的撰写技能核对形态。
