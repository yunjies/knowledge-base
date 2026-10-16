# AGENTS.md

## 约束

执行期禁令（含不写注释、长期价值优先于成本、不以历史记录替代当前状态、不转述可自行取回的事实）的判据在 [Agent 行为约束](.agents/knowledge-repository/agent-constraints.md)，本节只承载其中的工程落地细则。

- **决策与审核一律走第一性原理 + 辩证**：方案取舍、审核出具的 PASS/FAIL，都必须从可验证的最小事实推出，并写出最强反题。以"现状如此""既有代码这么写""惯例如此""保持一致性"为由的结论一律不成立。展开与判据见[「决策与审核准则」](#决策与审核准则)。
- **取回路径的写法**：凡事实的权威承载在工程本身（源码、配置、目录结构、命令输出）时，写**取回它的路径**而非取值。替代表达按优先级：
  1. **给可复算的命令**：写 `UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest _lint -q`，让读者现取现得；判据写成性质（"全绿且退出码 0"）而非具体条数。宿主机默认缓存目录只读，需显式把缓存落在工作区 `.uv-cache/`。
  2. **指向单一事实源**：写"见 `.gitmodules` 的 `path` 字段"或"以[知识库目录结构](knowledge-repository/directory-structure.md)的目录树为准"，而不是把值抄一份到这里；抄写即制造第二事实源，必然分叉。
  3. **穷举成员**：写"`git ls-files -- assets/projects/` 列出的每个路径"或把成员逐个点名，让读者自己数。
  4. **改用序号**：编号用于引用（`步骤 1`），不承担数量断言。本节是本工程指令文档内取回路径形态的维护处——[文档撰写规范](.agents/skills/doc-writing/reference/doc-writing-constraints.md)的 D-02、D-03 仅就本工程指令文档让位于此，本工程之外的文档仍由该规范判定。上述四类形式中，机器可判定的只有带单位计数与外部记录条目引用，由 `_lint/test_doc_hygiene.py` 守护（含反向样本）；其余形式的合规由审核者按本节判据判定。**该门禁全绿不等于整体合规**，完整守护范围见 [_lint/README.md](_lint/README.md)。
- **对接外部实现的实际形态前先读它的源码**：需要确定宿主或任何外部包的真实形态时——DOM 结构与控件类型、属性名、渲染时机、初始化次序——先读该实现的源码，再动手探测。DSH 随包分发的构建产物与其类型定义就在本机安装目录内，用 `ls $DSH_HOME/web-restart/installs/*/node_modules/@deepseek-ai/` 现取承载当前会话的那次安装；源码给出的是确定性事实，在运行环境里逐次试探付出的是猜测与环境重启的代价。**判据：同一个待确定的形态连续试探两次仍不成立时立即停手去读源码**——第二次落空已经说明猜测的方向错了，此后每次试探都只是同一错误的重复。
- **本次会话的临时文件一律写在 `.sessions/$DSH_SESSION_ID/`**：探针脚本、命令输出、比对基准、中间产物，以及**本次审核工作的全部产出物**（发现清单、合并结果、裁定书、审核报告、验证证据），都落在该目录下，不散在工作区其他位置、也不写进 `knowledge-repository/`。`DSH_SESSION_ID` 由 DSH 注入到每个子进程（形如 `session-<uuid>`），在同一会话的每次调用之间稳定、跨会话唯一，故该目录天然按会话隔离：不同会话互不覆盖，同一会话就地累积。目录不存在时自行建立（`mkdir -p ".sessions/$DSH_SESSION_ID"`）。**其余会话目录一概不访问**：读写、列举、删除与移动一律限于 `.sessions/$DSH_SESSION_ID/` 之内，`.sessions/` 自身只作为该目录的父目录被穿越与创建。**这是工作区内的临时根，不是宿主目录**——`~/.dsh/sessions/` 是 DSH 自己的会话记录存储，插件往里写会污染宿主数据，两者不可混同（用 `ls $DSH_HOME/sessions/` 现取宿主那侧的形态）。判据：临时产物不越出该目录，且 `git status` 保持干净——`.sessions/` 由 `.gitignore` 覆盖。**审核产出物为何不入库**：它是某一轮工作的产物，不是供后续照做的条文；入库会使其与当前基线并行存在，随基线演进静默失配而无门禁能发现。审核中提炼出的**规则**才入库，且按规则自身形态撰写，不携带轮次与证据引用——落点与写法取[决策与审核准则](#决策与审核准则)与[文档撰写规范](.agents/skills/doc-writing/reference/doc-writing-constraints.md)。

### 可达执行路径验证

定义**开始与目标（最终结果）**，通过**无限递归推演林，验证出一条**可达执行路径。

## 决策与审核准则

适用于为非平凡改动作方案取舍，或审核交付并出具结论。其余章节规定"怎么做"，本节规定"凭什么这么定"；本节与本文其他章节冲突时，本节优先。

### 第一性原理：从最小事实出发，不从现状出发

做取舍前先落到不可再分的事实与目标，再从目标往回推方案。三步必须做完：

1. **最小事实**：描述模块脱离现有实现也必须满足的需求。
2. **被推翻的假设**：逐条列出当前实现中只是历史偶然的假设，并给出裁决。
3. **从目标重推**：假设今天从零实现，写出最直接的解法；它与现状的差值就是候选改动。

"现状如此"、"既有代码这么写"、"为了保持一致"、"惯例如此"、"改动面太大"、"现在能跑"或"以后再重构"均不是有效理由；一致性只有在其本身是目标时才成立。

### 辩证：必须写出最强反题

任何方案都须同时给出支持面与反对面；反对面要取最强版本，并归因于设计。固定回答三问：

- **最强反题**：在什么条件下该方案会错？
- **证伪条件**：什么可观测证据出现时判定方案失败？须在动手前写明。
- **弃用代价**：若未来必须推翻方案，代价落在谁身上、有多大？

只列优点的方案按未论证处理，不得进入实施。

### 成本条款：短期成本无否决权

- 本次多花工时、多写代码或多跑测试不构成否决长期正确方案的理由。
- 必须计入长期维护负担、复杂度债务、演进阻力、认知负担与故障半径。
- 裁决顺序为长期正确、长期可演进、短期便捷；若选择短期便利，须记录可偿还的临时债、偿还触发条件与责任人。
- 正在发生的不可逆破坏可先止血；止血仍须标为临时并写明归位计划。

### 留痕：可检查的产出，不是态度

非平凡决策在答复或知识库条目中留下：

```
【事实】脱离现状描述的需求与最小事实
【反题】最强反对意见与证伪条件
【裁决】选定方案、长期视角下的理由、已知代价与偿还计划
```

单文件、无对外契约变化、可一步回滚且不存在多个合理实现方案的小改动，可只留一行裁决；接口与契约、数据模型、构建与挂载、跨半协议及任何审核结论不适用此豁免。

### 审核：结论必须可复算

审核（含自审与交叉复核）不得只给结论，必须同时满足：

- **PASS/FAIL 由事实推出**：列出测试输出、代码路径或实测日志等可验证事实，使结论可复现。
- **正反向检查并重**：既问做对了什么，也问什么情况下会错而未被发现。
- **不得以成本为由放行**：会降低长期正确性的缺陷一律 FAIL，并给出修复方向。
- **不得以措辞让步代替论证**：把断言改成"通常"、"一般"或"建议"不构成修复。
- **禁止空转**：放宽断言、删用例或跳过 E2E 换来的绿灯是 FAIL。
- **默认视角清单**：审核前从[源码审核的默认视角清单](.agents/knowledge-repository/audit-perspectives.md)取本轮启用视角，并逐轮固定。
- **分派形态**：多视角审核会话的分派方式取[审核事实记录流程](.agents/knowledge-repository/notes/audit-record-loop-flow.md)的 `AUDIT_DISPATCH`，本文件不复制其流程细节。

## 目录结构

工程根目录树、各目录职责、资产边界与项目内容阅读顺序见[知识库目录结构](knowledge-repository/directory-structure.md)，本节的目录地图以该文为准。跨项目通用规则与审核流程归 `.agents/knowledge-repository/`；随技能分发的判据册归 `.agents/skills/`；本知识库专有的边界、方法和操作说明归 `knowledge-repository/`。

任何创建、修改、删除或移动 `assets/projects/<项目>/` 文件的需求，都必须先在 `assets/inbox/` 新建或续办需求，并按[需求流程模板](assets/inbox/template.md)执行。项目内容路径与分支阅读顺序见[知识库目录结构](knowledge-repository/directory-structure.md)；需求准入和归档规则见[收件箱 README](assets/inbox/README.md)与[归档 README](assets/archive/README.md)。Git 提交、同步或 GitHub 操作按[版本管理技能](.agents/skills/version-management/SKILL.md)执行。

### 部署与验收

知识库环境部署、验收与排查步骤见[部署说明](knowledge-repository/deploy.md)。

## 测试

目标是证明改动正确并达到相应证据强度。按改动性质选择测试层，不得以成本为由降层或跳过。分层准入、镜像规则、套件可信性与反证纪律见[为项目建立测试套件的流程](knowledge-repository/notes/doc-writing-standards/samples/source-to-tests-flow.md)；按需读取[静态面](knowledge-repository/notes/doc-writing-standards/samples/tests-static-layer.md)、[活体面](knowledge-repository/notes/doc-writing-standards/samples/tests-live-layer.md)或[外部面](knowledge-repository/notes/doc-writing-standards/samples/tests-external-layer.md)。

被收录项目的测试套件只随项目源码维护在项目自己的仓库克隆中；跑法与判据从该项目的 `tests/README.md` 取得，不在本知识库复制项目测试。

## 本知识库的文档守护

`_lint/` 将[文档撰写规范](.agents/skills/doc-writing/reference/doc-writing-constraints.md)与[流程类文档撰写规范](.agents/skills/process-doc-writing/reference/process-doc-writing-constraints.md)的可机械判定部分落成检查；改判据不等于改用例，反之亦然。守护范围与门禁对照见 [_lint/README.md](_lint/README.md)。

运行命令为 `UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest _lint -q`，判据为全绿且退出码为 0。该守护面覆盖知识库文档及 `main` 上 `assets/projects/` 为空这一分支边界；项目实现与项目克隆内文档由项目自身测试，不属于本知识库的守护对象。
