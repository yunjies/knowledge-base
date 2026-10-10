# 需求：按 review-guide 评审 dsh-credentials 源码并闭合证据

```yaml
target: assets/projects/dsh-credentials/dsh-credentials/src/、assets/projects/dsh-credentials/dsh-credentials/tests/、assets/projects/dsh-credentials/dsh-credentials/dist/bundle/、assets/projects/dsh-credentials/dsh-credentials/reviews/ 与 assets/projects/dsh-credentials/feature-flow.md
output: assets/projects/dsh-credentials/dsh-credentials/src/、assets/projects/dsh-credentials/dsh-credentials/tests/、assets/projects/dsh-credentials/dsh-credentials/dist/bundle/、assets/projects/dsh-credentials/dsh-credentials/reviews/review-20261010-010816.md 与 assets/projects/dsh-credentials/feature-flow.md
prompt:
  - dsh-credentials根据reviewguide进行review
```

本需求从 dsh-credentials 的只读源码评审开始，按 review-guide 覆盖其规定的六个维度，并仅对可由源码定位且经测试验证的缺陷执行红测、修复、绿测、破坏性反证、恢复复测闭环，最终由独立验收者核对完整改动并形成评审报告。

## 需求澄清

### 澄清记录

无——review-guide 已规定评审范围、六个维度、事实准入、测试与修复闭环、报告结构；需求只要求按该指南执行，无额外模糊点需要裁决。

### 验收锚点

- A1：六个规定的评审维度均有独立评审者提交结果，且评审阶段没有读取 `src/` 之外的工程材料或运行命令。
- A2：进入事实清单的问题均有源码触发条件、可观察错误结果、预期行为、对应测试及完整的修复前红／修复后绿／破坏后红／恢复后绿证据；不能闭环的候选只列入未验证面并说明原因。
- A3：报告字段、运行入口、修复与测试对应关系、破坏与恢复核验及未覆盖范围均可从报告复算。
- A4：独立验收逐项比对需求和完整 diff，确认无漏项且无需求外改动。

### 范围边界

- 不做：评审 `src/` 以外的产品代码、配置或文档；扩展 review-guide 之外的审查范围；提交、推送、部署或触及生产环境。
- 不做：把未经完整测试闭环的候选记为已验证事实。

## 主流程图

```mermaid
flowchart TB
  START(["评审范围就位"]) --> REVIEW["独立源码评审"]
  REVIEW --> REVIEW_GATE{"有经源码汇总核实的候选吗"}
  REVIEW_GATE -->|"无候选"| REPORT["报告阶段"]
  REVIEW_GATE -->|"有候选"| TEST["红测与验证闭环"]
  TEST --> TEST_GATE{"当前证据到达哪个阶段门"}
  TEST_GATE -->|"修复前红测确认"| DEVELOP["独立修复源码"]
  DEVELOP -->|"修复交付，继续验证"| TEST
  TEST_GATE -->|"闭环全绿"| REPORT
  TEST_GATE -->|"无法安全继续"| BLOCKED(["阻塞：保留未验证事实"])
  BLOCKED --> REPORT
  REPORT --> ACCEPT["独立验收"]
  ACCEPT --> ACCEPT_GATE{"报告与需求逐项吻合吗"}
  ACCEPT_GATE -->|"是"| DONE(["评审报告完成"])
  ACCEPT_GATE -->|"否"| REPORT
  ACCEPT_GATE -->|"需求方终止未完成评审"| CANCELLED(["需求方明确终止"])

  classDef todo fill:#f9d71c,stroke:#8a6d00,color:#000
  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff
  classDef stuck fill:#d73a49,stroke:#7d1220,color:#fff
  class START,REVIEW,REVIEW_GATE,DEVELOP done
  class TEST,TEST_GATE,REPORT,BLOCKED,ACCEPT,ACCEPT_GATE stuck
  class DONE todo
  class CANCELLED done
```

## START

评审作业书与范围已就位；六个独立维度、只读源码的阶段边界和闭环要求均明确。本节点不出分支。

**输入**

- `REVIEW_SPEC`：本需求与验收锚点；来源为本文件。

**输出**

- `REVIEW_SPEC`：评审规格；去向为 `REVIEW`。

## REVIEW

