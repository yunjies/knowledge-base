# dsh-cronjob 部署与使用

本文档给出把 `@deepseek-ai/dsh-cronjob` 挂进一个 DSH 进程、并把它用起来的做法。本能力**没有「落地形态」之分**——它不像同目录另外两个 DSH 插件那样在 cordis 与 bundle 之间二选一，而是**两个平面上的两行**，缺一行能力就不完整：

- **Host 平面**挂 `@deepseek-ai/dsh-cronjob`：发布跨会话的 `cronjobs` 服务。**不得置于 agent preset**。
- **agent preset** 挂 `@deepseek-ai/dsh-cronjob/tool-cronjob`：不发布任何服务，消费 `cronjobs` 与 `tools`，注册九个 `cronjob_*` 工具。

工程根在下文记作 `<工程>`，即 `assets/projects/dsh-cronjob/dsh-cronjob/`。命令都在该目录下执行。

## 为什么必须分两行两平面

这不是风格问题，两条拒绝各自有结构性原因，写在同一份示例的注释里（`examples/cordis.overlay.yml`）：

- `@deepseek-ai/dsh-cronjob` 发布的是**进程全局**的 `cronjobs` 服务。一行服务如果散落在某个 preset 里，它会落在 root realm——**第二个挂载同一 preset 的会话就会在服务名上撞车**。挂载期直接拒绝，而不是让这次冲突晚些时候才浮出来。
- `tool-cronjob` **什么都不发布**，只消费 `cronjobs` 与 `tools`。这正是 preset 该贡献的东西。

反过来把 provider 写进 preset，就是在 agent 平面上放第二份服务副本，挂载会失败。

调度、存储与通知都是跨会话关切，这也解释了为什么服务必须只有一份。每次到点或每次被手动触发都重新读取并校验该任务定义，校验不通过就在任何模型调用与子进程之前拒绝本次运行。

## 挂载

### 1. 准备包

本包是 ESM、`private: true`、不随 registry 分发，`main` 与 `exports` 指向 `dist/`。因此**先构建**：

```bash
npm install
npm run build        # tsc -p tsconfig.build.json
```

构建产物为 `dist/index.js`（服务行）与 `dist/cronjob/tool-cronjob.js`（工具行），由 `package.json` 的 `exports` 暴露为 `.` 与 `./tool-cronjob` 两个入口。`files` 字段只收 `dist`。

`engines` 声明 `node >= 22.0.0`；`@deepseek-ai/cordis` 与 `@deepseek-ai/dsh-tools` 是 peerDependencies，由部署侧提供，不由本包自带。

### 2. Host 平面加一行

在宿主组合里加一行，与其它 host 行并列，**一个进程只挂一次**：

```yaml
- id: cronjob
  name: '@deepseek-ai/dsh-cronjob'
  config:
    interpreter: python3
    maxGlobalConcurrency: 4
```

配置项共四个，全部可选，缺省语义在 `src/cronjob/index.ts` 的 `CronjobPluginConfig`：

| 键 | 作用 | 缺省 |
| --- | --- | --- |
| `dshHome` | 存储根 | 由运行期自己的 `DSH_HOME` 解析决定 |
| `interpreter` | pythonScript 节点用的解释器 | 不设，由执行器决定 |
| `maxGlobalConcurrency` | 跨全部作业的有界全局并发 | 不设 |
| `subagentDefaultProvider` | subagent 节点未指名 provider 时用的那个 | 不设 |

服务行的 `inject` 是**空数组**：所有可选协作者都经 `get(name)` 惰性读取并带兜底，缺了某项能力也不会阻塞宿主组合——服务降级，而不是等待。

### 3. agent preset 加一行

在要给这套工具面的那个 preset 里加：

```yaml
- id: tool-cronjob
  name: '@deepseek-ai/dsh-cronjob/tool-cronjob'
```

工具行的 `inject` 是 `["cronjobs", "tools"]`：fiber 等这两个服务就位，`ctx.tools`／`ctx.cronjobs` 的读取才是合法的。

**完整示例取回自克隆内的 `examples/cordis.overlay.yml`**，含两行与逐项注释。该文件是示例，不是可直接追加到某个 profile 的文件——挂到哪一行由部署决定。

## 写一个作业

作业定义是 YAML，一个文件一个作业，落在 `$DSH_HOME/cronjobs/definitions/<cronjobId>.yaml`。**文件名必须与文件内的 `cronjobId` 一致**——不一致会被拒绝，使一个文件无法冒充另一个作业的调度与通知目标。

**示例取回自 `examples/daily-report.yaml`**（含 pythonScript 与 subagent 两种节点、`context`、通知绑定与 misfire 语义的逐项注释）。定义的关键字段：

