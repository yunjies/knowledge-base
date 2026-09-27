# dsh-plugin-manager 部署与使用

本文档给出把 `dsh-plugin-manager` 装进一个 DSH 部署、并把它用起来的做法。本工程支持两种落地形态，但两者的**用途关系不同**，不是同一件事的两个入口：

- **cordis 形态**是**开发期即时验证**的通道。改完代码不必重启 DSH，重新定义并激活一个动态包即可看到效果——它服务的是本插件的开发者，不是最终用户。
- **bundle 形态**是**交付分发**的路径。插件随 profile 常驻，对该 profile 下的会话长期可见，装完不用再管。

因此本文档把两者分开写：先讲怎么交付（bundle），再讲开发时怎么迭代（cordis）。工程根在下文记作 `<工程>`，即 `assets/projects/dsh-plugin-manager/dsh-plugin-manager/`。

## 它做什么

设置界面的「插件」页新增一个**插件管理** tab，一屏列出全部插件，每个插件一个 cell，网格多列排布。每个 cell 第一行是插件名与版本，第二行是**开关**与**更新**两个按钮。

它补的是 DSH 原有插件页的空缺：那一页是只读清单，能看不能改；开关一个插件要手改 profile 的 `cordis.patch.yml`，更新一个插件要自己查版本再敲 `dsh plugin add`。本插件把这两件事放进同一个面板。

## 交付：bundle 形态

适用：让这套面板随部署存在。

前置：能访问 pnpm 存储与 registry（安装走官方 `dsh plugin` 通道），且已有一份可用的 DSH 部署。

1. 构建 bundle 产物：

   ```bash
   npm run build
   ```

   即 `npm run build:bundle`，产物为 `dist/bundle/{index.mjs,client.js}`；`package.json` 的 `main`、`exports`、`files` 三个字段声明的就是这两份产物加 `bundle.patch.yml`。

2. 装进目标 profile：

   ```bash
   dsh plugin add file:<工程> --profile <profile 名>
   ```

3. 重载 profile。**装载后需要重载才生效**——面板会在每个动作的结果里写明这一点，不必自己去猜。

bundle 形态的宿主半在 profile 的 `webServer` 上注册 `/dsh-plugin-manager/api` 前缀路由，客户端半经同源 `fetch` POST 到该前缀。宿主半**声明了 `inject: ['webServer']`**：不声明时该行会在 server 就位前激活，路由注册静默失败，客户端只会看到一个来自它从未占用过的路径的 405。

`bundle.patch.yml` 上带一条**双挂载守卫**（`!!js` 表达式）：若已有另一个启用中的 entry 挂了同名包，本行让出，使第一个实例胜出——两个挂载会把 `/dsh-plugin-manager/*` 注册两次，Loader 以重复为由拒绝。守卫只能看到自己**前面**的行，而 `dsh plugin add` 默认追加到末尾，所以聚合 bundle 必须排在它前面；顺序反过来是该守卫的已知限制。同 id 的手工重复仍会在 Loader 处直接报错。

## 开发：cordis 形态

适用：改本插件的代码时看到效果，不重启 DSH。

```bash
npm run build:cordis   # 产出 dist/cordis/pgm/{host-body.js,client-body.js}
npm run make-loader    # 生成 loader 壳子
npm run verify         # 校验产物
```

判据：`npm run verify` 末尾出现 `ALL CHECKS PASSED` 且退出码为 0。

然后用 `cordis_define` 把两份 body 定义为动态插件，用 `cordis_run` 激活。形态差异由构建期吸收（`loader-configs/build.json` 的 `adapters` 按形态把 `src/{host,client}/adapters/index.ts` 解析到 `bundle/` 或 `cordis/` 下的实现），业务代码不分叉。

产物与参数表由 `loader-configs/loader.json` 声明：`bodyDir` 与 `build.json` 的 `runtimeDir` 相同，`hostParams` 为 `harness`、`ctx`，`clientParams` 为 `React`、`host`、`styles`、`ctx`。

## 使用面板

打开设置界面 → 「插件」页 → 「插件管理」tab。面板按组件的层序读出清单，每个 cell 给两件事：

**开关**。写的是 profile 的 `cordis.patch.yml`——**用户自有那一层**，不是 `cordis.yml`（生成层，升级会重写，写它会丢）。首次写入前会在同目录留下 `<patch>.before-plugin-manager` 备份，那是可回滚的抓手。

一条必须知道的语义边界：**bundle 自带的 `disabled` 属于下层，本插件删除自己的覆盖并不能推翻它**。面板会如实说明这一点，而不是让你以为开关失灵。

**更新**。只在 registry 报告了更新的版本时才执行，安装走官方 `dsh plugin ... add` 通道，由 DSH 自己承担 profile 层的语义。

**本插件自己的行不可开关、不可更新**——否则会卸载正在显示这个面板的 tab。

版本按包名读该包自己的 `package.json`，包根在 profile 自有树与 profiles 同级共享树两处依序找。

## 部署落点怎么被找到

