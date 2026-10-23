# 通用领域 agent 脚手架

本目录提供一个通用协调器 preset 和每次调用临时创建的 worker；不按领域或知识条目创建持久 Agent preset。领域 manifest 与知识资料位于 `assets/domain-knowledge/<领域标识>/`，项目源码 checkout 独立位于 `assets/projects/<仓库标识>/`。

## 通用脚手架清单

| 构件 | 职责 | 必须通过的通用验证 |
| --- | --- | --- |
| `AGENTS.md` | 规定 worker 的知识/源码读取顺序和可调用工具边界 | lint 校验必需指令存在；行为测试验证 worker 不能使用普通文件或 shell 工具绕过范围 |
| `index.js`、`cordis.patch.yml`、`package.json` | 提供协调器 preset、领域目录发现与一次性 worker 启动 | preset 注册、child setup、取消和释放的 Host 行为测试 |
| `scripts/` | 读取 domain manifest、校验 methodId 映射、绑定 child 的知识/源码工具并拒绝越界路径；只通过子进程服务运行固定的领域知识 pytest；将审核发现校验为活动仓库内的有界源码证据 | manifest 解析、统一 lint 契约、固定测试命令/输出字段、路径穿越/符号链接拒绝及 audit 越界证据的行为反例 |
| `data/schema/` | 定义通用领域目录与 manifest 数据形状 | schema 校验及跨资源 ID 引用测试；领域业务字段不得固化在通用 schema |
| `tests/` | 验证协调、调用范围、资源读取与失败封闭 | 通用脚手架测试全绿且退出码为 0 |

## 每次调用

协调器先从 `assets/domain-knowledge/catalog.json` 发现领域和仓库标识，再调用 `run_domain_agent` 创建一次性 worker。调用输入固定活动领域与仓库；创建阶段把对应 manifest 闭包到该 child 的工具 handler，因此 child 不接收可切换领域的路径或 root 参数。worker 默认使用通用 `minimal` preset，领域工具只在 AgentSetup 期间注册到该 child，处置 child 时一并移除。

worker 依照 **agent 指令 → 领域知识 → 项目源码** 的顺序工作。它先用 `get_access_paths` 读取本次范围；有版本管理、部署或测试操作时，先用 `get_operation_method` 查询 manifest 中的精确 `operationId`，再把返回的 `resourceIds` 交给 `get_knowledge_resource`；需要核对实现时，先用 `list_project_files` 定位，再用 `get_project_source` 读取仓库内有界文本。每个工具 handler 都闭包绑定本次 manifest 和仓库，工具参数不含可改变 scope 的 domainId 或仓库 root。

## 领域知识与审核

通用知识类别包括项目与源码定位、已实现流程、DSH 集成部署、版本管理、测试规范、路径授权、操作方式映射和领域业务规则。每个领域维护其 manifest、业务规则、业务脚手架和自己的 lint/tests；资源索引只登记稳定 ID、权威路径、类型和读取限制，不复制来源正文。

所有领域统一使用 `domain-knowledge` 变更类别、`domain-tests` 资源和 `domain-knowledge-validation` / `pytest` 操作映射。领域 agent 必须先从 `get_test_specification` 解析 lint 层与测试资源，再从 `get_operation_method` 解析测试方式并读取测试入口，然后调用 `run_domain_knowledge_lint` 运行固定命令并报告原始输出与退出码。运行器只使用子进程服务，命令固定为 `UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest assets/domain-knowledge/<domain-id>/tests -q`，不接受模型提供的命令或路径；`<domain-id>` 必须取当前调用的领域标识。测试入口登记同一命令和“全绿且退出码为 0”的判据。领域间唯一允许不同的是本领域测试断言和覆盖内容，调用顺序、证据及通过判据一致。通用 manifest 校验会拒绝缺少此测试契约的领域。

审核统一由 coordinator 使用通用 audit 流程；worker 只返回领域证据，不复制 audit workflow 或自判最终 verdict；审核结果通过 `submit_audit_findings` 结构化提交，工具会在活动仓库的读权限内校验并附上行摘录与源版本，不持久化记录。

## 验收边界

通用 tests 必须证明 DA-01 至 DA-13 的公共契约，包括一次性 child scope、确定性 `methodId` 解析、资源/源码读取、范围隔离、失败封闭和破坏性反例。领域 tests 只验证该领域的数据 schema、资源映射、方法枚举与业务边界；不能替代通用工具测试。静态契约测试不能单独证明真实 Host 运行行为，实际加载时还需验证 AgentSetup、tool visibility 和 child teardown。安装或启用 bundle 需要用户明确要求。
