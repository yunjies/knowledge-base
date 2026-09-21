# 以 cordis 落地 home-media-pilot 服务

要在 DSH 会话里把 home-media-pilot 当动态 Cordis 插件跑起来、并借面板按钮打开它的 WebUI 做本机测试时读这篇。它给出该落地形态的构件、配置存盘位置与重启后的行为。

## 适用范围

- **成立**：本机开发/测试，服务与 DSH 同机；分支 `feat/cordis-hmp-service`（该分支在 `main` 的 bundle 路线之外**另加** cordis 落地，两者并存）。
- **失效**：生产或 NAS 部署——那走容器路线，见[部署 home-media-pilot](deploy-home-media-pilot.md)，与本篇无交集。

## 构件

仓库克隆内（`assets/projects/home-media-pilot/home-media-pilot/`）：

- `cordis/host.js`：host 半。经 cordis 的 `shell` 服务启停服务进程，经 `fs` 服务读写配置。
- `cordis/client.js`：client 半。注册进 `tool.view.cordis` 的 `key: 'self'`，即运行卡片内的那块面板。
- `src/apps/api/serve.py`：启动器。它把实际绑定的端口写进 `PILOT_API_PORT` / `PILOT_WEBUI_PORT` 再起 uvicorn。
- `src/apps/api/probe.py`：一次 HTTP 请求，结果以 JSON 打到 stdout。
- `src/apps/api/routes_settings.py`：`/settings/effective`、`/settings/ports`、`/settings/env`。

## 两条硬约束（改代码前必读）

**host 半跑在受限沙箱里**，不是普通 Node：`require`、`fetch`、`setTimeout`／`setInterval` 都被拦成报错，`process`、`Buffer` 为 `undefined`。文件走 `ctx.fs`，进程走 `ctx.shell`，延时走 `ctx.timeout`（时序另需 `inject: ['timer']`）。要确认某个能力是否存在，先用 `cordis_inspect_query` 查 `Service.listService`，不要按名字猜。

**动态包拿不到环境**：`harness` 只有 `defineTool`／`registerTool`／`handle`，沙箱也没有 cwd。所以**服务根目录是用户输入**，由面板填写后存进配置文件；空值时启动会明确报「the service root is not configured」，而不是静默拼出一条错命令。

## HTTP 为什么不经 curl

沙箱没有 `fetch`，而 `curl` 并非每台机器都有（实测本机就没有）。请求改由配置里的 Python 解释器执行 `apps.api.probe`——该解释器按定义必然存在，因为服务本身要靠它启动。请求体以 JSON 走 stdin，不依赖 shell 引号。

## 配置存盘

`cordis/settings.json` 与 `cordis/settings.env`，两者均被仓库 `.gitignore` 排除；判据可复算：

```bash
git check-ignore -v cordis/settings.json cordis/settings.env
git add -A -n | grep -c 'cordis/settings'   # 期望 0
```

`settings.json` 存根目录、端口、解释器与 `env`；`settings.env` 由服务的 `/settings/env` 写，供服务重启后读取。该路由拒绝 `PATH`、`DATABASE_URL` 等由运行时掌管的变量——它们不由面板管辖。

## 面板行为

运行卡片内提供「打开 WebUI」与启停/重启/刷新，以及配置表单。**按钮打开的端口取自服务自报的 `/settings/ports`**，不在 host 半二次推导：推导出的值与实际绑定值一旦分叉，症状是按钮打开一个空地址。

## 加载与判据

`cordis_define` 传两半全文，`cordis_run` 激活。判据是 `cordis_inspect_self` 报 `runtime.state` 为 `running`，且 host 半的 `handlers` 含 `hmp-status`／`hmp-start` 等方法、client 半 `waitingFor` 为空。client 半首次激活需在 GUI 批准。

## 已知边界

- `settings.json` 里的 `settingsFile` 默认写死为绝对路径。它在**服务根之前**就要可解析，而根本身存于该文件内，故不能相对化。换机器或挪动克隆目录时要改这一处。
- 面板的「打开 WebUI」用 `window.open`，受浏览器弹窗策略约束；被拦时页面不会有提示。
