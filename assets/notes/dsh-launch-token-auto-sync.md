# DSH 启动 Token 自动同步方案报告

需要在 DSH Web 前使用 Nginx 反向代理、且首次访问需要取得当前启动实例的 launch token 时，本文可作为部署设计参考。以下版本与验证结论是本次部署报告所记录的状态，不是对后续运行现场的保证；重新部署或升级后，应从服务日志和运行配置取回当前事实。

## 目标与适用范围

目标是在 DSH 每次启动后，将本次启动生成的 launch token 同步到反向代理，并让没有 DSH 认证 cookie 的浏览器首次访问首页时自动完成 token 引导。此设计只适用于 DSH Web 经 Nginx 反代的请求链路；它不替代反向代理上的 Authelia 校验，也不应扩大为对其他路径或已认证浏览器注入 token。

## 方案结构

DSH 所在主机的 systemd 服务通过 `ExecStartPost` 钩子读取当前服务 invocation 对应的 journal，从启动日志提取本次 launch token，再通过已有 SSH 身份调用反向代理主机上的更新脚本。提取逻辑必须限定在当前 invocation，避免误取前次启动的 token。

反向代理主机的更新脚本验证输入 token，原子替换 Nginx map 文件，并执行 `nginx -t`。配置检查通过后才 reload Nginx；更新失败时恢复旧 map，避免把无效配置留在生效链路中。

Nginx 用 `map` 检查请求方法与 DSH cookie，仅对没有 DSH cookie 的首页 `GET /` 注入 token。Authelia 认证校验继续生效，其他路径沿用原有反代与认证配置。应将 token 当作敏感凭据处理，不写入知识库、普通日志或公开响应以外的路径。

## 部署位置

本次报告记录的主机和文件位置如下；部署前应在目标主机现场核对文件是否仍存在以及是否仍被 systemd/Nginx 引用：

- DSH 主机 `/usr/local/sbin/dsh-publish-token-to-proxy`：发布启动 token 的脚本。
- DSH 主机 `/etc/systemd/system/deepseek-harness.service.d/20-dsh-token-publish.conf`：systemd 启动后钩子配置。
- 反向代理主机 `/usr/local/sbin/dsh-update-token-map`：验证 token、更新 map、检查配置及失败恢复脚本。
- 反向代理主机 `/etc/nginx/snippets/dsh-token-bootstrap.location.conf`：首页 token 引导规则。
- 反向代理主机 `/etc/nginx/conf.d/00-dsh-launch-token-map.conf`：承载 token map 的配置文件。
- 部署文件副本保存在 `deploy`；具体文件清单以该目录当前内容为准。

## 本次记录的版本与验证

本次部署报告记录的 DSH 日志版本为 `0.2.1-alpha.1`，与此前提到的 `0.2.0-rc.2` 不同。后续使用时应以当前服务启动日志中的版本为准，不从本段推断升级状态。

本次报告记录的验证结果为：DSH 与 Nginx 服务处于 active 状态；启动钩子成功同步 token；Nginx map 已写入 token 且权限为 `600`；`nginx -t` 检查通过。完整验证应从服务日志确认钩子读取了当前 invocation 的 token，并从浏览器分别验证无 DSH cookie 的首页 GET 获得引导、已有 DSH cookie 时不注入、Authelia 仍执行认证、其他路径行为不变。

报告还记录了一次启动故障：DSH 主机上有遗留进程占用监听端口，导致 systemd 新实例启动失败。确认进程命令与目标服务一致后清理遗留进程，随后由 systemd 正常启动实例。此记录不是通用清理指令；遇到端口占用时先核实进程归属，不能仅凭端口号终止进程。

同一运行日志还报告 `dsh-codex-subscription` 插件版本不兼容及 `dsh-workbench` 导入失败；这两项不等同于 DSH 服务启动失败，也不由 token 同步方案修复。遇到此类问题，应分别从当前插件兼容性与导入日志排查。

## 风险边界与验收

最强反题是：从启动日志解析 token 会依赖日志格式与 invocation 过滤正确性；若上游改变日志格式、token 输出位置或 cookie 语义，脚本可能无法提取新 token，或错误复用旧 token。证伪条件是新启动后发布内容与本次启动 token 不一致，或者有 DSH cookie 的请求仍收到 token 引导。发生任一情况即视为方案失效，暂停依赖自动引导并检查日志解析、map 更新和 cookie 判定。

该方案放弃了对任意路径统一注入 token 的能力，以保持 token 暴露面受限；改造或回滚的代价主要落在两台主机的启动钩子、更新脚本与 Nginx 配置上。若 token 生成方式或认证 cookie 契约改变，应重新设计并完整验证，而非仅调整日志匹配表达式。

每次变更或升级后，至少验证：

- DSH 启动钩子只读取当前服务 invocation 的启动日志，提取失败时不发布旧 token。
- 反向代理更新脚本拒绝格式错误的 token；更新失败时恢复旧 map，且 `nginx -t` 失败不会 reload。
- 配置通过后 Nginx reload 成功，token map 文件权限限制为仅必要服务身份可读。
- 无 DSH cookie 的首页 GET 可完成 token 引导；已有 DSH cookie 的首页 GET 不再注入。
- Authelia 校验仍在其原请求边界生效，非首页 GET 与其他路径不受引导规则影响。

仅有 `nginx -t` 成功不能证明启动 token 对应正确、cookie 条件正确或首次访问认证成功。报告提及的备份位置和部署时临时处置不作为长期事实；需要回滚时应从现场确认本次变更对应的备份，并先通过配置检查再 reload。
