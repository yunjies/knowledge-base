# 通用领域 agent 脚手架

本目录提供一个通用协调器 preset 和每次调用临时创建的 worker；不按领域或知识条目创建持久 Agent preset。领域 manifest 与知识资料位于 `assets/domain-knowledge/<领域标识>/`，项目源码 checkout 独立位于 `assets/projects/<仓库标识>/`。

## 通用脚手架清单

| 构件 | 职责 | 必须通过的通用验证 |
| --- | --- | --- |
| `AGENTS.md` | 规定 worker 的知识/源码读取顺序和可调用工具边界 | lint 校验必需指令存在；行为测试验证 worker 不能使用普通文件或 shell 工具绕过范围 |
| `index.js`、`cordis.patch.yml`、`package.json` | 提供协调器 preset、领域目录发现与一次性 worker 启动 | preset 注册、child setup、取消和释放的 Host 行为测试 |
| `scripts/` | 读取 domain manifest、校验 methodId 映射、绑定 child 的知识/源码工具并拒绝越界路径；领域开发按固定 file grant 和会话文件策略写源码，项目测试只在 full read-only sandbox 中执行 | manifest 解析、授权写入和 CAS、子 agent 生命周期、测试沙箱失败关闭、证据新鲜度、固定领域 lint、路径穿越/符号链接拒绝及 audit 越界证据的行为反例 |
| `data/schema/` | 定义通用领域目录与 manifest 数据形状 | schema 校验及跨资源 ID 引用测试；领域业务字段不得固化在通用 schema |
| `tests/` | 验证协调、调用范围、资源读取与失败封闭 | 通用脚手架测试全绿且退出码为 0 |

## 每次调用

协调器先从 `assets/domain-knowledge/catalog.json` 发现领域和仓库标识，再调用 `run_domain_agent` 创建一次性 worker。调用输入固定活动领域与仓库；创建阶段把对应 manifest 闭包到该 child 的工具 handler，因此 child 不接收可切换领域的路径或 root 参数。worker 默认使用通用 `minimal` preset，领域工具只在 AgentSetup 期间注册到该 child，处置 child 时一并移除。

worker 依照 **agent 指令 → 领域知识 → 项目源码** 的顺序工作。它先用 `get_access_paths` 读取本次范围；有版本管理、部署或测试操作时，先用 `get_operation_method` 查询 manifest 中的精确 `operationId`，再把返回的 `resourceIds` 交给 `get_knowledge_resource`；需要核对实现时，先用 `list_project_files` 定位，再用 `get_project_source` 读取仓库内有界文本。每个工具 handler 都闭包绑定本次 manifest 和仓库，工具参数不含可改变 scope 的 domainId 或仓库 root。

## 领域知识与审核

通用知识类别包括项目与源码定位、已实现流程、DSH 集成部署、版本管理、测试规范、路径授权、操作方式映射和领域业务规则。每个领域维护其 manifest、业务规则、业务脚手架和自己的 lint/tests；资源索引只登记稳定 ID、权威路径、类型和读取限制，不复制来源正文。

所有领域统一使用 `domain-knowledge` 变更类别、`domain-tests` 资源和 `domain-knowledge-validation` / `pytest` 操作映射。领域 agent 必须先从 `get_test_specification` 解析 lint 层与测试资源，再从 `get_operation_method` 解析测试方式并读取测试入口，然后调用 `run_domain_knowledge_lint` 运行固定命令并报告原始输出与退出码。运行器只使用子进程服务，命令固定为 `UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest assets/domain-knowledge/<domain-id>/tests -q`，不接受模型提供的命令或路径；`<domain-id>` 必须取当前调用的领域标识。测试入口登记同一命令和“全绿且退出码为 0”的判据。领域间唯一允许不同的是本领域测试断言和覆盖内容，调用顺序、证据及通过判据一致。通用 manifest 校验会拒绝缺少此测试契约的领域。

审核统一由 coordinator 使用通用 audit 流程；worker 只返回领域证据，不复制 audit workflow 或自判最终 verdict；审核结果通过 `submit_audit_findings` 结构化提交，工具会在活动仓库的读权限内校验并附上行摘录与源版本，不持久化记录。

## 源码开发链路

