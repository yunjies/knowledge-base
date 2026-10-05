# DSH Settings trusted-authority 插件部署与使用

本说明覆盖插件包的测试、打包、Web profile 安装、Models 页面验收与卸载。项目仓库位于 [dsh-settings-trusted-authority/](dsh-settings-trusted-authority/)，其 GitHub remote 为 [yunjies/dsh-settings-trusted-authority](https://github.com/yunjies/dsh-settings-trusted-authority)。

## 适用范围与替代行为

插件面向 DSH Web profile；其 `client.js` 是基于 DSH `0.2.0-rc.2` Settings provider 的独立 bundle，Host 与 browser 契约升级后须按本说明重新验收。

profile patch 只禁用 browser roster 中的 `ui-settings` provider 并插入替代 provider；其他 `ui-settings-*` 页面与 Settings 消费模块仍留在组合树中。

替代 client bundle继续提供 ConfigForms（含共享 `developerTools` preference）、Settings schema 与 Settings describe mirror，并经现有 `remote.settings` 读写；Models 页 provider 配置在刷新后读回是本项目的浏览器验收面。

因此，在当前兼容基线上没有已知的 Settings 功能被有意移除；尚未逐项验证的 schema 与 provider 变体见[测试说明](dsh-settings-trusted-authority/tests/README.md)。

该包经 `dsh plugin` 作为 profile dependency 装载，不写 DSH 安装目录；这隔离了插件包与核心安装文件，但不保证未来 DSH 的 `ui-settings` entry、`webRuntime` 或 `configForms` 契约兼容。

## 前置条件

- DSH 已安装，目标 profile 使用 Web bundle，且插件管理器可写该 profile。
- Host Web 启动参数已把目标 authority 纳入 `--trusted-host`；默认 Web bundle 会把 Web runtime 的信任列表传给 Connection，若 profile patch 另行覆盖 Connection 配置，两份值必须保持一致。
- Node.js、npm 与 pnpm 可用；包不需要额外 runtime 安装步骤，执行入口取自仓库的 `package.json`。
- 安装或移除 bundle 会改变 profile membership；必须通过当前部署所用的服务管理器重启该 profile 后再做浏览器验收。

## 测试与打包

在仓库根目录运行 Node 静态测试：

```bash
npm test
```

全部用例通过且退出码为 0 才继续打包；测试对象和未覆盖面见 [tests/README.md](dsh-settings-trusted-authority/tests/README.md)。

在仓库根目录预览实际包内容并生成 tarball：

```bash
pnpm pack --dry-run
pnpm pack
```

`pnpm pack --dry-run` 的分发清单以 `package.json` 的 `files` 字段为准；生成的 `.tgz` 被仓库 `.gitignore` 排除，可随时重建。

## 安装与验收

将 `<profile>` 替换为目标 Web profile 名称，并在仓库根目录运行：

```bash
dsh plugin --profile <profile> add ./dsh-settings-trusted-authority-plugin-0.1.0.tgz
dsh --profile <profile> --dump-config
```

转储配置应显示内置 `ui-settings` entry 被禁用，并出现 `trusted-settings-authority-provider`；该组合同时由 `cordis.patch.yml` 与 `package.json` 声明。

重启目标 Web profile 后，使用已经通过浏览器会话认证的目标 authority 打开 Web 页面。

打开设置面板的 Models 页面，新增并保存一个 provider 配置，然后刷新页面；验收通过条件是该 provider 仍显示为已配置，且浏览器控制台没有 Settings 读写错误。

此步骤应在隔离 profile 中先执行；不得以运行中的用户 profile 代替兼容性探测。

## 回滚

在仓库根目录运行卸载命令：

```bash
dsh plugin --profile <profile> remove dsh-settings-trusted-authority-plugin
```

卸载后重启该 profile，再执行 `dsh --profile <profile> --dump-config`；验收结果是内置 `ui-settings` entry 恢复启用且替代 entry 不再出现。

卸载不会放宽或撤销 Host Connection 自己的信任配置；若不再需要该 authority，应通过部署原有的 `--trusted-host` 配置单独移除。

## 功能边界

- loopback 页面保留原来的 Host-backed Settings 行为。
- Web runtime 信任列表中匹配的非 loopback authority 可以选择 Host-backed Settings；Host/Origin fence 与浏览器会话认证仍独立判定每个 API 请求。
- 未匹配信任列表的非 loopback 页面继续使用页面内存态 Settings，刷新后不保证保留。
- 插件只扩展 Settings provider 的持久化选择，不改变 Connection 的 `isLoopback`，也不授权其他 loopback-only 功能。
- 第三方扩展若运行时依赖官方 provider 的原 module id 或内部导出，可能需要调整；上线前应审查该类直接依赖。
- 使用自定义 profile patch 覆盖 Connection `trustedHosts` 时，必须保证其与 Web runtime 信任列表一致；否则 Host/API fence 仍以 Connection 当前配置为准。