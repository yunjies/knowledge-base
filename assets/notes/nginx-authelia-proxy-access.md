# proxy 上的 Nginx + Authelia 认证入口设计与部署

需要在家庭网络的 proxy 上为经 HTTPS 暴露的 DSH Web 加认证时读本文；它记录 Nginx、Authelia、TLS、反代与放行例外之间的现行关系，以及如何核对部署。本文只适用于当前 DSH 服务入口，不是所有 Nginx 服务的通用认证模板。

## 设计边界

浏览器访问 `https://<域名>:<公开入口端口>/` 时，流量经网关端口转发到 proxy 的 Nginx；Nginx 将普通 DSH 页面请求交给仅绑定 loopback 的 Authelia 授权端点检查。未认证请求收到 Authelia 的重定向并前往同一 HTTPS authority 下的 `/authelia/` 登录；认证通过后，Nginx 将请求反代到 DSH Web，并把 Authelia 返回的用户、组、姓名和邮箱响应头传给上游。Authelia 用户认证采用文件后端，访问策略由其配置中的 access-control 决定。

Authelia Portal 路径必须能直接访问认证服务，因而 `/authelia/` 不经过自身的 `auth_request`；内部授权子请求用精确路径且标为 `internal`，外部客户端不能直接调用。当前 `/plugins/` 也绕过 `auth_request`，是为避免不可变的 DSH client bundle 请求触发 Authelia 431 响应；这条路径是公开静态资源例外，不能把它误当作已认证内容。若该路径以后承载私密或按用户授权的内容，必须移除此旁路或改用可证明安全的认证传递方案。

Authelia 仅监听 proxy 的 loopback 地址，Nginx 是该认证服务的 HTTP 接入点。外部 TLS 在 Nginx 终止，Portal 和授权子请求由 Nginx 转发到本机 Authelia。实际访问 authority、cookie 域、回跳 URL、Nginx 的 `server_name` 与证书必须相互对应；部署时从当前配置取值，不能把下文示例中的路径和端口照搬到不同域名环境。

## 当前配置事实源

- Nginx 生效配置：proxy 上的 `/etc/nginx/conf.d/<DSH入口配置>.conf`；包含顺序取 `/etc/nginx/nginx.conf` 的 `include`。用 `sudo nginx -T` 查看合并后的生效配置，不从备份文件推断当前行为。
- Authelia 部署定义：`/opt/authelia/compose.yml`；运行配置：`/opt/authelia/config/configuration.yml`；文件用户库：`/opt/authelia/config/users_database.yml`。
- Authelia 的 JWT、会话与存储加密密钥由 `/opt/authelia/secrets/` 下独立文件提供。数据库、用户库、通知文件与密钥均属于运行数据或敏感材料，不复制到知识库、命令记录或提交内容。
- Authelia 容器持久化数据目录与监听映射，以 Compose 文件及 `docker inspect authelia` 的实时结果为准；不要仅凭容器名称判断健康状态。
- TLS 证书与私钥路径从 Nginx 生效配置取回；私钥内容不得读取或记录。

## 请求路由与信任关系

1. **授权子请求**：`location = /internal/authelia/authz` 设为 `internal`，把 Nginx 的原始方法、完整原始 URL 和客户端地址转发到 Authelia 的 `/api/authz/auth-request`，并关闭请求体转发。Authelia 的 2xx 表示放行，401 由主 location 转为指向 `$upstream_http_location` 的 302。
2. **登录 Portal**：`/authelia` 规范化重定向至 `/authelia/`；`/authelia/` 转发到 Authelia 服务，传递 Host、原始 URL、scheme、host、URI 与客户端地址等头部。Portal 本身不能再要求相同的授权子请求，否则会形成认证死循环。
3. **DSH 主应用**：其余路径执行 `auth_request`，随后反代至本机 SSH 隧道端点 `127.0.0.1:<隧道端口>`。该隧道把请求送往 VM 内的 DSH Web 监听端口；隧道两端的实际转发关系从运行中的 SSH 进程与服务配置复核。
4. **身份头部**：Nginx 从 Authelia 授权响应读取 `Remote-User`、`Remote-Groups`、`Remote-Name`、`Remote-Email`，再设置同名上游请求头。上游只有在可信任该 Nginx 注入、且不能被客户端直接访问绕过 Nginx 时，才能把这些头当作认证身份。部署或改动后检查客户端传入的同名头是否会原样穿透；必须由 Nginx 覆盖身份头，不能信任客户端自报值。
5. **静态插件资源**：`/plugins/` 单独反代到隧道端点且不做授权，配置里说明其为静态 bundle 例外。保持资源确实可公开这一前提；新增入口或插件若涉及私有资源，按认证边界重新设计。
6. **WebSocket**：主应用保留 Upgrade/Connection 转发与长读写超时；认证需要对建立连接时的请求生效。修改 WebSocket 路由时同时验证普通页面、API 与 WebSocket，不能只以首页可打开作为验收。

