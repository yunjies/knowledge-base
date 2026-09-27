# dsh-credentials 部署与使用

本文档给出把 `dsh-credentials` 装进一个 DSH 部署、并把它用起来的两条路径：**cordis 形态**（动态包，随会话存在）与**bundle 形态**（装进 profile，随部署常驻）。两条路径产出的能力相同，择一即可，也可以都走——形态差异由构建期吸收，业务代码只有一份。文档另给出跑它的测试、判读它的失败、以及判断这份做法何时不成立所需的事实。

工程根在下文一律记作 `<工程>`，即 `assets/projects/dsh-credentials/dsh-credentials/`（自带 `.git` 与远端）。命令都在该目录下执行。

## 两条路径共有的前置

- 一份可用的 DSH 部署，且 `DSH_HOME` 下有默认 profile。
- Node 与 npm 可用（构建与单测都要）。
- 构建期工具链 `plugin-loader` 位于本知识库工程内（工程内 `package.json` 的 build script 按相对路径调用它，它不是本工程的依赖项，也不随包分发）。
- 凭证存**默认落在** `$DSH_HOME/.credentials.yaml`（`dsh-credentials-local` provider）。本插件不重造存储，只提供它缺的那层目录与界面。

本能力**不提供权限隔离**：存储文件与 agent 的工具进程同属一个 OS 用户，agent 读得到它。它降低的是重复配置成本与泄露面，不是隔离边界。

## 路径一：cordis 形态（动态包）

适用：让某个会话临时具备凭证管理能力，不写 profile、不落盘常驻。

1. 构建 cordis 产物：

   ```bash
   npm run build:cordis
   ```

   产物为 `dist/cordis/cred/{host-body.js,client-body.js}`（形态与产物目录的声明见 `loader-configs/build.json` 与 `loader-configs/loader.json`）。判据是**退出码 0 且两份产物非空**。

2. 用 `cordis_define` 把两份 body 定义为一个动态插件：`code.host` 取 `dist/cordis/cred/host-body.js` 的内容，`code.client` 取 `dist/cordis/cred/client-body.js` 的内容。

3. 用 `cordis_run` 激活该 package。

4. 激活后：宿主侧注册模型工具 `credential_manage` 与一组 Package 私有 RPC，浏览器侧在设置面板注册一个「凭证」页。**开发期即时验证**正是这条路径的长处——改代码后重跑构建并定义一个新 package 即可，不必重启 DSH。

cordis body 内**不得有静态 `import`**（它以 `new Function` 形态求值，不接受 import）。判据可现取：

```bash
grep -cE "^\s*import[\s(]" dist/cordis/cred/*.js   # 期望为 0
```

## 路径二：bundle 形态（装进 profile 常驻）

适用：让这套能力随部署长期存在，对该 profile 下每个会话都可见。

1. 构建 bundle 产物：

   ```bash
   npm run build:bundle
   ```

   产物为 `dist/bundle/{index.mjs,client.js}`；`package.json` 的 `main`、`exports` 与 `files` 三个字段声明的就是这两份产物加 `bundle.patch.yml`。

2. 把工程作为一个包装进目标 profile：

   ```bash
   dsh plugin add file:<工程> --profile <profile 名>
   ```

   `dsh plugin add` 会把该行**追加到 profile 组合树的行列表末尾**（这一点是下面双挂载守卫的已知限制的来源）。

3. 重载该 profile。bundle 形态的宿主半在 profile 的 `webServer` 上注册 `/dsh-credentials/api` 前缀路由，客户端半经同源 `fetch` POST 到该前缀，两者都不经过 `cordis_define`/`cordis_run`。

**`bundle.patch.yml` 目前刻意处于未注册状态。** 它携带可挂载的行，但本仓库没有把它装进任何 profile，也没有触碰任何 profile 文件。挂载是产出活体证据的那一步，因此是一个单独、显式的动作——不执行上面的 `dsh plugin add`，bundle 形态在本部署里就不存在。

`bundle.patch.yml` 的行上带一条**双挂载守卫**（`!!js` 表达式）：若已有另一个启用中的 entry 挂了同名包，本行让出。两个挂载会让 `/dsh-credentials/api` 前缀被注册两次，Loader 以重复为由拒绝。守卫只能看到自己**前面**的行——聚合 bundle 必须排在它前面，而 `dsh plugin add` 默认追加到末尾，顺序正好相反，这是该守卫的已知边界；同 id 的手工重复仍会在 Loader 处直接报错。

## 使用

两条路径装好后，使用方式完全相同。

**界面**：设置面板里出现「凭证」页。页面按领域分组列出目录里的每一项，每行给名称、ref、状态徽章与用途，已配置时另显来源。状态四值互相可辨——`set`／`unset`／`no-store`／`error`；`no-store` 表示这台机器写不了（存储缺席），`error` 表示该项这次没读到、可能再读一次就好，二者的处置不同，不合并。存储未挂载时整页降级为一句不可用说明，不渲染行、不给按钮。

