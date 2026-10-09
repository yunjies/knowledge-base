---
name: version-management
description: 对 Git 仓库执行通用版本管理；先确认仓库状态与适用策略，再安全地整理、提交或发布变更。
whenToUse: 用户要求管理 Git 版本、检查工作区、创建或检查提交、同步远端，或通过 GitHub 工具查看/操作仓库时。
---

# 版本管理

本 skill 提供跨项目通用的 Git 版本管理逻辑。目标是让每次版本变更范围可解释、历史可追溯、失败可恢复；项目自己的分支策略、发布流程与目录约定优先于本 skill 的通用默认值。

## 执行入口

1. 确认用户要求的仓库、目标结果和允许的操作范围；含糊时先询问，不从当前目录名、历史对话或远端默认分支推断授权。
2. 先把目标路径解析到所属 Git 工作树根目录；工作区可能包含多个独立仓库，不能仅凭当前目录或最外层仓库推定目标。
3. 在每个目标仓库分别读取当前分支、工作区与暂存区状态、相关差异及项目声明的版本管理策略；保留与本次需求无关的既有改动。
4. 将变更限制在需求范围内；不要为制造干净状态而覆盖、丢弃、重置或移动用户的改动。
5. 本地 Git 操作不触发任何托管平台的初始化；只有远端操作确实需要平台能力时，才确认目标平台与仓库，并读取该平台的工具和认证约束。
6. 只有目标已确认为 GitHub 且本次操作需要 GitHub 工具、`gh` 或 GitHub Git 远端（SSH 或已认证的 HTTPS）时，才按[GitHub 工具护栏](references/github-constraints.md)发现并使用相应工具；不假设工具、权限、目标仓库或远端状态。
7. 若远端操作依赖的平台或 host 在目标运行环境中尚未初始化或缺少可用认证，停止该远端操作，向用户说明具体平台、环境和缺口并询问是否初始化；只有用户明确要求初始化或在此后确认，才安装工具、登录或修改认证配置，单纯请求远端操作不构成初始化授权。
8. 提交、推送、合并、创建发布或删除远端对象是彼此独立的动作。只执行用户明确要求且当前策略允许的动作；执行后核验实际结果。

## 通用基本逻辑

- **版本对象**：Git 提交记录一组有边界的变更及其父级关系；分支是提交历史的可移动引用，标签用于标识稳定版本。不要把工作区文件、提交、分支、标签或 GitHub 发布混为一谈。
- **多仓库工作区先定边界**：对每个目标路径用 `git -C <目标路径> rev-parse --show-toplevel` 解析所属工作树，并以 `git -C <仓库根>` 分别检查和操作。嵌套仓库与外层仓库是独立的版本边界；不得用外层仓库的状态、remote、身份配置或差异代替内层仓库的事实。一次需求涉及多个仓库时，分别核对每个仓库的改动与授权，不把它们合成一次提交。
- **先查状态再改动**：在已确定的目标仓库内查看当前分支、未提交差异、暂存内容、上游关系以及项目约定。若仓库状态与目标不匹配，先报告并暂停可能改变历史或远端状态的动作。
- **提交只纳入预期内容**：提交前逐项检查暂存差异，确保不包含无关文件、秘密或生成物；提交信息说明变更目的，而非复述实现细节。没有明确提交请求时，只准备或说明建议，不自行提交。
- **共享历史优先可追加**：普通修正以新增提交表达。改写已共享历史、强制推送、删除分支或标签等会影响他人的操作，须有明确授权并确认影响范围；不以方便为由执行。
- **同步先判方向**：拉取、推送或合并前核实本地与远端的关系、目标分支及冲突风险。冲突时保留双方信息并报告，不擅自选择丢弃一侧。
- **验证与复原**：操作后重新读取仓库状态及相关远端结果，证明目标已达成且没有额外影响。若失败，停止重复写操作，报告已完成步骤、当前状态与可逆/不可逆影响。

## GitHub CLI 与 SSH 接入