六个维度分别由全新的一次性 subagent 执行；评审者只读相关 `src/` 源码，不读测试或其它材料，不运行命令、不修改文件。另一名全新 subagent 仅按候选引用位置核实候选并按根因去重。

**输入**

- `REVIEW_SPEC`：评审规格；来源为 `START`。

**输出**

- `CANDIDATES`：独立评审候选及来源；去向为 `REVIEW_GATE`。

## REVIEW_GATE

只保留能够从被引用源码说明触发条件、可观察错误结果与预期行为的候选；其余候选不得作为事实进入报告。没有保留候选时直接形成无缺陷评审报告。

**输入**

- `CANDIDATES`：独立评审候选；来源为 `REVIEW`。

**输出**

- `VALIDATED_CANDIDATES`：经源码核实的问题；去向为 `TEST`。
- `NO_CANDIDATE`：无经核实候选的结果；去向为 `REPORT`。

## TEST

每项候选由独立一次性 subagent 检查现有覆盖或新增直接测试，并在修复前证明测试因目标错误行为失败。初始红测确认后，测试阶段把证据交给 `DEVELOP`；修复后由新的测试 subagent 验证绿测，再由新的 subagent 做可恢复的本地破坏性反证，最后由另一名 subagent 恢复并复测。每次失败都保留证据并回到相应阶段，无法准确恢复时停止。

**输入**

- `VALIDATED_CANDIDATES`：经源码核实的问题；来源为 `REVIEW_GATE`。
- `PATCH`：独立修复者交付的源码修复；来源为 `DEVELOP`。

**输出**

- `RED_EVIDENCE`：修复前因目标错误行为失败的直接测试证据；去向为 `TEST_GATE`。
- `CLOSURE_EVIDENCE`：修复后绿测、破坏性反证及恢复复测证据；去向为 `TEST_GATE`。
- `UNVERIFIED`：无法安全继续的候选及阻因；去向为 `TEST_GATE`。

## DEVELOP

针对已由修复前红测证实的问题，由一个独立的一次性 subagent 只改对应源码，不改证据测试、不夹带无关改动。修复者不负责测试验收。

**输入**

- `RED_EVIDENCE`：修复前失败的目标测试；来源为 `TEST_GATE`。
- `VALIDATED_CANDIDATES`：对应的源码问题事实；来源为 `REVIEW_GATE`。

**输出**

- `PATCH`：最小源码修复；去向为 `TEST`。

## TEST_GATE

初始红测须因目标行为失败才允许进入修复；修复后的相关测试全绿、破坏修复后目标断言转红、恢复后再次全绿且所有命令退出码为 0，才进入归档。无法安全或准确恢复的候选留在未验证面。

**输入**

- `RED_EVIDENCE`：修复前测试证据；来源为 `TEST`。
- `CLOSURE_EVIDENCE`：绿测、反证、恢复复测证据；来源为 `TEST`。
- `UNVERIFIED`：闭环阻因；来源为 `TEST`。

**输出**

- `RED_EVIDENCE`：足以进入修复的失败证据；去向为 `DEVELOP`。
- `VERIFIED_FACTS`：完整闭环的问题事实；去向为 `REPORT`。
- `UNVERIFIED`：未验证面；去向为 `BLOCKED`。

## REPORT

由独立一次性 subagent 按 review-guide 规定的字段与结构撰写报告，只登记具有完整闭环证据的问题；记录测试运行入口、对应关系、破坏方式、恢复核验与未覆盖范围。报告位置为项目仓库 `reviews/`。

**输入**

- `VERIFIED_FACTS`：完整闭环的问题事实；来源为 `TEST_GATE`。
- `UNVERIFIED`：未验证面；来源为 `BLOCKED`。
- `NO_CANDIDATE`：无候选结果（若适用）；来源为 `REVIEW_GATE`。
- `ACCEPT_FAILURE`：验收发现的遗漏或越界项；来源为 `ACCEPT_GATE`。

**输出**

- `REVIEW_REPORT`：评审报告；去向为 `ACCEPT`。

## ACCEPT

独立一次性验收者核对完整 diff 与本文件的提示词、验收锚点和范围边界，逐项检查评审覆盖、事实准入、闭环证据和报告字段。验收者不修正产物；发现遗漏或越界时交回报告阶段处置。

