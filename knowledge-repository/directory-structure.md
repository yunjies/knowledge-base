# 知识库目录结构

本文承载 knowledge-base 工程根的目录地图：目录树列出顶层条目与主要子目录，各目录作用说明其归属边界及读者应进入的文档层级。根 [AGENTS.md](../AGENTS.md) 的「目录结构」节以本文为准；任何影响目录边界或项目内容路径的改动，都须先核对本图并同步更新。

## 目录树

工程根即本仓库工作树，路径均相对工程根解析。

```text
knowledge-base-main/
├── AGENTS.md
├── .gitignore
├── .gitmodules
├── .agents/
│   ├── domain-agents/
│   │   ├── AGENTS.md
│   │   ├── spec.md
│   │   └── template/
│   │       ├── AGENTS.md
│   │       ├── scripts/
│   │       ├── data/
│   │       └── tests/
│   ├── knowledge-repository/
│   └── skills/
├── .github/
│   └── workflows/
├── _lint/
│   ├── _harness/
│   └── hooks/
├── assets/
│   ├── archive/
│   ├── domain-knowledge/
│   ├── inbox/
│   ├── notes/
│   └── projects/
└── knowledge-repository/
    └── notes/
        └── doc-writing-standards/
            └── samples/
```

目录树不列本机缓存、会话临时目录或其他可重建产物。根目录中若新增持久化内容，应同步更新本树及下文职责说明。`_lint/` 的 `test_projects_main_boundary.py` 守护 `main` 上的 `assets/projects/` 边界：目录和 Git 索引仅保留空的 `.gitkeep`；项目仓库只出现在获准承载项目内容的分支。

## 分支归属与变更路径

`main` 是本知识库基础框架的唯一权威分支。基础框架包括根 `AGENTS.md`、`.agents/`、`knowledge-repository/` 与 `_lint/`；这些路径在内容分支上只消费从 `main` 同步来的版本，不在内容分支保留仅该分支存在的基础规范副本。

`assets/` 的基础目录维护也归 `main`：目录骨架、用于说明跨分支准入边界的通用 README 与流程模板可在 `main` 维护。项目清单、领域索引、领域知识、具体项目资料、长期笔记正文及单条收件箱/归档需求记录属于仓库业务内容，必须留在需求方确认的非 `main` 内容分支。文件名或所在目录不能单独决定归属，应按它承载的是通用结构契约还是具体业务事实判定。

需要修改基础框架或 `assets/` 通用骨架时，从最新 `main` 基线建立独立工作分支，只纳入基础框架范围内的变更，并创建 base 为 `main` 的 PR；不得直接在内容分支改写基础规范，也不得把项目业务内容捆入该 PR。需要修改仓库业务内容时，先确认对应的非 `main` 内容分支，再按该目录的准入流程实施，不向 `main` 提交业务内容。

同一需求同时涉及基础框架与仓库业务时，先拆成两个可独立审查的变更：基础框架变更走 `main` PR，业务变更留在确认的内容分支；基础框架 PR 合入后，再将 `main` 同步到内容分支并继续业务工作。若无法证明两部分可独立，暂停并向需求方确认，不以混合 PR 替代边界裁决。

## 各目录作用

- `.agents/domain-agents/` — 通用领域 agent 规范与脚手架；行为规范为 `spec.md`，`template/` 提供每次调用复用的 Host bundle、脚本、通用 schema 与测试，不放领域业务数据或领域实例。
- `.agents/knowledge-repository/` — 跨项目可复用的规则、审核视角与流程；索引为其 `AGENTS.md`。它与工程根 `knowledge-repository/` 按复用范围分工，同一条规则只在一个权威位置承载。
- `.agents/skills/` — 随本工程分发的自定义技能、规范册与技能工具；技能入口为各自的 `SKILL.md`。规范册以此处为权威源，`_lint/` 不扫描此目录。
- `.github/workflows/` — 仓库自动化工作流；文档守护工作流调用 `_lint/` 的运行入口。
- `_lint/` — 本知识库文档的可执行守护，包含判据实现、测试与共享辅助模块；运行方式和守护范围见 [_lint/README.md](../_lint/README.md)。
- `assets/` — 需求记录、归档、长期笔记、领域知识与项目源码仓库的容器；不同子目录的准入边界分别由各自的 `README.md` 声明。
- `assets/domain-knowledge/` — 按领域标识组织的知识、全局 `catalog.json`、各领域 manifest、业务脚手架及领域专属 lint/tests；项目流程归相应领域，DSH 集成部署信息只在项目仓库未承载时写入，通用审核流程不在此复制。
- `assets/inbox/` — 尚待推进的需求，一条需求一份流程记录；骨架见 [template.md](../assets/inbox/template.md)。单条需求记录须保留在需求方确认的非 `main` 记录或内容分支，不进入知识库 `main`。
- `assets/archive/` — 已完成并获需求方同意归档，或经需求方明确取消的需求过程记录；从收件箱整篇移动，不复制。结论按其所属层级归位，不把过程记录当作结论副本。
- `assets/notes/` — 跨会话仍成立且没有更适合承载位置的长期笔记；项目专属流程、可由工程自行取回的事实、执行规范与过程归档均不进入此处。
- `assets/projects/` — 被领域知识引用的独立源码仓库 checkout；仓库根直接以 `assets/projects/<仓库标识>/` 承载。`main` 仅保留空的 `.gitkeep`；项目源码和其测试留在项目仓库。
- `knowledge-repository/` — 本知识库专有的执行规范、边界、操作手册与样本；索引及内容装载时机见 [AGENTS.md](AGENTS.md)。
- `knowledge-repository/notes/` — 场景流程与撰写样本；按实际任务读取对应文档，不因进入目录而全量装载。

## 领域 agent 的阅读顺序

领域 agent 每次调用由通用脚手架、调用方选定的领域知识和授权项目仓库动态组装，不为每条知识创建 agent。主 agent 先确定活动领域及可读仓库，再让领域 agent 按下列顺序取用：

1. 加载通用 agent 指令及当前调用授权范围。
2. 从 `assets/domain-knowledge/<领域标识>/` 读取任务所需的流程、DSH 集成部署索引、版本管理、测试或领域规则资源；审核按需读取 `.agents/knowledge-repository/` 中的通用 audit 流程和视角。
3. 只有需要核对源码实现时，才从登记的项目仓库标识进入 `assets/projects/<仓库标识>/`；源码事实以 checkout 内为准。
4. 从项目源码仓库自己的 `tests/README.md` 取得测试入口和判据。

工具读取知识时接受登记的资源标识；读取源码时接受登记的仓库标识和有界相对路径。模型不得自行构造可交给文件系统的原始路径。领域知识只登记权威源位置，不复制源码或权威文档正文。

## 领域知识与源码仓库的改动入口

任何创建、修改、删除或移动 `assets/domain-knowledge/<领域标识>/` 或 `assets/projects/<仓库标识>/` 下文件的需求，都必须先在 `assets/inbox/` 新建或续办需求，再按[需求流程模板](../assets/inbox/template.md)执行；不得先改后补，小改、知识与源码改动均适用。领域流程和必要的 DSH 集成索引归领域知识目录，源码和项目测试归独立仓库，通用 audit 流程只维护在 `.agents/knowledge-repository/`。Git 提交、同步或 GitHub 操作按[版本管理技能](../.agents/skills/version-management/SKILL.md)执行。
