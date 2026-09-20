# 部署 home-media-pilot 到 Unraid 时，使用本文的 compose 配置

需要把 home-media-pilot 部署到 Unraid 主机时读这篇。它承载该部署的 Compose 配置全文与两处易失败点，使 agent 无需回工程取配置即可完成部署。

## Compose 配置全文

存为 `/boot/config/plugins/compose.manager/projects/home-media-pilot/docker-compose.yml`，即 Compose Manager 的项目文件。构建上下文指向主机上解包后的源码包目录：

```yaml
name: home-media-pilot

networks:
  scraping_server_default:
    external: true

services:
  pilot:
    build:
      context: /mnt/user/appdata/home-media-pilot/project
      dockerfile: docker/Dockerfile.nas-local
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

`CORS_ORIGINS` 与 `JELLYFIN_URL` 由现场环境填入：前者是两个 WebUI 端口的来源地址，后者是 Jellyfin 的地址，两者都随主机而异，故不在此写死。

## 两处易失败点

**构建上下文必须是源码包目录**。`build.context` 指向 `/mnt/user/appdata/home-media-pilot/project`，即主机上解包后的源码包路径。工程的其它 compose 都以仓库根为上下文，在 Unraid 上套用会因宿主机找不到该目录而失败。

**源码包必须含前端产物**。前端 bundle 被 `.gitignore` 排除，`git archive` 直出的归档里没有它；缺 `src/frontend/dist` 时镜像构建失败。生成含产物的源码包用 [create-nas-source-bundle.sh](../projects/home-media-pilot/home-media-pilot/docker/create-nas-source-bundle.sh)。（该路径中的 `src/frontend/dist` 是**仓库克隆内部**的 `src/`，与知识库的目录层级无关。）

## 适用范围

- **成立**：Unraid + Compose Manager，从主机上的源码包构建镜像。
- **失效**：普通 Docker 主机（用工程内的 `docker-compose.nas.yml`，它拉取已发布镜像）；仅需本地开发栈（用 `docker-compose.yml`）。
- **命名耦合**：`context` 的主机路径、镜像内文件名 `docker/Dockerfile.nas-local`、以及 Compose Manager 的项目文件名，三者与本配置的对应关系是该配置成立的前提，改动任一处须同步。