部署根与 profile 名**由发现得出，不靠配置**：

- `DSH_HOME` 读环境变量；
- **profile 名读不到**——已启动的 `dsh web` 不发布它。改由文件系统发现：DSH home 持 `profiles/`，其下带 `package.json` 的条目即 profile；多个并存时取 manifest **最近修改者**，面板显示它落定的路径。

因此**装好后面板列的是哪个 profile 的插件，取决于该目录下哪个 manifest 最新被改**。多 profile 并存而面板显示的清单与你预期不符时，先看这一点，不要先怀疑清单读取坏了。

**清单读的是组合树的层序，不是单份文件**：profile `package.json` 的 `dsh.profile.bundles` → 各 bundle 的 patch 文件里的 `insert:` 行 → profile 自己的 `cordis.patch.yml`。只读 profile 自己的 `cordis.yml` 会得到空列表，因为那一份在真实部署里就是 `[]`。

## 测试与验证

四层，各自回答不同的问题：

```bash
npm test          # 单测：内存打包的模块
npm run test:e2e  # cordis E2E：打真实常驻 GUI（需要 GUI 在跑，且本插件已 define 并可激活）
npm run test:mount  # bundle-mount E2E：自建 scratch profile + 独立 dsh web
npm run verify    # 产物校验
```

判据：四条命令各自全绿且退出码为 0。

`npm run test:mount` 是**唯一**能回答「发布出去的那份 bundle 真的装得上、装完真的能用」的一层：它建一个临时 DSH home，经官方 `dsh plugin add` 通道挂载 `dist/bundle`，另起一个独立 `dsh web` 打那个 scratch profile，跑完删除。它也是唯一被允许**写** profile 的一层，因为它写的 profile 属于它自己建的临时目录；其余各层都不得触碰用户的部署。

两条 E2E 轨都以 `tests/e2e/check-freshness.cjs` 为前置（重建并比对产物哈希，防止验证过期产物），并各自带**零用例即失败**守卫——一条没跑到的用例不得读作绿。

分层判据、各文件的对象与本层不断言什么，取回自 `tests/README.md`。

装好后自查：设置界面「插件」页里出现「插件管理」tab → 打开后网格渲染出插件 cell → 点一次开关，profile 的 `cordis.patch.yml` 出现对应改动且同目录留下 `.before-plugin-manager` 备份。

## 故障处置

- **tab 没出现**：先确认 profile 已重载。仍不出现时，看客户端注册契约——tab 的注册选项必须**同时**带 `name`（目标插槽键 `settings.plugins.tab`）与 `id`（本项在该插槽内的 cell 键，本工程用 `manager`）；缺 `name` 会被客户端 Guard 在激活后拒绝。
- **面板打开但请求 405／打不通**：宿主半的 `webServer` 注入未生效，路由注册静默失败。这是 bundle 形态最容易踩的一处——它不报错，只是从一个从未被占用的路径收到 405。
- **列表为空**：多半是读错了层。清单来自组合树的层序，profile 自己的 `cordis.yml` 在真实部署里就是 `[]`。
- **开关点了没反应**：该插件所在的下层（bundle 自带的 patch）声明了 `disabled`，本插件删除自己的覆盖推不翻它。面板会写明这一情形。
- **版本列读不出**：包根按包名在两处依序找，找不到就报缺。先确认该插件确实装在 profile 自有树或同级共享树里。

## 未验证面

尚无证据的环节，不要当作已验证：

- **`npm run test:e2e` 需要一份正在运行且已加载本插件的常驻 GUI。** 它打的是**你自己的部署**（只读地开与关它自己那一行除外），因此没有这样一份实例时它跑不起来，其结论也不是可复算的。bundle-mount 轨不需要常驻实例，是这一情形下可取的第二条证据。
- **面板在像素层的行为**（多列排布的具体列宽、窄屏折叠）只有常驻 GUI 轨覆盖；单测断言的是面板的过滤与响应折叠这类纯决策。
- **`npm run verify` 判的是 loader 壳子与 body 的形状**（`ALL CHECKS PASSED`），它不证明真实 DSH 进程能激活这份 body——那由两条 E2E 轨承担。

## 适用范围

- **成立**：已有一份可用的 DSH 部署；执行安装的账号对 `$DSH_HOME` 有读写权（开关动作要写 profile 的 patch 层）；bundle 形态另需能访问 pnpm 存储与 registry。
- **失效**：
  - `workspace-write` 沙箱下**开关与更新不可用**——它们要写 profile 目录，被环境拒绝。那是环境拒绝，不是面板缺陷。单测不受影响。
  - 想用本面板管理**它自己这一行**时。设计上就不允许：开关它等于卸载正在显示面板的 tab。
  - 多 profile 并存且你依赖「面板显示哪个 profile」时，结论由 manifest 修改时间决定，不由此处的任何配置决定。
  - 拿未构建的源码树走 `dsh plugin add file:<工程>` 时：`files` 字段只收 `dist/bundle/` 的两份产物与 patch，`dist/` 不入库，先跑 `npm run build`。