本节仅在目标已确认为 GitHub 且本次操作需要 `gh`、GitHub SSH 或经认证的 GitHub HTTPS 访问时执行；调用本 skill 或进行纯本地 Git 操作不触发 GitHub 初始化。

使用 GitHub CLI 时，按需参考 GitHub 官方 [`gh` agent skill](https://github.com/cli/cli/blob/trunk/skills/gh/SKILL.md)中的命令用法；它提供通用调用模式，本节的凭证存储、明文回退与 HTTPS 验证要求仍是本工作流的安全护栏，不得被通用示例覆盖。

进入本节后，先在目标运行环境检查 `gh --version`；若已安装，再运行 `gh auth status` 核实目标 host。若 `gh` 未安装、目标 host 未认证或所需认证不可用，且本次请求未明确要求初始化，按执行入口步骤 7 停止并询问；若请求明确要求初始化，则仅按后续步骤处理已确认的 host 与运行环境。

用户明确要求或确认安装 GitHub CLI 后，若 `gh` 未安装，按操作系统选择[官方安装说明](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)中的受支持渠道；Debian 系统使用 GitHub CLI 官方 APT 源与签名 keyring，再运行 `sudo apt update && sudo apt install gh`，不得从不明来源下载二进制或跳过包签名校验。没有管理员权限时，可从[官方 release](https://github.com/cli/cli/releases)取与平台匹配的预编译包，在用户目录安装；安装前按该 release 发布的 SHA-256 校验值核验文件，并把版本化安装目录加入用户 PATH，不覆盖系统路径。

GitHub 凭证由 `gh` 的系统安全凭证存储管理，与 DSH Credentials 插件分开；不得通过 `credential_manage` 读取、写入或迁移 GitHub token。只有用户明确要求或确认初始化 GitHub 登录后，才检查目标主机的 Linux Secret Service。

不得在 workspace-write 沙箱中执行 GitHub 凭证预检、发起 `gh auth login` 或 `gh auth refresh` 的设备授权；先切换到目标主机、运行 `gh` 的同一 Unix 用户上下文，并以 `danger-full-access` 执行且经批准。若无法获得该执行权限，停止并请用户在目标主机终端执行，不要先在沙箱里发起授权链接。

先在目标主机、运行 `gh` 的同一用户会话中复用该会话里由 PAM 解锁的 Secret Service，并查询默认 collection 的 `Locked` 属性。若该进程没有 D-Bus 环境变量但目标用户总线 socket 存在，临时使用 `XDG_RUNTIME_DIR=/run/user/$(id -u)` 与 `DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus` 连接同一用户总线。若 Secret Service 未运行，先尝试运行 `gnome-keyring-daemon --start --components=secrets` 连接或启动该会话服务，再重新查询；该命令不解密真正锁定的 collection。`b false` 表示未锁定，`b true` 表示仍锁定；命令退出码为 0 或出现 `SSH_AUTH_SOCK` 都不能代替状态复核。若 D-Bus 不可达或 collection 仍锁定，不发起授权链接。

`busctl --user call org.freedesktop.secrets /org/freedesktop/secrets org.freedesktop.Secret.Service ReadAlias s default` 返回默认 collection 对象路径；把该路径传给 `busctl --user get-property org.freedesktop.secrets <对象路径> org.freedesktop.Secret.Collection Locked` 检查状态。

若自动连接或启动后 collection 仍锁定，由 agent 提示用户在目标主机终端一次性粘贴并运行以下命令；密码仅在本地提示中输入，可能是 keyring 密码，不得要求用户把密码发给 agent：

```bash
set -o pipefail
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemd-ask-password 'Unlock GNOME Login keyring' |
  env DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
      XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
      gnome-keyring-daemon --unlock
```

无论 keyring 起初已解锁还是用户执行了解锁命令，agent 都必须在发起授权前确认默认 collection 的 `Locked` 属性为 `b false`，并以新的临时属性名及无敏感内容的临时值完成 Secret Service 写入、读取与删除测试；不得将真实 token 用作测试值。若 `secret-tool` 不存在，停止并先按执行入口步骤 7 征求安装工具的同意。

```bash
set -eu
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
probe="gh-preflight-$(date +%s)-$RANDOM-$RANDOM"
trap 'secret-tool clear dsh-preflight "$probe" >/dev/null 2>&1 || true' EXIT
printf '%s' 'temporary-test-value' | secret-tool store --label='gh storage check' dsh-preflight "$probe"
test "$(secret-tool lookup dsh-preflight "$probe")" = 'temporary-test-value'
secret-tool clear dsh-preflight "$probe" >/dev/null
trap - EXIT
```

用户执行解锁命令后，退出码为 0 不算成功，必须重新查询状态。若仍锁定、Secret Service 不可达或往返测试失败，停止授权流程，不尝试猜测密码或重置 keyring。

确认安全凭证存储可用后，由 agent 运行 `gh auth login --hostname github.com --git-protocol https --web` 发起设备授权；若账号已用明文存储且用户要转入安全存储，运行 `gh auth refresh --hostname github.com` 重新授权，默认保留现有 scopes。若命令输出设备验证 URL 与一次性代码，agent 将两者提供给用户，并请用户在 GitHub 页面输入代码、完成授权。agent 等待用户确认后继续读取该进程结果，再用 `gh auth status` 核实目标账号及认证来源为 `keyring`。不得要求用户提供 GitHub 密码、token 或私钥。gh 在安全凭证存储不可用时可能退回明文文件；若凭证仍回退到 `~/.config/gh/hosts.yml` 等明文文件，立即停止，不继续用于 Git 操作，并运行 `gh auth logout --hostname github.com --user <账号>` 删除本地凭证。`gh auth logout` 不会撤销 GitHub 侧 OAuth 授权；远端撤销可能影响同一 GitHub CLI 应用的其他会话，需单独评估。

仅当本次 GitHub HTTPS 操作需要 gh credential helper 且用户明确要求或确认修改 Git 配置时，运行 `gh auth setup-git`，并检查 `git config --show-origin --get-all credential.helper` 确认配置落在预期的 Git 配置层。不得使用 `credential.helper store` 保存认证信息，因为它会以明文写入磁盘。

用户明确要求将 GitHub CLI 默认 Git 协议设为 SSH 时，运行 `gh config set git_protocol ssh --host github.com`；随后用 `gh config get git_protocol --host github.com` 核实配置值。该设置影响 GitHub CLI 生成或选择的 Git remote URL，不会把现有仓库的 remote 自动改写。

用户要求使用 GitHub SSH remote 时，先在实际执行 Git 操作的环境运行 `ssh -T git@github.com`，确认响应问候中的账号与预期账号一致；SSH 测试可能在认证成功时仍以非零退出码结束，应以认证问候判定，不单看退出码。若 SSH 身份不存在或账号不符，先停下并向用户说明；生成密钥或将公钥添加到 GitHub 账户前须取得用户确认，绝不读取、输出或传输私钥。SSH 登录只确认 GitHub 账号身份，不证明该账号能访问目标仓库；需要验证仓库读取权限时，在目标仓库运行 `git ls-remote <SSH_REMOTE> HEAD`。读取成功不能证明写入权限。

仅当本次操作需要验证已确认的 GitHub HTTPS remote 时，才在目标仓库运行 `GIT_TERMINAL_PROMPT=0 git ls-remote <HTTPS_REMOTE> HEAD` 验证非交互式读取；若要确认写入权限，另按用户明确授权的目标做临时分支写入与删除，并复核分支确已删除。读取成功不能证明写入权限。

## 策略优先级与范围

先遵循用户对本次操作的明确要求，再遵循目标项目当前的分支、提交、审查与发布约定；本 skill 只补充其未规定的通用逻辑。不得借通用流程覆盖项目特定策略。此 skill 不决定版本号语义、发布审批或项目验收标准；这些应从目标项目的当前权威资料中取回。