**写入与移除**：点「设置」或「替换」展开输入行，点「移除」删除该 ref。`writable` 为假（只读来源遮蔽该 ref）或状态为 `no-store` 时两个按钮**禁用而非隐藏**，使「为什么不能改」在界面上可见。最常见的失败原话是「只读来源遮蔽了该 ref」——即启动环境里已有同名变量，此时存了也不生效，原样读它比任何改写都准确。

**模型侧**：agent 调 `credential_manage`，三个 action 为 `list`／`set`／`remove`。`list` 返回与页面同源的清单（同一 `CredentialCatalog`），`set`／`remove` 只返回写入结果。**三个 action 都不返回值**，模型无法把凭证读进上下文——这是设计，不是疏漏。

**SSH 免密配置**：设置页的「为另一台机器配置免密登录」是本插件唯一的 SSH 配置路径（目录里已不存在「粘贴私钥」那一行）。次序是设计的一部分：

1. 填地址、端口、账号（别名可留空自动生成），点「读取指纹」——这一步只跑 `ssh-keyscan`，**不提交任何凭据**；
2. 界面显示目标机公钥指纹，**在你勾选确认之前禁用提交按钮**；
3. 确认后提交密码，本机生成 ed25519 密钥对，用密码登录一次把公钥追加到远端，再写本机私钥与 `~/.ssh/config` 的 `Host` 段；
4. 密码只有那几秒存在于内存与一个仅本用户可读的临时文件里，成功、失败、抛错三条路都在 `finally` 里删除它。

**密码的传递路径是硬约束，不是实现细节。** 只有「600 临时文件 + `SSH_ASKPASS_REQUIRE=force`」一条同时不进 argv、也不进 `/proc/<pid>/environ`；命令行参数会进 argv，环境变量会进 environ（实测可读），两条都弃用。写入后还会回读该文件的权限位确认是 600，不符即删除并报错。

**指纹必须由人确认**：第一次连接一台尚未验证身份的机器没有可对照的信任锚，界面不会替你判断，也不会「因为连过」而豁免。

**已配置的目标面板**：表单下方列出本机所有能免密到达的机器，每行三个互相独立的事实——登记状态（`已登记`／`未登记`）、连接状态（`已连接`／`认证失败`／`连不上`／`未检测`）、显示名称（纯显示，不影响 ssh 怎么连）。**打开页面不向任何机器发起连接**；探活只在用户点「检测连接」时发生，因为要跑一次真实的 `ssh`。连接状态在本次进程内记忆、不落盘，进程重启后每个目标回到 `未检测`。`未登记` 的行是 `~/.ssh/config` 里发现但尚未纳管的机器，点「登记」即纳管；移除登记**不动** `~/.ssh/config` 里的段。探活报「认证失败」时，行内提示指名「重新绑定」——重输一次账号密码换一把新密钥，不必从零再配。

## 运行环境与沙箱

**免密登录需要写入 `~/.ssh`**（私钥与其 `Host` 段都落在那里，否则 `ssh <别名>` 用不上）。在 `workspace-write` 沙箱下这不成立：实测该模式把 `~/.ssh` 随 `--ro-root` 只读挂入，写会失败。**该功能因此在 `danger-full-access` 下运行，或由挂载它的 bundle / preset 授予相应访问。**

本插件**不会自行提权**：`shell` 执行器的契约是「tool 层拥有审批并传入完整策略；direct call 回落到部署策略」，插件是 direct caller，自行传 `danger-full-access` 等于给自己超出会话的权限。所以它如实报告拒绝，而不是绕过它。

`--tmpfs /tmp` 另有一条后果：每条被沙箱约束的命令拿到独立的 `/tmp`，上一条命令建的文件下一条看不见。密码临时文件因此放在会话工作区而非系统临时区，且每条需要目录的命令都自己在同一条命令内建它。

**bundle 形态的宿主探针需要写 `DSH_HOME`**（每次启动都往 profile 目录写 `cordis.yml`）。`workspace-write` 下它们以 `EROFS` 失败——那是环境拒绝，不是用例失败。

## 测试与验证

```bash
npm test              # 单测：内存打包的模块
npm run build:bundle  # 两形态都要能转换
npm run build:cordis
npm run test:e2e:setup   # 幂等；建专用 profile e2e-credentials（端口 3099），不动你的 web profile
npm run test:e2e
```

判据：`npm test` 全绿且退出码 0；两条构建命令各自退出 0 且产物非空；E2E 的**每一个探针都退出 0**（不是与某个写死的条数相等）。测试分层、镜像规则、各文件的对象与反证纪律取回自 `tests/README.md`。

E2E 用专用 profile 与临时凭证库，开发者的运行中 harness 与 `.credentials.yaml` 都不被触碰。**不能用全新 `DSH_HOME`**——那会得到一个空的默认 profile，行根本不会挂载，探针会因与代码无关的原因 404。