使用者是协调器和领域维护者。协调器负责需求准入、审批目标分支及复核交付；领域维护者在 [manifest schema](data/schema/domain-manifest.schema.json) 的仓库记录内配置 `development`，由它声明写模式、变更类别、操作映射和固定测试 argv。没有此登记的仓库保持只读。测试资源 `project-tests` 必须指向该仓库的 `tests/README.md`，并同时被开发操作及变更类别引用；调用者不从自然语言推断执行命令。

协调器给 `run_domain_agent` 增加 `development` 参数时，以现存收件箱记录文件名去掉 `.md` 作为 `requestId`，以仓库相对精确路径数组作为 `writeFiles`。授权只包含现存文件的完整替换；新增文件、删除、移动、领域知识、manifest、提交与部署不在授权内。每次写入都重读主会话的 sandbox policy，并把文件系统写策略缩窄到该目标的规范路径；文件系统沙箱在原子发布前重新解析目标并比较该精确根，减少外部符号链接替换造成的越界。此策略约束最终目标；底层原子写实现可在目标同目录创建短暂 staging 文件/目录，属于 Host 文件服务自身的实现副作用，不把它声明为目标级拒绝。MVP 只允许版本守卫的现存文件替换；新建文件需要 Host 提供原子 no-follow 创建能力，在此之前封闭拒绝。工具验证需求文件存在不等于验证流程审批，需求准入及分支审批仍由协调器完成，模型不得把一个现存需求 ID 视为自动批准。

领域 worker 通过 `run_domain_developer` 把方案、最强反题和验收标准交给独立开发 child。开发 child 用 `read_development_file` 观察文本或不存在状态，再用 `write_project_file` 原样提交版本。领域 worker 没有直接写工具，开发 child 没有委派和测试工具；两者均不能调用普通文件或 shell 工具。领域 worker 用 `get_development_change` 复核前后文本，先用 `prepare_project_tests` 读取登记的测试标准、argv 与测试入口正文，再以 `run_project_tests` 取得实测证据，通过后调用 `submit_domain_acceptance`。测试入口在准备与运行之间版本变化时，工具拒绝继续。协调器读取返回的 `development` 证据，不用 child 的 `completed` 代替领域验收。

项目测试入口须能在 200 行与 50000 UTF-8 字节内完整展示给领域 worker。项目测试依赖 Host 的 filesystem、subprocess、sandbox 与 sandboxPolicy 服务。运行器只在 `full` 的 `read-only` 文件沙箱下启动登记 argv；无法满足时失败封闭。测试不继承凭据环境，仍不提供网络或机密读取隔离。需要在源码树生成构建产物的测试不适用此 MVP，应返回未验收，不能偷偷改成 workspace-write 或跳过测试。支持范围是可在只读源码下运行测试的项目；测试命令与项目判据由领域登记维护，不在通用脚手架复制项目说明。

测试证据绑定可读项目文件的版本与内容摘要，覆盖读取策略内的文件集合；读取范围外依赖、外部服务及测试判据的充分性仍需领域 agent 报告和协调器审核。摘要有容量上限，超限即拒绝验收，不返回不完整摘要。测试前后或验收前输入变化会使证据失效。开发调用对同一规范化仓库根互斥，但不宣称阻止外部编辑器；路径解析和版本守卫也不是跨进程文件系统事务。当前 Host 文件沙箱按最终 canonical target 执行 containment；它未提供 openat/no-follow 目录句柄，不能宣称抵御同一主机上可并发改写目录结构的恶意进程。

部分写入、失败和取消均保留逐文件副作用，不自动回滚以免覆盖用户编辑。调用返回时工具与 child 被释放；不提供会话恢复后的续写能力。协调器必须先复核副作用，再发起新调用。授权期间主会话切换为只读时，后续写入必须拒绝。

运行通用脚手架测试：`node --test .agents/domain-agents/template/tests/*.test.js`；运行知识库门禁：`UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest _lint -q`。两者以全绿且退出码为 0 为通过判据；真实 Host 挂载与后端隔离仍按下一节单独验收。

## 验收边界

通用 tests 必须证明 DA-01 至 DA-13 的公共契约，包括一次性 child scope、确定性 `methodId` 解析、资源/源码读取、范围隔离、失败封闭和破坏性反例。领域 tests 只验证该领域的数据 schema、资源映射、方法枚举与业务边界；不能替代通用工具测试。静态契约测试不能单独证明真实 Host 运行行为，实际加载时还需验证 AgentSetup、tool visibility 和 child teardown。安装或启用 bundle 需要用户明确要求。
