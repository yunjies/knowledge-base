# Unraid 上的 MetaTube Server 本地运维

需要维护本地 Unraid 上的 `metatube-server` 容器、确认它当前如何运行，或排查服务端与插件之间的连接时读本笔记。本文只记录本机运维约定与事实取回路径；Unraid 上的安装步骤与插件配置步骤以 [MetaTube 官方 Unraid 部署说明](https://metatube-community.github.io/deploy/unraid/) 为准，不在此复述。

## 本地事实取回

容器是否存在、运行状态与实际名称均以 Unraid 当前 Docker 状态为准：

```bash
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
```

若该过滤条件未返回容器，使用 `docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'` 在 Unraid 上查找实际容器名与镜像，再用该名称执行后续命令。

容器发布的宿主端口与容器端口映射以运行时输出为准：

```bash
docker port <容器名>
```

容器创建参数（包括网络模式、端口、卷、环境变量）以 Docker inspect 为准；不要从网页示例或本笔记推断本地取值：

```bash
docker inspect <容器名>
```

## 服务检查与故障定位

MetaTube Server 当前实例的 `/health` 路径返回 404；应从 Unraid 主机本地用实际发布端口请求其搜索 API，端口取自上一节 `docker port` 的输出：

```bash
curl -i --max-time 20 'http://127.0.0.1:<宿主端口>/v1/movies/search?q=test&fallback=true'
```

HTTP 200 只证明搜索 API 返回响应；还须确认返回数据能被调用方解析，不能把 HTTP 状态单独当作 HMP 接入成功。

若请求失败，先查看容器日志与状态，再核对容器监听端口和发布映射：

```bash
docker logs --tail 200 <容器名>
docker inspect <容器名>
```

若主机本地请求成功、插件侧仍无法连接，应从插件配置中读取当前填写的服务端地址，并核对该地址从插件所在网络是否可达；主机本地成功不证明客户端网络路径可达。

遇到手动识别时预览图无法加载，应分别验证服务 API 与图片请求，并检查客户端是否要求 HTTPS；官方说明记载了其 Unraid 部署形态未启用 HTTPS 时的预览限制，具体排查入口见[官方说明](https://metatube-community.github.io/deploy/unraid/)。

## 维护边界

本笔记不冻结本地容器名、镜像标签、端口、数据库 DSN、数据目录或插件端点；这些值可能因 Unraid 配置变动，以 Docker 当前配置和实际请求结果为准。

对容器进行重建或调整持久化设置前，先从 `docker inspect <容器名>` 确认数据库模式与数据挂载，并按本机备份策略保护持久化数据；不要仅凭容器可启动就判断数据已持久化。

## 适用范围

- **成立**：MetaTube Server 由 Docker 容器运行在本地 Unraid 主机上，且操作者能在该主机执行 Docker 命令。
- **失效**：服务迁移到其他主机、改用非 Docker 部署，或 Unraid 不再承载该服务；此时应以新部署环境的事实源重新建立运维说明。
