# DSH 远程 Web Settings 持久化问题的判别原则

通过非 loopback authority 访问 DSH Web 时，若 Settings 不可用或修改刷新后消失，应先分清 Host 接受该 authority、浏览器/API 获准访问与 Settings 选择持久化位置这三件不同的事，再决定是否需要改变 Settings 自身的持久化策略。

## 适用边界

本笔记适用于页面已能通过认证访问、但 Settings 的远程持久化行为与预期不同的 DSH Web 场景；它不替代单个插件的安装、配置、验收或回滚手册。

若页面本身无法访问、API 返回授权拒绝或会话认证失败，应先处理 Host/Origin 与浏览器会话边界；调整 Settings 持久化选择不能修复这些授权失败。

## 判别与处理原则

Host 信任配置表示部署端接受某个 Web authority，不代表浏览器端已选择 Host 持久化，也不自动授予 Settings API 的访问权限。

Settings 持久化策略属于浏览器端 provider 的选择；若问题仅发生在远程页面而授权正常，应检查该 provider 是否将非 loopback authority 固定为页面内存态。

应优先使用 DSH 当前版本提供的受支持配置接口；若没有满足需求的接口，扩展范围也只应覆盖 Settings 的持久化选择，并让未受信任的 authority 保持页面内存态。

不要把远程 authority 强行归类为 Connection loopback，不要放宽 Host/Origin fence 或浏览器会话认证，也不要让一份客户端信任名单变成 API 授权旁路。

对自定义 Web profile，应确认 Connection 与 Web runtime 的 Host 信任配置没有互相矛盾；不要在多个层维护彼此独立且含义不同的“可信”列表。

## 版本复验

先运行 `dsh --version`，再对照[项目索引](../projects/README.md)中的本机版本与具体方案的兼容基线；版本不同或未记录时，不得把已有验证结果外推到目标环境。

每次 DSH 升级后，都应在隔离 Web profile 中验证至少一个真实 Settings consumer 的读写与刷新行为，并确认未受信任 authority 仍不能借此获得 Host 持久化或 API 权限。

可信 authority 插件的具体部署入口、配置、浏览器验收和回滚只以[项目部署说明](../projects/dsh-settings-trusted-authority/deploy.md)为准；组件关系与失败分支见[项目流程说明](../projects/dsh-settings-trusted-authority/feature-flow.md)。

## 决策边界

**【事实】** 目标是在不削弱 Host/API 授权的前提下，让受 Host 信任的远程页面使用持久化 Settings；Host 信任、浏览器/API 授权与客户端持久化选择是不同的控制面。

**【反题】** 若扩展把“可信”误作“loopback”或改变 API 授权边界，就会让本为 UI 持久化修复的改动扩大安全权限；独立复制共享 provider 也可能随 DSH 版本漂移。

**【证伪条件】** 若未受信任 authority 能因该修复访问原本被拒绝的 API，或受支持的 Settings consumer 在匹配版本的隔离 profile 中丢失服务、写入或刷新读回行为，就应判定方案不成立。

**【裁决】** 只在 Settings 持久化层处理远程可信 authority，并保留原 Host/Origin 与会话认证边界；若 DSH 提供官方受支持接口，优先改用该接口，若依赖独立 provider，则按具体项目兼容基线逐版本复验。

**【弃用代价】** 放弃该扩展会让可信远程页面回到 DSH 原有的持久化限制；继续维护独立 provider 则由其维护者承担服务契约审计、版本同步与浏览器回归成本。