**输入**

- `REVIEW_REPORT`：评审报告与本次完整改动；来源为 `REPORT`。

**输出**

- `COMPARISON`：评审覆盖、事实证据与报告内容逐项比对结果；去向为 `ACCEPT_GATE`。

## ACCEPT_GATE

独立验收阶段按验收锚点和范围边界逐项判断评审与报告是否完整。任何遗漏或需求外改动均不通过。

**输入**

- `COMPARISON`：逐项比对结果；来源为 `ACCEPT`。

**输出**

- `ACCEPTED`：逐项吻合的验收结论；去向为 `DONE`。
- `ACCEPT_FAILURE`：遗漏或越界项；去向为 `REPORT`。

## CANCELLED

需求方明确终止本评审流程并要求归档。现有报告总体仍为 INCOMPLETE；终止不等于验收通过，也不改变报告结论。

**输入**

- `CANCELLATION`：需求方明确终止决定；来源为需求方当前指示。

**输出**

- 无。

## DONE

评审报告已通过独立验收。本需求流程文档不因验收通过自动归档；须待需求方明确同意后再移动归档。

**输入**

- `ACCEPTED`：独立验收通过；来源为 `ACCEPT_GATE`。

**输出**

- 无。

## BLOCKED

无法准确恢复破坏性反证造成的状态，或环境阻碍导致闭环无法继续时停止，不把候选记为已验证事实，并在报告未验证面列明阻因。

**输入**

- `UNVERIFIED`：未验证候选及阻因；来源为 `TEST_GATE`。

**输出**

- `UNVERIFIED`：未验证面与阻因；去向为 `REPORT`。

## 状态配色

前一版独立验收拒绝交付：A1 因 Lead 在六位评审完成前读过 `tests/README.md` 不符合原锚点；A2/A3 因报告逐阶段证据不可复算而失败；A4 对起始已 dirty、无基线快照的 `targets-rebind-probe.test.ts` 无法逐字节划分。需求方明确不豁免 A1 或 A4，严格锚点不变，故仍不能接受交付。后续证据复核发现 A–F、U4/U5、U8、U9 原列闭环的阶段摘要缺逐项命令、退出码、目标输出或精确恢复核验；当前[评审报告](../projects/dsh-credentials/dsh-credentials/reviews/review-20261010-010816.md)将 A–E、U1–U6、U9 保留为未验证候选并列具体缺口，U7、U8与F则分别基于受控重建的红／绿／破坏红／恢复绿列为单项闭环事实。U7的完整四阶段命令、退出码、目标输出、hash及恢复纠正记录见报告U7事实项；它证明当前错误传播契约的因果，不证明历史原始源码来源或完整安装覆盖。U8独立复核确认标准patch可复算，Lead实跑 `git apply --check -` exit 0且未改源文件；F四阶段同样以受控read/edit变异证明现时因果，不证明历史原始源码来源。F字符计数 mutant 的目标断言实际返回200、预期413，恢复后目标测试通过；U8红测首断言失败后续 removal-attempt 断言未执行。最终独立审计认为F的结构与四阶段证据合格、无必须修订；U7独立复核确认本轮四阶段事实及全局状态一致、无必须修订，但不代表整份需求验收通过；整体仍为INCOMPLETE。除U7、U8与F外，历史阶段证据仍缺逐项原始记录；U6部署授权与可达性未知；原始候选清单未归档、覆盖非穷尽；E/U9受起始dirty测试无快照限制。报告总体仍为 INCOMPLETE。A1/A4不豁免，需求未重新验收、未归档。U7、U8与F源码均已精确恢复到各自受控周期known-good hash。Bundle与Cordis构建通过；全量 `npm test` 为392 passed、34 failed（38 files），退出码1；_lint为47 passed。未执行真实SSH/browser E2E，未触及生产，未commit、push或deploy。需求方于 2026-10-10 明确终止本评审流程并要求归档；报告仍为 INCOMPLETE，A1/A4 未重新验收，未验证候选保持原状。终止不构成 PASS。绿色表示已执行且有证据确认，黄色表示尚待执行，红色表示阻塞需外部协助；图中每个节点以颜色单独表示状态。
