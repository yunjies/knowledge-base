# dsh-dynamic-cordis-loader 部署与使用

本项目是 DSH Web profile 的 bundle 插件。用户在 WebUI 为目标 Session 输入 Host 可读的项目根目录，递归检索候选源码并手动选择；只有点击 **Load** 或 **Load update** 才会校验、读取并运行源码。动态定义不持久化到 profile，DSH 重启后须再次手动加载。项目流程见 [feature-flow.md](feature-flow.md)，包说明见 [README.md](dsh-dynamic-cordis-loader/README.md)。

## 部署

前置条件：目标 profile 提供 WebUI、动态 Cordis Host runner 与 Client runner，且 Host 进程能够读取用户输入的项目根目录。

在目标 profile 安装本地项目包：

```sh
dsh plugin add file:/absolute/path/to/dsh-dynamic-cordis-loader --profile web
```

将 `web` 替换为目标 profile。插件管理器也可接受本地目录安装 spec。首次安装或新增 profile bundle 可能需要重启；以插件管理器返回的 `application` 状态为准。侧栏出现 **Dynamic Cordis／动态 Cordis** 才能证明已挂载；`restart-required` 时刷新浏览器不能代替重启。

工程没有独立编译步骤。用户输入的是已构建动态 Cordis 源码的项目根目录，而不是一个普通 npm 插件包；加载器不会读取 `package.json`，不会解析 entry、打包、转译或解析依赖。

## 使用

1. 打开 WebUI 侧栏的动态 Cordis 面板并选择目标 Session。
2. 输入 Host 可访问的绝对项目目录路径。可用 POSIX `/`、Windows drive 或 UNC 路径语法，路径不得超过 4096 个字符。Client 仅用 `trim()` 判断输入是否为空；路径校验、Session 登记与发给 Host 的 payload 保留用户输入的原始路径字串。
3. 点击 **检索文件**。Client 调用 `/dcscan`；Host 递归列目录元数据，不读取源码字节、不执行源码，响应只含候选目录与相对文件路径。候选项要求同一目录内存在精确名称且类型为普通文件的 `host.js`；同目录的精确 `client.js` 为可选半区。`host-body.js`、`client-body.js` 不是别名，检索不会把其它目录的 `client.js` 与 Host 文件配对。
4. 单个候选项会预选；多个候选项必须由用户明确选择。选定后登记会把项目根目录及相对文件路径按所选 Session 存入当前浏览器的 `localStorage`。没有候选项时不能登记或加载。项目结构变更后，用户可点击 **重新检索**；如果原候选项仍在，面板保留它，否则用户须重新选择。旧 `{paths:{host,client}}` 逐文件登记仍可显示，但没有 `sourceDir`，加载按钮禁用。
5. 用户点击 **Load** 或 **Load update** 后，Client 才向 Host 发送 `/dcload`。Host 重新解析项目根与已选目录，确认所选路径仍在根目录内，并检查同一目录中的当前 `host.js` 与可选 `client.js` 文件集合仍与所选项相同。文件缺失、非普通文件、路径越界或文件集合变化时，Host 拒绝加载，用户须重新检索。文件字节改变但路径与文件集合不变时，显式 Load 会读取当前字节。
6. Host 以严格 UTF-8 读取所选文件，每个半区最多 256 KiB，合计最多 512 KiB。Host 与 Client 半区必须是动态 Cordis runner 接受的 JavaScript async-function body，并返回 Cordis Plugin；ESM `export` 语法不接受。Plugin 名称取项目根目录 basename，经 trim 后截断至 120 个字符；根目录、`.` 或 `..` basename 使用 `Dynamic Cordis` fallback。用途由加载器固定，不提供编辑字段。
7. 若当前 Session 的 inventory 仍包含登记关联的动态插件，Client 用该插件身份追加不可变 package；否则 Host 定义新插件。删除浏览器登记不会停止已运行插件；DSH 重启清除进程内定义，但保留浏览器登记。

`/dcscan` 与 `/dcload` 请求体最多 16 KiB，项目根目录及每个已选相对文件路径最多 4096 字符。检索深度上限为 32 层、访问目录数上限为 10,000、目录项数上限为 50,000、候选项数上限为 128、序列化结果上限为 12 KiB；超过任一界限时检索报错，不静默截断并返回部分结果。两个命令都设置 `recordInput: false`，但 `command/done.text` 仍写入 Session log；`/dcscan` 的结果仅含相对路径。检索上限测试覆盖绝对根目录校验、必需路径对、非普通文件 `host.js`，以及深度、目录数、目录项数、候选数、序列化结果大小和相对路径长度各项上限。Cordis VM 不是安全边界，只登记可信源码。

文件名契约严格且不做猜测。当前知识库中的 `dsh-credentials` 项目根目录搜索不会产生候选：其 Cordis 输出是 [`host-body.js`](../dsh-credentials/dsh-credentials/dist/cordis/cred/host-body.js) 与 [`client-body.js`](../dsh-credentials/dsh-credentials/dist/cordis/cred/client-body.js)，没有精确的 `host.js`；这两个 body 文件不映射为 `host.js`／`client.js`。[`dist/bundle/client.js`](../dsh-credentials/dsh-credentials/dist/bundle/client.js) 位于无匹配 Host 文件的另一个目录，也不会被配对。Host 要求 `/dcload` 请求同时提供已选中的 `hostRelativePath` 与 `clientRelativePath` 字段；无 Client 半区时仍须显式传 `null`。缺少任一字段的请求会在目录列表与源码读取之前被拒绝，不提供直接根目录 Load 兼容；调用方须先搜索并提交选择路径。

## 验证

当前源码测试命令与覆盖边界见 [tests/README.md](dsh-dynamic-cordis-loader/tests/README.md)。自动化测试使用 fake Host filesystem／runner 与静态 Client 断言；没有真实 WebUI render、live Host-Client 执行或 `command/done.text` 日志行为验证。侧栏可见与成功的 runner 收据也不能替代用户对目标 Session 的 live UI/E2E 验收。
