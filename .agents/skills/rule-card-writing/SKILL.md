---
name: rule-card-writing
description: 撰写、修订或审阅规则卡片的字段与子标签时使用。给出字段全集、子标签登记、判定真值源与字段规则的可执行工序，并指向权威源的原文与核验方式。只管单条卡片的字段结构。把卡片组成册取 spec-book-writing，正文行文表述取 doc-writing。
whenToUse: 撰写、修订或审阅以规则卡片承载单条规则的文档、新增或调整某条卡片的字段与子标签时。
---

# 规则卡片撰写工序

本 skill 的工序由一条约束链推出：判定只能读若干字段，故凡要生效的语义都必须落在这些字段里，而字段的合法集合是封闭登记的。执行时自上而下走。

## 判据源与范围

本 skill 的按条判据以全文唯一权威源为准：[规则卡片撰写规范](reference/rule-card-writing-constraints.md)——随本 skill 分发，本 skill 不复制其条款。本 skill 工序中的 `§n` 指该册的章节号，`F-nn` 指 [§2](reference/rule-card-writing-constraints.md#2-字段规则定义) 内**字段定义条的章节序号**——它不是规则卡片 ID，不得出现在条目标题行上，也不得被 `overrides[]`／`external_exceptions[]` 引用（见规范 [F-01](reference/rule-card-writing-constraints.md#f-01-id--规则标识)）。规则卡片的 ID 形如 `R-014`，与 `F-nn` 分属两个命名空间。

本 skill 管**单条卡片的字段结构**。**把卡片组成规范册**归[规范册撰写工序](../spec-book-writing/SKILL.md)，其判据源为[规范册撰写规范](../spec-book-writing/reference/spec-book-writing-constraints.md)——册正文的构成、新条目准入、册级取用范围、条目落笔次序与缺口登记取它。落在卡片字段行里的文本，其**行文表述**取[文档撰写 SKILL](../doc-writing/SKILL.md)——含字段值、子标签行与列表的写法。**执行者不得越过判据源另立判据**：本 skill 只编排落笔次序，工序中不新增判据；规范未覆盖且册层规范 §0.1 亦未登记的情形，须显式报出该情形与其归属，不得就地发明写法、不得把既有断言改写成"通常""建议"一类措辞来放行。

## 路由表

判据源较长（700 余行）。**按任务只取回所需章节**，下列链接直达规范内的对应位置（`规范` 指 `reference/rule-card-writing-constraints.md`）：

| 你要做的事 | 读规范哪几节 |
|---|---|
| 写一张完整的新卡片 | [§1 模板](reference/rule-card-writing-constraints.md#1-规则卡片模板) → 所涉字段的 [§2](reference/rule-card-writing-constraints.md#2-字段规则定义) 条目 → [§0.1](reference/rule-card-writing-constraints.md#01-标签--字段对照)／[§0.2](reference/rule-card-writing-constraints.md#02-子标签登记封闭集合) |
| 判断某字段/子标签是否参与判定、判定什么 | [§0.5](reference/rule-card-writing-constraints.md#05-判定真值源越界即失效)（唯一真值源表） |
| 查某字段的登记、基数、必填性 | [§0.1](reference/rule-card-writing-constraints.md#01-标签--字段对照)（顶层字段）／[§0.2](reference/rule-card-writing-constraints.md#02-子标签登记封闭集合)（子标签）／[§0.3](reference/rule-card-writing-constraints.md#03-文档层定义的文本形态)（文档层定义项） |
| 写 `scope` 的布尔组合 | [F-06](reference/rule-card-writing-constraints.md#f-06-scope--适用域与前置状态) + [§0.2](reference/rule-card-writing-constraints.md#02-子标签登记封闭集合) 的「连接」行 |
| 写 `action` 的形态（六选一） | [F-07](reference/rule-card-writing-constraints.md#f-07-action--动作) |
| 写产出物与判定维度 | [F-08](reference/rule-card-writing-constraints.md#f-08-artifact--可观测产出物) + [§0.2](reference/rule-card-writing-constraints.md#02-子标签登记封闭集合) |
| 处理覆盖关系 | [F-10](reference/rule-card-writing-constraints.md#f-10-overridable--可覆盖性)／[F-11](reference/rule-card-writing-constraints.md#f-11-coverage_point--覆盖点)／[F-12](reference/rule-card-writing-constraints.md#f-12-overrides--正向覆盖指针) |
| 处理失败行为与外部依赖 | [F-14](reference/rule-card-writing-constraints.md#f-14-failure_behavior--失败行为)／[F-15](reference/rule-card-writing-constraints.md#f-15-dependencies--依赖指针) |
| 查结构约束、引用完整性、计数上限 | [§3](reference/rule-card-writing-constraints.md#3-结构约束汇总) |
| 查哪些写法被禁止 | [§4](reference/rule-card-writing-constraints.md#4-禁止字段与禁止形态) |
| 找一条可照抄的完整卡片 | [附录](reference/rule-card-writing-constraints.md#附-规范化完整示例) |
| 查规范自身的登记是否自洽 | [§0.5](reference/rule-card-writing-constraints.md#05-判定真值源越界即失效) 的完备性义务 + `scripts/verify.js` |

**字段 → 条目编号对照**（规范 [§2](reference/rule-card-writing-constraints.md#2-字段规则定义) 内每条以其字段名为标题）：

`id`→F-01、`title`→F-02、`modality`→F-03、`actor`→F-04、`when`→F-05、`scope`→F-06、`action`→F-07、`artifact`→F-08、`external_exceptions`→F-09、`overridable`→F-10、`coverage_point`→F-11、`overrides`→F-12、`layer`→F-13、`failure_behavior`→F-14、`dependencies`→F-15、`why`→F-16、`examples`→F-17。

## 工序

1. **定判定输入**：先写出生效条件、强度、行为、完成判据四者的取值，再落笔成字段。标题、层标签、注释与一切结构构件不参与判定，写在其中的限制不具约束力。
2. **查登记**：按下列次序逐个核对，缺登记者先补——顶层字段查规范 §0.1；子标签查 §0.2；文档层定义项查 §0.3。**覆盖点行是卡片自己的字段**，被覆盖方在卡片内嵌写（见规范 `F-11`），不在别处另立。**卡片层自身判不了的情形不必在此登记**：本册不设缺口登记，须把该情形与其归属**显式报出**交回使用者，不得就地发明写法。**册层的**缺口才登记在册层规范 `§0.1`（`S-04`），且仅限"落在该册覆盖范围内"的情形。
3. **填必填核心**：`id`、`action`、`artifact`——三者缺失即不合法。`id` 形态须匹配规范 F-01 的正则 `^[A-Z][A-Z0-9]{0,7}-[0-9]{2,4}$`（前缀为 1–8 位大写字母或数字、且以字母开头，`-` 后为 2–4 位数字）；**前缀不设登记表**，由承载文档自己的条目标题行给出、全文一致即可；引用完整性只判形态与文档内唯一。适用性槽组（`when`／`scope`）不属必填核心：二者各有缺省语义，用不上即整行不出现。
4. **逐字段撰写**：按规范 §2 的 F-01 至 F-17；`scope` 与 `action` 先选 `form`，再写该形态专属字段，非当前形态的字段不出现。
5. **拆判定维度**：`artifact` 的可机械求值部分写 `判定口径`，不可机械求值部分写 `语义判据`，不判定的对象写 `判定边界` 并点名承担者。
6. **收尾**：条件不成立的行整行删除；按规范 §3 自查引用完整性与计数上限。
7. **核验**：分两步，两者的绿灯**不可互相替代**。
   - **验所写卡片**：以规范 §1 的模板与被撰文档既有卡片的字段行互为对照，逐字段核规范 §2 该字段条目；**并跑本 skill 的卡片校验器**：`node scripts/check-card.js <被撰文档路径>`（退出码 0 为通过）。它从规范文本提取判据，机械核这几项：卡片标题行的 `id` 形态、必填核心齐备、每个标签与子标签都在 §0.1／§0.2／§0.3 的登记内、`产出物` 有「判定口径」或「语义判据」。**它的覆盖仅限上述可机械求值项**——`语义判据`、`判定边界` 的承担者、覆盖关系等语义判据不在其内，退出码 0 不等于卡片正确，仍须逐条核规范 §2；被撰文档自带校验命令时也跑该命令。
   - **验规范自身**：本 skill 的 `SKILL.md`、`reference/`、`scripts/` 所在目录即**技能根**。在技能根下跑 `node scripts/verify.js`（退出码 0 为通过），或跑 `node --test` 执行本 skill 的用例。**该脚本只校验规范文件自身**的三类登记与判定真值源的完备性及互斥性，**不读、也不校验你所写的卡片**：它退出码 0 只说明规范未漂移，不说明卡片正确。改动规范 §0.1／§0.2／§0.3 或 §0.5 后**必须**跑它。

## 高频改写

- 意图级表述、程度副词、工具与参数细节改写为工具无关的具体动作。
- 执行时序从适用性槽移入 `action`，并把 `ordered_steps` 限定在步间存在数据依赖时。
- 行为写在 `action`，完成判据写在 `artifact` 的「判定口径」／「语义判据」，格式依据写在 `artifact` 的「形态」，三者不互串。
- 字段值内自造的分隔记号改写为具名子标签。
- 本地可判定的例外改写为 `scope` 的原子谓词取反，不写成 `外部例外`。
- 覆盖只写正向指针，被覆盖方内嵌 `覆盖点`。

## 自检

**本清单是高频错项摘要，不是判据全集**；判据全集在 `reference/` 规范内，逐条核对时以该册各条自身的判定口径与语义判据为准。

- 每个字段名与子标签名都能在规范 §0.1／§0.2 解析到，每个文档层定义项都能在 §0.3 解析到；字段值内不出现 `operators` 一类未登记的 ASCII 标识符。
- `id` 形态匹配规范 F-01 的正则，前缀全文档一致，且在该文档内唯一。
- 必填核心齐备；「判定口径」与「语义判据」至少出现其一。
- 完成判据写在 `artifact` 内，未在 `动作` 值或 `产出物` 值里自造分隔记号；`action` 值内不含"判定口径／语义判据"意义上的判据。
- 「必须／不得／should」不出现在 `why:nb` 内；`why:nb` 仅在 `scope` 值含开放记号时出现。
