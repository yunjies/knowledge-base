# 家庭网络的服务暴露：三段端口与逐级验证

需要把家庭内网里某个服务暴露到外网，或排查"外网访问不到"时读这篇。它给出这条链路上每一跳的地址与验证方式，使 agent 无需先摸清网络拓扑即可定位断点在哪一跳。

## 拓扑与三段端口

家庭网络里一个服务要能从外网访问，须连续穿过三段，每段各有一对端口：

1. **容器端口**：服务在容器内监听的端口（如 `8000`）。
2. **宿主端口**：容器端口映射到的部署机端口（如 `18081`）。映射关系取 `docker port <容器名>`。
3. **代理端口**：nginx 在 proxy 上对外监听的端口，转发到宿主端口。

外网流量经 openwrt 的端口转发进入 proxy 的代理端口，再由 nginx 转到部署机的宿主端口，最后进容器。三段各自独立，**任一段没通，外网就访问不到**。

设备地址（在对应机器上取回，不在此复述取值）：

- **openwrt**（网关/路由器）：LAN 侧 `192.168.1.1`，SSH 端口 `2200`。
- **proxy**（NanoPi-R2S，跑 nginx）：LAN 侧 `192.168.1.224`，其 default route 指向 `192.168.1.1`。
- **unraid**（部署机，跑 Docker）：主网口 `br0` 上 `192.168.1.217`，default route 同样指向 `192.168.1.1`。

三者同在 `192.168.1.0/24`。SSH 免密通道按 `~/.ssh/config` 里的主机名 `unraid`、`proxy`、`openwrt` 取用。

## 新增一个外网入口

按三段自内向外做，每段做完即验证，不要在没验证上一段时就做下一段。

### 第一步：容器端口与宿主端口

在部署机上确认服务已在宿主端口上应答。`HostIp` 为空表示该映射绑在宿主的所有网口上。

```bash
docker port <容器名>
```

### 第二步：proxy 上新增 server 块

在 proxy 的 `/etc/nginx/conf.d/cyclonejoker.xyz.conf` 末尾追加一个 server 块。该文件已承载全部对外服务，每个服务一个块，统一用域名 `cyclonejoker.xyz` 与该域名的证书；沿用文件中既有块的写法即可。

要点三项：

- `listen <代理端口> ssl`——该端口须是 proxy 上未被占用的端口。
- `server_name cyclonejoker.xyz`——与既有块一致。
- `location /` 里 `proxy_pass http://<部署机IP>:<宿主端口>`，并带上转发头：`X-Forwarded-Proto https`、`X-Forwarded-Port <代理端口>`、`Host $host`，以及 WebSocket 所需的 `Upgrade` 与 `Connection "upgrade"`。

代理端口是否被占用，取 `ss -tln` 在 proxy 上现查。改完先 `nginx -t` 再 reload：

```bash
nginx -t
systemctl reload nginx
```

### 第三步：openwrt 上放行

在 openwrt 的防火墙加一条端口转发，把 WAN 侧的代理端口转到 proxy 的同一端口：外部端口取代理端口，内部 IP 取 proxy 的 LAN 地址，内部端口取代理端口。

这一跳的界面操作在 openwrt 上进行；agent 侧 SSH 到 `openwrt` 时若报 `Permission denied (publickey,password)`，说明该机的免密登录未生效，须先在凭证侧修复或用密码进入。

## 逐级验证

从内向外依次取这三处的应答，三处都对才算通：

1. 部署机上：`curl http://<部署机IP>:<宿主端口>/health`——验证容器与宿主映射。
2. proxy 上：`curl -k https://127.0.0.1:<代理端口>/health`——验证 nginx 转发。**用 `127.0.0.1` 而非域名**，见下节。
3. 外网侧：`curl -k https://<域名>:<代理端口>/health`——验证 openwrt 已放行。

断点定位：第 1 处不通是容器或映射问题；第 1 处通而第 2 处不通是 nginx 配置问题；前两处通而第 3 处不通是 openwrt 未放行。

## 域名在内网会绕出 WAN

`cyclonejoker.xyz` 在内外网都解析到同一个公网地址。因此**在内网用域名访问自己的服务时，流量会先出到 WAN 再绕回 LAN**（发夹 NAT）：openwrt 未放行该端口时，从内网用域名访问会失败，而同一端口用 `127.0.0.1` 或 LAN IP 访问却是通的。

排查时因此不要用域名判断 nginx 是否配置正确——用域名测出的失败可能只反映 openwrt 未放行。内网访问直接用 `https://<proxy 的 LAN IP>:<代理端口>/`。发夹 NAT 是否被路由器支持不由本文档判定，未支持时按上句取 LAN 地址访问。

## 跨域来源须与最终访问地址一致

服务若校验 CORS 来源，其允许列表须包含**外网访问所用的那个协议与主机**。以 https 经域名访问时，允许列表里只有 `http://<部署机IP>:<宿主端口>` 是不够的——页面能打开但接口会被拦。新增外网入口后若出现"页面打开、数据加载失败"，先核对服务的 CORS 来源配置，改后须重建容器才生效。

## 改动前先备份

nginx 配置改前先备份，回滚即恢复该文件并 reload：

```bash
cp /etc/nginx/conf.d/cyclonejoker.xyz.conf \
   /etc/nginx/conf.d/cyclonejoker.xyz.conf.bak-before-<用途>-$(date +%Y%m%d-%H%M%S)
```

## 适用范围

- **成立**：家庭内网为 `192.168.1.0/24`、网关与代理分工如上、对外服务经 nginx 以端口区分的这套拓扑。
- **失效**：改用反向代理按路径或子域名区分服务（此时无"一个服务一个端口"的映射）、网络地址段变更、或代理与网关合并在同一台设备上。
