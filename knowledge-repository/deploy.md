# knowledge-base 部署与环境查漏补缺

本文档的职责是让 knowledge-base 在一个新环境中具备可运行条件，或对已经部署的 knowledge-base 做环境检测、发现缺项并补齐。它不负责部署任何被收录项目的运行服务，单个项目的部署请读对应的 [项目部署文档](../assets/projects/<项目>/deploy.md)。

## 适用范围

本说明有两种运行模式：新环境模式负责安装或准备 KB 所需工具并逐项验收；查漏补缺模式从已部署的 KB 根目录开始，复用同一套检查，定位缺失、失效或权限不足的能力后修复并复验。检查范围包括 KB 守护、项目测试所需的基础工具、GitHub 远端与 GitHub Actions。它不保存令牌、密码、私钥、私有地址或某次机器的具体取值，环境相关值都通过命令现取。

## 前置条件

- 已从 Git 仓库检出 knowledge-base，并能在仓库根目录执行命令。
- 主机提供 Git、uv、Node.js 与 npm；具体版本和是否可执行以现场命令输出为准。
- 需要运行某个被收录项目时，先进入该项目自己的独立克隆，再按其 tests/README.md 的前置条件准备依赖；不要把项目测试移到本知识库执行。
- GitHub 远端的访问凭据已由宿主的 SSH agent、Git credential helper 或其它受管凭据来源提供；凭据不写入仓库文件。

## 部署与环境检测流程

### 1. 确认工作区与工具链

新环境先安装或准备前置工具；已部署环境直接从 knowledge-base 根目录执行：

~~~bash
pwd
git status --short --branch
for command in git uv node npm; do
  command -v "$command" || exit 1
  "$command" --version
done
~~~

pwd 必须指向当前 knowledge-base 根目录。新环境中任一工具缺失时，先按主机发行版或官方安装方式补齐，再从本步骤重新检查；已部署环境中任一工具失效、版本不满足或权限不足时，先修复该项再继续。不要把本机生成的缓存、凭据或环境文件作为部署产物提交。

### 2. 验收知识库测试环境

知识库自己的可执行守护位于 [_lint/](../_lint/)，它只验证知识库文档。入口与固定的缓存位置由 [_lint/run.sh](../_lint/run.sh) 承载：

~~~bash
./_lint/run.sh
~~~

判据是测试全绿且退出码为 0。该命令会把 uv 缓存写入仓库内的 .uv-cache/；该目录是可重建的本地产物，不是部署内容。失败时读取 pytest 的具体失败项，修正文档后从本步骤重新执行，不通过放宽断言或跳过用例。

### 3. 验收被收录项目的测试环境

被收录项目的测试套件属于项目自己的仓库克隆。进入目标项目克隆后，先读它的 tests/README.md，再执行其中列出的命令；该文件同时给出测试层、前置服务、真实环境限制与“全绿且退出码 0”的判据。

不要用知识库的 [./_lint/run.sh](../_lint/run.sh) 代替项目测试，也不要从知识库根目录猜项目测试的工作目录。需要真实进程、浏览器、容器或外部服务的测试，只能在其 README 声明的环境中运行；环境不满足时记录为未验证面，不把静态测试的绿灯升级成完整部署证明。

### 4. 验收 GitHub 远端与 CI 路径

先从 Git 配置取回远端，不在本文档抄写仓库地址：

~~~bash
git remote -v
git ls-remote origin HEAD
~~~

git ls-remote origin HEAD 退出码为 0，且能返回远端 HEAD，才算当前工作区能读取 GitHub 远端。失败时按失败类型检查 SSH agent、Git credential helper、网络出口与远端权限；不要把令牌写进命令行、仓库或日志。

GitHub Actions 的知识库守护入口是 [.github/workflows/guard.yml](../.github/workflows/guard.yml)，它在推送到 main 或拉取请求时调用 ./_lint/run.sh。提交前必须先在本地通过同一入口；推送或创建拉取请求后，以 GitHub Actions 的该工作流实际结果为远端验收证据。若远端工作流失败，读取失败步骤与提交对应的 diff，修复后重新运行本地守护再提交。

### 6. 完成前检查工作区

~~~bash
git status --short
git diff --check
~~~

完成部署或查漏补缺前应确认：

- 变更只包含需求范围内的知识库文档或明确的工程改动；
- 没有把 .env、令牌、私钥、凭据文件、真实主机地址或运行缓存纳入提交；
- ./_lint/run.sh 已以退出码 0 完成；
- 目标项目的测试结果按其 tests/README.md 的判据单独记录；
- GitHub 远端可读，且远端 CI 对当前提交通过。

## 失败定位

- **工具缺失或版本不满足**：修复主机工具链后重新执行“确认工作区与工具链”。
- **知识库守护失败**：只按 [_lint](../_lint/) 的失败信息修正文档；测试入口在 [_lint/run.sh](../_lint/run.sh)，判据在 [_lint/README.md](../_lint/README.md)。
- **项目测试失败**：在项目克隆内按该项目的 tests/README.md 归因；不要修改知识库守护来掩盖项目失败。
- **GitHub 远端读取失败**：先分离网络、凭据与仓库权限问题；不得用复制令牌到命令行的方式止血。
- **本地通过、GitHub CI 失败**：以 [.github/workflows/guard.yml](../.github/workflows/guard.yml) 的 runner 步骤为准，核对提交内容与 runner 所需工具，不以本地缓存结果替代远端证据。

## 可观察完成条件

只有以下证据同时成立，才把当前环境视为可运行且检查合格：

1. 工具链检查全部成功。
2. ./_lint/run.sh 全绿且退出码为 0。
3. 目标项目按其自身测试 README 完成了声明范围内的测试；未具备的真实环境证据已明确标为未验证。
4. git ls-remote origin HEAD 退出码为 0。
5. 若本次产生需要提交的变更，提交后 GitHub Actions 中 .github/workflows/guard.yml 对该提交通过；仅做环境复核时，以本地守护通过为准。

## 适用边界

- **成立**：knowledge-base 仍以 [_lint/run.sh](../_lint/run.sh) 作为本库守护入口，GitHub CI 仍由 [.github/workflows/guard.yml](../.github/workflows/guard.yml) 调用该入口，且被收录项目继续在各自克隆内维护测试。
- **失效**：守护入口、CI 工作流、项目测试位置或远端认证方式发生变化。此时先从仓库配置与目标项目的 tests/README.md 重新取回入口，再更新本文档。