## 部署与变更步骤

以下操作在 proxy 上执行。改动前先备份将要编辑的 Nginx 或 Authelia 文件，备份不得包含或暴露密钥；不在知识库保存备份副本。先阅读现行配置再改，不用旧备份覆盖当前状态。

1. **取回运行输入**：通过 `sudo nginx -T` 查看 Nginx 合并配置；通过 `/opt/authelia/compose.yml`、`/opt/authelia/config/configuration.yml` 查看 Authelia 服务定义与认证策略。账号由文件用户库管理，密钥由 Compose 引用的 secret files 提供；不要把用户密码、密码哈希、secret 值或 cookie 写入 shell 历史、工单或本文。
2. **改 Authelia 配置时先校验**：在 `/opt/authelia` 目录执行 `docker compose config -q` 检查 Compose 语法；再按当前镜像版本支持的方式校验 Authelia 配置。只有校验通过后才重建或重启 Authelia 服务。不要把更新镜像版本与认证配置变更混在一次未验证的操作中。
3. **改 Nginx 配置时先校验再 reload**：执行 `sudo nginx -t`；成功后执行 `sudo systemctl reload nginx`。reload 失败时保留现场日志并恢复本次备份，不能先覆盖后再猜测配置。
4. **用户管理**：文件后端的用户记录应由 Authelia 支持的密码哈希生成流程维护；权限保持仅管理员可读。不得在文档中存放真实凭据或可复用的哈希。首次登录和改密后都要验证原账户失效、新账户可用。
5. **网关入口**：如果新增或更换 WAN 入口，在 OpenWrt 将对应外部端口转发至 proxy 对应监听端口，并从外网实际验证。网关端口映射的通用拓扑与逐段测试见[家庭网络服务暴露笔记](home-network-service-exposure.md)。

## 验收与定位

每次部署、升级或认证配置变更后按请求链路验收，所有探测都不得包含真实密码或 session cookie：

- `sudo nginx -t` 成功，且 `sudo nginx -T` 显示目标 server、Portal、auth subrequest、主应用、插件例外都来自当前生效文件。
- 在 proxy 上检查 Authelia 容器状态与日志，确认服务监听仅在预期 loopback 地址，并核实其只读 secret 挂载；命令与属性以 `docker ps`、`docker inspect authelia` 的现场输出为准。
- 未登录访问 DSH 主页面应跳转到该 authority 的 `/authelia/`；完成登录后页面可用。用无效账号登录应失败；用户文件中不应有明文密码。
- `/plugins/` 静态 bundle 未登录时仍可获取，这是显式例外；应单独核对该路径返回内容仅是公开 client bundle。
- 验证 DSH API 与 WebSocket 在登录态下可用，并确认伪造 `Remote-User` 等头部不能改变上游看到的认证身份。
- 从 LAN 与真实外网分别访问。若本机直连 Nginx 与 Authelia 均正常但外网失败，检查网关转发；若 Portal 加载失败，先检查 Authelia 健康、Portal location 与 cookie domain/URL 是否一致；若登录后主应用报错，检查 auth 响应码、回跳地址、隧道目标及 Host/Origin 转发。

只看到 `nginx -t` 成功只能证明配置语法可解析，不能证明登录、访问控制、身份头或外网链路正确。可观测的完整验收必须同时覆盖未认证拒绝/跳转、有效登录放行、无效凭据拒绝、静态资源例外和已认证 API/WebSocket。

## 回滚与升级

回滚只恢复本次修改前备份的对应配置文件；先运行 `sudo nginx -t`，通过后再 reload。Authelia 配置回滚后按 Compose 约定重启对应服务并重新验收登录。密钥、数据库和用户库是独立运行数据，不随配置回滚覆盖；恢复这些数据属于单独的数据恢复操作，先确认备份和一致性，不执行盲目删除或替换。

升级 Authelia 镜像前核对当前镜像版本与配置选项兼容性，保留数据库与配置备份，先在可回滚条件下升级，再执行完整验收。Authelia 或 Nginx 重大变更若取消了上述认证边界，必须重新审视 Portal 自我依赖、静态资源例外、身份头信任链与上游可达性。

## 适用范围与尚未证明面

本文描述的是现场 proxy 上 Nginx + Authelia 为 DSH Web 提供的当前认证入口设计与配置取回路径。它不代表所有域名服务都使用 Authelia，也不代表 `/plugins/` 资源受认证保护。改成子域名、不同 TLS 终止点、不同身份提供方或不同上游后，应重新验证 redirect URL、cookie 域、auth_request 路径、头部信任和网络可达性。

当前证据由 proxy 的生效 Nginx 配置、Authelia 容器定义和运行配置提供；本文没有记录真实账户和密钥。外网完整登录流程、伪造头部测试及每项 API/WebSocket 的实测结果，应在部署验收时现场执行；本文不把未执行的验证描述为已通过。
