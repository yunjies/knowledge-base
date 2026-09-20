# 部署 home-media-pilot：先选路线，再照做

需要在 Unraid 或有 Docker 的设备上部署 home-media-pilot 时读这篇。它给出两条路线各自的做法与 Compose 配置全文，使 agent 无需回工程取配置即可完成部署。

## 先选路线

| | 路线 A：拉已发布镜像 | 路线 B：在部署机上从源码构建 |
|---|---|---|
| 前提 | 持有 `read:packages` 的 GitHub 凭据 | 无需凭据 |
| 部署机需要 | 能访问 `ghcr.io` 并 `docker login` | 能访问 Docker 镜像仓库（构建时拉 `node:22-alpine`、`python:3.13-slim`） |
| 耗时 | 只下载镜像 | 每次部署都要构建 |
| 适合 | 常规部署、要跟随已发布版本 | 无法持有凭据，或要改源码 |

两条路都**不需要**预先准备前端产物，也**不需要**在部署机上装 Node——前端由镜像自己在构建阶段产出。

选定后照对应小节做。下面的 Compose 片段可直接用。

## 路线 A：拉已发布镜像

发布工作流推 `ghcr.io/yunjies/home-media-pilot`，标签为 `main`（跟随 main 分支）、`vX.Y.Z`（版本 tag）与 `sha-<short>`。

**该包是 private，匿名拉取会被拒绝**：实测匿名换取拉取令牌即返回 `401 UNAUTHORIZED`。所以每台设备上都先登录：

```bash
# 凭据是 classic PAT，scope 至少含 read:packages
export CR_PAT=<你的 token>
echo "$CR_PAT" | docker login ghcr.io -u <你的 GitHub 用户名> --password-stdin
```

**凭据形态是硬约束**：GitHub Packages 只接受 personal access token (classic)，fine-grained token 不被支持。classic UI 里勾 `write:packages` 会连带勾上权限过宽的 `repo`；只要读权限时用 `https://github.com/settings/tokens/new?scopes=read:packages` 直接建。依据见 [Working with the Container registry 的 Authenticating 一节](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。

Compose 里**去掉 `build:` 段，只留 `image:`**——两者同存时 Compose 仍会构建，与"只拉不建"的意图相反。仍以 Unraid 的 Compose Manager 项目文件为例：

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
    environment:
      # 与路线 B 的 environment 逐项相同
    ports:
      - "18080:8000"
      - "18081:8000"
    volumes:
      # 与路线 B 的 volumes 逐项相同
    networks:
      - scraping_server_default
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
```

`environment` 与 `volumes` 照抄路线 B 的全文中对应两段；那两项随主机而异，两路线通用。

启动与拉取：

```bash
docker compose pull
docker compose up -d
docker compose ps
```

不要把发布工作流里的 `GITHUB_TOKEN` 拿来用：它短时效且仅限 Actions 内部，设备侧拉取必须另建 PAT。

## 路线 B：在部署机上从源码构建

把仓库克隆到部署机：

```bash
mkdir -p /mnt/user/appdata/home-media-pilot
git clone https://github.com/yunjies/home-media-pilot.git \
  /mnt/user/appdata/home-media-pilot/project
```

该目录必须含 `docker/`、`src/`、`pyproject.toml`、`uv.lock`——镜像构建的上下文就是它，克隆完整即满足。

### Compose 配置全文

Unraid 上存为 `/boot/config/plugins/compose.manager/projects/home-media-pilot/docker-compose.yml`（Compose Manager 的项目文件）；其它设备存为任意目录下的 `docker-compose.yml`。

```yaml
name: home-media-pilot

networks:
  scraping_server_default:
    external: true

services:
  pilot:
    build:
      context: /mnt/user/appdata/home-media-pilot/project
      dockerfile: docker/api.Dockerfile
    container_name: home-media-pilot
    restart: unless-stopped
    labels:
      net.unraid.docker.webui: "http://[IP]:[PORT:8000]/"
    environment:
      APP_ENV: nas-readonly
      APP_LOG_LEVEL: INFO
      DATABASE_URL: sqlite:////app/data/home_media_pilot.db
      CORS_ORIGINS: ${CORS_ORIGINS}
      MEDIA_READ_ONLY: "true"
      DOWNLOADS_READ_ONLY: "true"
      MEDIA_ROOT: /media
      MOVIES_ROOT: /media/电影
      TV_ROOT: /media/电视剧
      LOGICAL_PATHS: '{"电影":"/media/电影","电视剧":"/media/电视剧","节目":"/media/节目","动漫":"/media/动漫","特摄":"/media/特摄","xoxo":"/xoxo"}'
      DOWNLOADS_ROOT: /downloads
      METATUBE_URL: http://metatube-server:8080
      JELLYFIN_URL: ${JELLYFIN_URL}
      MEDIA_LIBRARIES: '{"电影":{"paths":["电影"],"metadata_provider":"tvmaze","subtitle_provider":"opensubtitles"},"节目":{"paths":["电视剧","节目"],"metadata_provider":"tvmaze","subtitle_provider":"opensubtitles"},"动漫&特摄":{"paths":["动漫","特摄"],"metadata_provider":"tvmaze","subtitle_provider":"opensubtitles"},"xoxo":{"paths":["xoxo"],"metadata_provider":"metatube","subtitle_provider":"opensubtitles"}}'
    ports:
      - "18080:8000"
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

- **`CORS_ORIGINS`**：填你实际访问 WebUI 的地址（`18080` 与 `18081` 两个端口的来源地址）。不填则只允许 `localhost:5173` 与 `127.0.0.1:5173`，从别的机器访问时页面能打开但接口被拦。
- **`JELLYFIN_URL`**：填 Jellyfin 的地址。
- **`volumes` 的前三项**：填主机上真实的媒体、下载与受限目录路径。
- **`networks`**：`scraping_server_default` 须是主机上已存在的 Docker 网络，Metatube 等外部服务接在同一网络里；不用则删掉该网络与 `METATUBE_URL`。

### 构建并启动

Unraid 用 Compose Manager 界面的 Up，或：

```bash
cd /boot/config/plugins/compose.manager/projects/home-media-pilot
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 pilot
```

就绪后经 `http://<主机IP>:18080/` 或 `18081` 访问 WebUI（Unraid 的 Docker 页也有 WebUI 按钮指向 `8000`）。

## 数据持久化（两条路线都要）

`DATABASE_URL` 指向 `/app/data/home_media_pilot.db`，必须把该路径挂到主机目录（上面的 `volumes` 首项即是）。不挂则 sqlite 落在容器内，容器重建即清空。

## 适用范围

- **成立**：x86_64 主机（镜像目标为 `linux/amd64`，发布工作流未声明 `platforms`，取 GitHub runner 架构）。
- **失效**：`arm64` 等其它架构（当前只产出 amd64）；仅需本地开发栈（用工程内的 `docker-compose.yml`，那是绑定 localhost 的开发栈，不是部署栈）。
- **命名耦合**（仅路线 B）：`build.context` 的主机路径、`dockerfile: docker/api.Dockerfile`、Compose Manager 的项目文件名，三者须一致；改动任一处要同步改另两处。
