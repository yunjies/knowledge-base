# testbench 部署、运行与排查

## 前置条件

在 `assets/projects/testbench/testbench/` 执行命令。需要 Node.js、npm，以及可启动的 Chromium。依赖版本和脚本入口以项目根目录 `package.json` 为准。

## 本地部署与运行

```sh
cd assets/projects/testbench/testbench
npm ci
npm run test:static
npm test
```

`npm run test:static` 退出码 0 表示静态检查通过。此轮已验证 `npm run test:static` 退出码 0。

浏览器测试会启动 `src/server.js`，使用随机端口提供页面，执行标题、初始状态和按钮交互断言。测试脚本为浏览器进程建立 `tests/.artifacts/` 下的临时可写 `HOME/XDG` 环境；当前主机上的 `npm test` 退出码 0。

若部署机已有可用 Chromium，显式指定可执行文件：

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/path/to/chromium npm test
```

也可使用项目支持的备用变量：

```sh
CHROMIUM_EXECUTABLE_PATH=/path/to/chromium npm test
```

运行时证据写入 `tests/.artifacts/`：`testbench.png`、`trace.zip`、`report.html`、`server.stdout.log` 和 `server.stderr.log`。本轮已生成截图、trace、报告和日志；报告结果为 `PASS`。该目录是运行时证据，不应提交为源码。

## Docker 路径

项目提供：

```sh
docker build -t testbench .
docker run --rm testbench
```

Dockerfile 基于 `node:22-bookworm`，安装 npm 依赖和带系统依赖的 Chromium，再运行 `npm test`。本机不存在 `docker` 命令，因此 Docker 构建与运行尚未验证；不要把它写成已通过的部署方式。

## 排查

### 静态检查失败

读取 `npm run test:static` 的完整输出，确认 `package.json`、`src/index.html` 和 `src/server.js` 仍满足 `tests/static-check.js` 的断言。修复后重新运行静态检查，必须以退出码 0 为准。

### 浏览器启动失败

先查看：

```sh
sed -n '1,200p' tests/.artifacts/report.html
sed -n '1,200p' tests/.artifacts/server.stdout.log
sed -n '1,200p' tests/.artifacts/server.stderr.log
```

确认 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 指向真实可执行文件；若浏览器仍无法启动，读取报告与服务端日志，再检查 Chromium 运行库和可执行文件权限。测试脚本会为浏览器进程提供隔离的可写 `HOME/XDG` 目录。

### 页面断言或证据失败

确认 `npm test` 启动的本地 server 已监听，访问根路径返回页面，`#run` 点击后状态变为 `Check passed`。检查 `tests/.artifacts/report.html` 是否为 `PASS`，并确认截图和 trace 存在：

```sh
test -s tests/.artifacts/testbench.png
test -s tests/.artifacts/trace.zip
grep -F '<p class="result">PASS</p>' tests/.artifacts/report.html
```

只有 `npm test` 退出码 0 且报告显示 `PASS` 时，浏览器流程才算通过。
