# 部署 home-media-pilot：拉镜像，不在部署机构建

需要在 Unraid 或有 Docker 的设备上部署或升级 home-media-pilot 时读这篇。它给出部署机上的完整做法与 Compose 配置全文，使 agent 无需回工程取配置即可完成部署。

## 部署机制

部署机只从 GHCR 拉取 CI 已构建的镜像，**不构建镜像**。镜像由工程的发布工作流在推送到 GitHub 后产出，其自身在构建阶段产出前端产物——因此部署机上不需要 Node，也不需要克隆源码树。

这条约束的理由是结构性的：在部署机上改动源码会让该机的迁移链与代码偏离上游，下一次拉取官方镜像时，数据库版本可能超出镜像所知的迁移头，容器随即启动失败。**要改代码就在工程仓库改并推送，等 CI 出镜像后再拉**。

Unraid 上也没有可用的构建条件：`/usr/bin/node` 是 v14 且没有 `npm`，前端产物无法在部署机上生成。

## 前置条件

- 部署机能访问 `ghcr.io`。
- 该包是 private，匿名拉取会被拒绝，部署机上须持有 `read:packages` 的 GitHub 凭据并完成 `docker login ghcr.io`。凭据形态是硬约束：GitHub Packages 只接受 personal access token (classic)，fine-grained token 不被支持；只要读权限时用 `https://github.com/settings/tokens/new?scopes=read:packages` 直接建。依据见 [Working with the Container registry 的 Authenticating 一节](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。
- 主机上存在 Compose 要引用的外部 Docker 网络（`scraping_server_default`）；不用则删掉该网络与 `METATUBE_URL`。

镜像标签见工程的 `.github/workflows/publish-container.yml`：`main` 跟随 main 分支，`vX.Y.Z` 对应版本 tag，`sha-<short>` 对应提交。

## Compose 配置全文

Unraid 上存为 `/boot/config/plugins/compose.manager/projects/home-media-pilot/docker-compose.yml`（Compose Manager 的项目文件）；其它设备存为任意目录下的 `docker-compose.yml`。

```yaml
name: home-media-pilot

networks:
  scraping_server_default:
    external: true

services:
  pilot:
    image: ghcr.io/yunjies/home-media-pilot:main
    container_name: home-media-pilot
    restart: unless-stopped
    labels:
      net.unraid.docker.webui: "http://[IP]:[PORT:8000]/"
      net.unraid.docker.icon: "https://raw.githubusercontent.com/yunjies/Home-Media-Pilot/main/frontend/public/favicon.svg"
    # Only deployment invariants belong here. Libraries and provider endpoints
    # are persisted in Pilot and are changed through its API/UI without a
    # restart.
    environment:
      DATABASE_URL: sqlite:////app/data/home_media_pilot.db
      CORS_ORIGINS: http://192.168.1.217:18081
      MEDIA_READ_ONLY: "true"
      DOWNLOADS_READ_ONLY: "true"
      LOGICAL_PATHS: '{"电影":"/media/电影","电视剧":"/media/电视剧","节目":"/media/节目","动漫":"/media/动漫","特摄":"/media/特摄","xoxo":"/xoxo"}'
      MEDIA_ROOT: /media
      DOWNLOADS_ROOT: /downloads
    ports:
      - "18081:8000"
    volumes:
      - /mnt/user/appdata/home-media-pilot/data:/app/data
      - /mnt/user/Videos:/media:ro
      - /mnt/user/downloads:/downloads:ro
      - /mnt/user/KeepOut:/xoxo:ro
    networks:
      - scraping_server_default
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
```

四项随主机而异，按现场改：

- **`CORS_ORIGINS`**：填实际访问 WebUI 的地址（含端口）。不填则只允许 `localhost:5173` 与 `127.0.0.1:5173`，从别的机器访问时页面能打开但接口被拦。
- **`LOGICAL_PATHS`**：填主机上真实的逻辑根路径到容器内物理路径的映射。
- **`volumes` 的后三项**：填主机上真实的媒体、下载与受限目录路径。三项都以 `:ro` 挂载，与 `MEDIA_READ_ONLY`／`DOWNLOADS_READ_ONLY` 一致。
- **`networks`**：`scraping_server_default` 须是主机上已存在的 Docker 网络。

## 部署与升级

改动数据库前先备份它——`home_media_pilot.db` 是唯一无法从镜像重建的资产：

```bash
cp /mnt/user/appdata/home-media-pilot/data/home_media_pilot.db \
   /mnt/user/appdata/home-media-pilot/backups/home_media_pilot.db.before-$(date +%Y%m%d-%H%M%S)
```

升级只做拉取与重建容器，不构建：

```bash
cd /boot/config/plugins/compose.manager/projects/home-media-pilot
docker compose pull
docker compose up -d
```

Unraid 上也可以用 Compose Manager 界面的 Pull 与 Up。

## 验证

依次确认三项，全部通过才算部署成功：

1. 容器健康检查为 `healthy`：`docker ps --filter name=home-media-pilot` 的状态列。
2. 服务应答：`curl http://<主机IP>:18081/health` 返回 `{"status":"ok","service":"home-media-pilot"}`。
3. 数据可读：`curl http://<主机IP>:18081/media-libraries` 返回既有的媒体库条目。

确认这次升级是否真的换上了新代码，看 `curl http://<主机IP>:18081/version`：版本号取自镜像内 `/app/pyproject.toml` 的 `project.version`，**在运行时解析**，因此它反映的是这个镜像里声明的版本。同一版本号的连续两次发布分辨不出差别时（版本未 bump），改看镜像 ID 而非版本号：`docker image inspect ghcr.io/yunjies/home-media-pilot:main --format '{{.Id}}'` 在 `pull` 前后是否变化。WebUI 左下角（左侧栏底部）显示的就是这个版本，取回失败时该处不渲染。

启动失败时看 `docker logs home-media-pilot`。**数据库版本超出镜像所知的迁移头**时，日志里是 `alembic.util.exc.CommandError: Can't locate revision identified by ...`，容器退出——此时把该库的 `alembic_version` 改到镜像迁移链的头再重启（表结构与数据保留，超出那部分的迁移所加的功能不可用）。镜像的迁移头取 `docker run --rm --entrypoint sh <镜像> -c "ls /app/src/migrations/versions/"`。

## 数据持久化

`DATABASE_URL` 指向 `/app/data/home_media_pilot.db`，必须把该路径挂到主机目录（上面的 `volumes` 首项即是）。不挂则 sqlite 落在容器内，容器重建即清空。

## 适用范围

- **成立**：x86_64 主机（镜像目标为 `linux/amd64`，发布工作流未声明 `platforms`，取 GitHub runner 架构）。
- **失效**：`arm64` 等其它架构（当前只产出 amd64）；仅需本地开发栈（用工程内的 `docker-compose.yml`，那是绑定 localhost 的开发栈，不是部署栈）。