装好后想自查，按这条次序：**设置面板里真的有「凭证」页 → 该页渲染出目录行与摘要 → 在页面里存一个值后 `$DSH_HOME/.credentials.yaml` 里出现该 ref，且任何回包都不含该值**。

## 故障处置

- **插件停在未激活态，什么都没注册**：宿主半在 `harness.defineTool` 处被运行期拒绝。原因是结构性的——工具定义的形状不合运行期要求（缺 `output` 声明、`output.schema` 用了对象级 `required` 数组、`parameters` 根声明了 `additionalProperties` 三类已知）。**一个只注册了半边的插件比没有插件更难诊断**，所以这里不降级：能修的是定义，不是运行环境。形状由单测的形状锁守住，见 `tests/README.md`。
- **页面报「凭证存储未挂载」**：`credentials` seam 缺席。宿主侧 `seam()` 返回 `undefined` 而不抛错——目录仍要能列出「有哪些凭证」，即使这台机器一个都写不了。处置是改部署组合（把存储 provider 装回去），不是在页面上操作。
- **点「读取指纹」报错，或某个操作答 404**：RPC 清单的权威源是 `src/shared/protocol.ts` 的 `OPERATIONS`，宿主注册的每个方法都必须在其内，否则 bundle 路由不分发它。这条是有历史的：白名单曾与共享清单各自漂移，`bootstrap-scan`／`bootstrap-install` 答 404。防复发守卫在 `tests/client/adapters/bundle/transport.test.ts` 的 `THE COVERAGE CASE`。
- **免密安装报错**：本机已有同名私钥或 `~/.ssh/config` 已有同别名条目时**拒绝且不覆盖**——那可能是用户通往该机的既有通路。换个别名，或在已登记的行上用「重新绑定」以替换语义绕开。
- **远端「什么都没发生」但退出码 0**：远端命令是 `sh -s -- <公钥>`，脚本经 stdin 送达。端口丢掉 `stdin` 时 `sh` 什么都不跑、退出码 0、没有 `INSTALLED`，报出来的失败读起来像成功。两形态都曾如此，各自的用例现已锁住传递（`tests/host/adapters/{,cordis/}ports-bootstrap.test.ts`）。
- **写日志不落 journal**：宿主 logger 目前只进 cordis `LoggerService` 的内存环形 buffer，全宿主无 stdout／文件 exporter。本插件因此自带一条落盘通道，每条 `report()` 先落盘再走 logger，落盘文件是 `$DSH_HOME/logs/dsh-credentials.log`（一行一报可 grep）。排障先看它。

## 未验证面

以下环节**尚无证据**，读到这些部分时不要当作已验证。

- **密码认证从未对真实服务器成功过。** `bootstrap-success.e2e.mjs` 用 `PATH` 上的 `ssh` 替身顶掉「一台会接受密码的服务器」这一件，把「安装跑完并产出可用本机配置」证到；替身顶掉的正是认证那一段。这台机器上做不到的原因（无 root、无 `uidmap`、`/etc/pam.d` 与 `/etc/nsswitch.conf` 只读）逐条列在 `tests/README.md`。换一台有 root 或已装 `uidmap` 的机器即可补上，届时把替身换回真 `ssh`。
- **真实浏览器渲染**只断言到「section 出现且面板渲染出行与摘要」，像素级布局与样式没有断言，也没有截图基线。既有断言写于 SSH 私钥行还在时，SSH 组现无成员，该行断言待调整。
- **`tests/live-mount-probe.mjs` 当前基线即红**：报 `registered no tool`，对干净的 git 树同样失败，属装配面 loader 环境的既有问题，与任何进行中的源码改动无关；在该探针恢复之前，bundle 形态的装配级证据不可复算。
- **`bundle.patch.yml` 的挂载只有专用 profile 下的活体证据**（`e2e-credentials`）；本仓库的 profile 里从未挂过它。

## 适用范围

- **成立**：本部署的 DSH 版本与工程的契约相容（客户端侧用 `slots` 服务、宿主侧用 `credentials` seam，两者都是**可选读取**，缺失时不中止装配，只让对应能力不可用）；已按前置装好 Node、npm 与构建期工具链；`$DSH_HOME` 下已有默认 profile（**不是**全新的空 `DSH_HOME`）。
- **失效**：
  - `workspace-write` 沙箱下 SSH 免密配置与宿主探针不可用（前者被拒的是 `~/.ssh` 写权限，后者是 profile 写权限）。这是环境拒绝，不是插件缺陷。
  - 指望「读回已存的凭证值」时。这个能力**无法读回任何值**：seam 端口没有 `resolve`，`describe` 本身不返回值，页面输入框是只写的，模型工具三个 action 都不返回值。
  - 指望本能力充当权限边界时。它不隔离，见「两条路径共有的前置」。
  - 用 `dsh plugin add file:<工程>` 挂载时，工程目录必须先经 `npm run build:bundle` 产出 `dist/bundle/`（`files` 字段只收那两份产物与 patch，`dist/` 不入库）。拿一份没构建过的源码树去挂载，装上去的行没有可加载的入口。
