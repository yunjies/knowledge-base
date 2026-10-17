# 知识库目录结构

本文档承载 knowledge-base 工程根的目录地图：目录树列出顶层条目与主要子目录，各目录作用说明其归属边界及读者应进入的文档层级。根 [AGENTS.md](../AGENTS.md) 的「目录结构」节以本文为准；任何影响目录边界或项目内容路径的改动，都须先核对本图并同步更新。

## 目录树

工程根即本仓库工作树，路径均相对工程根解析。

```
knowledge-base-main/
├── AGENTS.md
├── .gitignore
├── .gitmodules
├── .agents/
│   ├── knowledge-repository/
│   └── skills/
├── .github/
│   └── workflows/
├── _lint/
│   ├── _harness/
│   └── hooks/
├── assets/
│   ├── archive/
│   ├── domains/
│   ├── inbox/
│   ├── notes/
│   └── projects/
└── knowledge-repository/
    ├── domain-agent-architecture.md
    └── notes/
        └── doc-writing-standards/
            └── samples/
```

目录树不列本机缓存、会话临时目录或其他可重建产物。根目录中若新增持久化内容，应同步更新本树及下文职责说明。`_lint/` 的 `test_projects_main_boundary.py` 守护 `main` 上的 `assets/projects/` 边界：目录和 Git 索引仅保留空的 `.gitkeep`；项目实际内容不进入知识库 `main`。

## 各目录作用

- `.agents/knowledge-repository/` — 跨项目可复用的规则、审核视角与流程；索引为其 `AGENTS.md`。它与工程根 `knowledge-repository/` 按复用范围分工，同一条规则只在一个权威位置承载。
- `.agents/skills/` — 随本工程分发的自定义技能、规范册与技能工具；技能入口为各自的 `SKILL.md`。规范册以此处为权威源，`_lint/` 不扫描此目录。
- `.github/workflows/` — 仓库自动化工作流；文档守护工作流调用 `_lint/` 的运行入口。
- `_lint/` — 本知识库文档的可执行守护，包含判据实现、测试与共享辅助模块；运行方式和守护范围见 [_lint/README.md](../_lint/README.md)。
- `assets/` — 需求记录、归档、长期笔记、领域知识库与项目源码仓库的容器。不同子目录的准入边界分别由各自的 `README.md` 声明。
- `assets/inbox/` — 尚待推进的需求，一条需求一份流程记录；骨架见 [template.md](../assets/inbox/template.md)。单条需求记录须保留在需求方确认的非 `main` 记录或内容分支，不进入知识库 `main`。
- `assets/archive/` — 已完成并获需求方同意归档，或经需求方明确取消的需求过程记录；从收件箱整篇移动，不复制。结论按其所属层级归位，不把过程记录当作结论副本。
- `assets/domains/` — 领域知识库的权威存储位置，承载领域配置、知识正文、领域流程与工具脚本；领域层级和配置契约见[领域 agent 架构](domain-agent-architecture.md)。
- `assets/notes/` — 跨会话仍成立且没有更适合承载位置的长期笔记；项目专属知识与流程、可由工程自行取回的事实、执行规范与过程归档均不进入此处。
- `assets/projects/` — 仅承载项目源码仓库克隆，不承载领域配置、知识正文、流程说明、部署说明或工具脚本。`main` 仅保留空的 `.gitkeep`；项目源码仓库留在 `duoduo` 内容分支。每个仓库克隆直接位于 `assets/projects/<repository>/`，所属领域与项目的对应关系由领域配置声明。
- `knowledge-repository/` — 本知识库专有的执行规范、边界、操作手册与样本；索引及内容装载时机见 [AGENTS.md](AGENTS.md)。
- `knowledge-repository/notes/` — 场景流程与撰写样本；按实际任务读取对应文档，不因进入目录而全量装载。

## 领域知识与项目源码的阅读顺序

读取某项目的领域知识或源码时，先从 `assets/domains/` 找到负责该项目的领域配置，再按配置中的入口读取知识与流程；项目源码克隆只提供源码事实，项目流程与部署说明由领域知识库承载。

1. 读领域配置，确认领域标识、知识入口、流程入口、工具入口与项目源码引用。
2. 读领域知识入口，获取领域术语、约束与业务知识。
3. 读领域流程入口，获取开发、部署、运维、验证与失败恢复约定。
4. 再读取配置引用的 `assets/projects/<repository>/` 源码仓库；源码事实以克隆内为准。
5. 从源码仓库内的 `tests/README.md` 取得该项目测试入口和判据。
6. 更新项目流程或部署说明时，更新所属领域知识库，不在 `assets/projects/` 或 `assets/notes/` 复制。

## 项目源码仓库的改动入口

任何创建、修改、删除或移动 `assets/projects/<repository>/` 下文件的需求，都必须先在 `assets/inbox/` 新建或续办需求，再按[需求流程模板](../assets/inbox/template.md)执行；不得先改后补，小改、源码与仓库元数据改动均适用。项目分支确认、开发与验收步骤只由需求模板承载；Git 提交、同步或 GitHub 操作按[版本管理技能](../.agents/skills/version-management/SKILL.md)执行。