- `scheduleTime`：标准五段式 cron（分 时 日 月 周）。
- `timeZone`：IANA 时区，**总是显式写出**——定义从不继承环境时区，因此在每台机器上含义相同。
- `bindSessionId`：接收该作业运行通知的会话；省略则只记录运行、不通知任何人。
- `enabled`、`timeoutSeconds`（约束整次运行，不是单个节点）、`maxConcurrentRuns`。
- `misfirePolicy`：**只支持 `skip`**，积压的触发时刻不会被补跑。
- `workflow`：节点序列，`nodeType` 只支持 `pythonScript` 与 `subagent` 两种。
- `scriptPath`：相对于 `$DSH_HOME/cronjobs/artifacts/scripts/`，其 realpath 必须留在该目录内——绝对路径、目录穿越与非 `.py` 后缀都被拒绝。

作业表由**受管 Host 定时器**驱动，不使用系统 `crontab`，也不起脱离进程的守护进程。

## 存储布局

```text
$DSH_HOME/cronjobs/
  definitions/{cronjobId}.yaml
  artifacts/scripts/          # scriptPath 唯一可解析到的根
  runs/{cronjobId}/{runId}/state.json
  runs/{cronjobId}/{runId}/nodes/{nodeId}.json
  logs/{cronjobId}/{timestamp}-{runId}.log
  notifications/{bindSessionId}/{notificationId}.json
  locks/{cronjobId}.lock
```

全部落在 `$DSH_HOME/cronjobs/` 下，不绑定任何具体工作区。备份与清理都以该目录为单位；日志是每次运行一份的 JSON Lines。

## 使用

一个 agent 拿到工具面后，按这个次序用（九个工具的完整说明取回自 `src/cronjob/tools.ts`）：

| 工具 | 什么时候用 |
| --- | --- |
| `cronjob_validate` | 先自查一份定义，不落盘 |
| `cronjob_upsert` | 校验并持久化一份定义，随后对齐定时器 |
| `cronjob_list` | 列出全部作业及其调度、时区、状态与下次触发时刻 |
| `cronjob_get` | 读一个作业 |
| `cronjob_enable` | 排上或撤下调度，保留其历史 |
| `cronjob_delete` | 删除定义；运行历史按保留策略留存 |
| `cronjob_run_now` | 在调度之外手动触发一次 |
| `cronjob_runs` | 读某个作业的近期运行 |
| `cronjob_log` | 读某一次运行的 JSON Lines 日志，有界 |

**改动作业定义后，权威承载是磁盘上的 YAML，不是内存里的定时器**——重建的是定时器，不是去改一份内存副本。因此手工改 YAML 后需要让装载重新发生（重载或 `cronjob_upsert`），不要指望正在运行的进程会自己发现文件变了。

通知只投递到 DSH Session，没有 IM、邮件等其它通道。

## 测试

```bash
npm test         # vitest run
npm run typecheck
```

判据：全绿且退出码 0。用例树与各文件的对象取回自 `tests/`。套件跑在单 fork 里（`vitest.config.ts`），每个套件持有一份私有临时 DSH home，使假时钟与文件系统夹具不互相穿插。

## 未验证面

**这条能力的核心面尚未验证，不要把它当作可用。**

- **没有任何一次真实的进程内定时触发跑通过。** 挂载用例是在真实 Cordis 运行期上、用**定时器替身**组合这两行的；`@cordisjs/plugin-timer` 本体、真实的 subagent provider、以及把结果投递进一个活的 Session，三者都未被实际执行过。**第一次活体挂载就是剩下的验证步骤**，在做完它之前，本能力的调度与通知链只有静态与替身级证据。
- 定义表、调度器、编排器、执行器、日志、通知 outbox、九个已注册工具、以及两行挂到真实 `Context` 上——这些是已实现并有测试的。两者的差别就是「实现了」与「跑通过」的差别。

## 适用范围

- **成立**：宿主进程能满足 `engines`（Node ≥ 22）且能在组合里同时加两行；`$DSH_HOME` 可写（存储、锁与日志都落在那里）；pythonScript 节点要求主机上有可用的解释器（由 `interpreter` 配置项或执行器缺省决定）。
- **失效**：
  - 只想给某个会话加工具、却不动宿主组合时。此时 `cronjobs` 服务无人发布，工具行会在等待中挂起——**两行不可只加一行**。
  - 想按会话隔离调度时。`cronjobs` 是进程全局服务，作业表也是全局一份，不按会话分。
  - 指望积压补跑、或指望通知走 IM／邮件时：`misfirePolicy` 只支持 `skip`，通知只到 DSH Session。
  - 把服务行放进 agent preset 时。第二个挂载该 preset 的会话会在服务名上撞车，挂载被拒绝。
  - 把这件事交给系统 `crontab` 或脱离进程的守护进程时。本能力刻意不使用它们，作业只在 DSH 进程活着的时候由受管定时器驱动。
