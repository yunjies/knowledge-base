# dsh-credentials 在 DSH 中部署

本文只记录将 dsh-credentials 接入 DSH profile 的步骤。bundle 构建方式以源码仓库 [README 的「构建」章节](../../projects/dsh-credentials/README.md#构建)为准；测试入口和判据以仓库的 [`tests/README.md`](../../projects/dsh-credentials/tests/README.md) 为准，本文件不复制这些说明。

## 前置条件

- 目标 DSH profile 已存在且可由当前 DSH CLI 管理。
- 已按源码仓库 README 的构建章节生成 bundle 产物。
- 需要验证业务行为时，按源码仓库 `tests/README.md` 选择对应测试层；安装动作本身不替代项目测试。

## 安装到 profile

在运行 DSH CLI 的主机上设置两个变量。`PROJECT_ROOT` 必须是该主机可读的**绝对路径**，并指向已构建的源码仓库根目录；`PROFILE` 是目标 profile 名。双引号使路径包含空格时仍作为单个参数传入。

```sh
PROJECT_ROOT="/absolute/path/to/dsh-credentials"
PROFILE="profile-name"
dsh plugin add --profile "$PROFILE" "file:$PROJECT_ROOT"
```

该命令通过 DSH 插件管理 CLI 将 bundle 依赖加入目标 profile 的组合；不要手工把 `bundle.patch.yml` 复制进其他 profile。命令成功不代表已运行的 DSH 进程已重新加载磁盘上的 profile。

如果目标 profile 正在运行，先通过**启动它的进程管理器**停止该进程；以前台方式启动的进程可在其终端按 Ctrl+C 停止。然后用 `dsh --profile "$PROFILE"` 启动 profile。DSH CLI 提供 profile 启动入口，但没有通用的热重载/停止命令；服务管理器的停止动作取部署实际使用的入口，不在本文猜测。

## 可观察验证

停止旧进程后运行 `dsh --profile "$PROFILE" --dump-config`，在组合 profile 输出中确认 dsh-credentials bundle 行；启动 profile 后再确认 DSH Settings 面板出现「凭证」页。进一步验证页面行为与宿主业务面时，运行源码仓库 `tests/README.md` 所列的相应活体测试；本文件不把已安装或页面可见等同于完整功能验收。
