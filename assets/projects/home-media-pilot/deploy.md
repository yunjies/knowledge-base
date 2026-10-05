# home-media-pilot 部署与使用

本文档给出在有 Docker 的常驻主机（Unraid 或其它 x86_64 设备）上部署与升级 `home-media-pilot` 的完整做法，以及在部署机上验证它、排查启动失败、判断这份做法何时不成立所需的事实。文档自带可直接使用的 Compose 配置全文与 `.env` 样板，读者不必回工程克隆取配置即可完成一次部署。

工程克隆根在下文记作 `<工程>`，即 `assets/projects/home-media-pilot/home-media-pilot/`（自带 `.git` 与远端，远端属主为 `yunjies`）。文中凡引用工程内的文件，一律写相对该克隆根的路径，读者照此定位即可，不必猜绝对位置；命令若不经 `cd` 声明工作目录，都在该目录下执行。

需要在开发机上跑那一套 PostgreSQL + API + worker + scheduler + 前端 dev server 的本地栈时，读的是工程克隆内的 `docker-compose.yml`，不是本文档——那一套绑定 localhost、用的是开发期密码，不含真实媒体路径，不是部署栈。两者的差别见[与开发栈的区别](#与开发栈的区别)。

## 部署机制

部署机只从 GHCR 拉取 CI 已构建的镜像，**不在部署机上构建镜像**。镜像由 `.github/workflows/publish-container.yml` 在推送到 GitHub 后产出；该工作流的构建步骤用 `docker/api.Dockerfile`，其第一个阶段是 `node:22-alpine`，前端产物在镜像构建内部生成。因此部署机上不需要 Node，也不需要源码树。

这条约束是结构性的，不是偏好：在部署机上改动源码会让该机的迁移链与代码偏离上游，下一次拉取官方镜像时数据库版本可能超出镜像所知的迁移头，容器随即启动失败。**要改代码就在工程仓库改并推送，等 CI 出镜像后再拉。**

主机的架构也可能让构建不可行——Unraid 上 `/usr/bin/node` 是 v14 且没有 `npm`，前端产物无法在该机上生成。判据是「部署机上能否产出前端产物」，不是「那台机器叫什么」。

镜像标签的取值规则以 `.github/workflows/publish-container.yml` 的 `docker/metadata-action` 步骤为准（`main`、版本 tag、`sha-<short>` 三档），读者从该文件现取。registry 属主同样由工作流在运行期从仓库解析得出，不在文档里写死。

## 前置条件

- 部署机是 x86_64，且已装 Docker 与 Compose v2（`docker compose` 子命令形态）。架构约束的适用边界见[适用范围](#适用范围)。
- 部署机能访问 `ghcr.io`。
- 该包是 private，匿名拉取会被拒绝，部署机上须持有 `read:packages` 的凭据并完成 `docker login ghcr.io`。凭据形态是硬约束：GitHub Packages 只接受 personal access token (classic)，fine-grained token 不被支持；只要读权限时用 `https://github.com/settings/tokens/new?scopes=read:packages` 直接建。依据见 [Working with the Container registry 的 Authenticating 一节](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。**凭据本身不入本文档，也不入任何随仓库分发的文件。**
- 若沿用下面 Compose 里的外部网络，该网络须已在主机上存在（`docker network inspect <网络名>` 能查到）；不用则连同 `METATUBE_URL` 一并删除。

## 环境信息的配置方式（`.env`）

**取值随主机而异的那些环境信息放在宿主侧的 `.env` 文件里，不放 Compose 正文里。** 这条链路是：应用自身不加载 `.env`（没有 dotenv 加载器），它只读进程环境变量——读取处见 `src/apps/api/main.py` 的 `CORS_ORIGINS`、`src/packages/infrastructure/library/roots.py` 的 `LOGICAL_PATHS`／`MEDIA_ROOT`／`DOWNLOADS_ROOT`、`src/apps/api/routes_library.py` 的 `MEDIA_READ_ONLY`／`DOWNLOADS_READ_ONLY`；`.env` 服务的是 **Compose**，由 Compose 把值注入容器环境。

Compose 有两条读 `.env` 的路径，本文档两条都用：

- **同目录的 `.env` 被自动读取，用于 Compose 文件自身的变量插值**。Compose 把 `.env` 的值替换进 `docker-compose.yml` 的 `${变量}` 位置，替换发生在 Compose 侧，不必在文件里写 `env_file:`。
- **`env_file:` 把 `.env` 整份注入容器**。用它可以省掉逐个变量写进 `environment:`，代价是容器环境里会多出该文件里的每个键。

`.env` 与 `docker-compose.yml` 同放一个目录：Unraid 上即下面那个目录，其它设备上即你存放 `docker-compose.yml` 的目录。

**`.env` 属宿主侧文件，不进镜像。** 工程克隆内把它排除在两处：`.gitignore` 排除 `.env` 与 `.env.*`（只留 `.env.example`），`.dockerignore` 同样排除，镜像构建上下文取值时出错。

```bash
REGISTRY_OWNER=<registry-owner>
HOST_PORT=<宿主端口>
HOST_IP=<部署机IP>
HOST_DATA_DIR=/<主机数据目录>/home-media-pilot
HOST_MEDIA_DIR=/<主机媒体目录>
HOST_DOWNLOADS_DIR=/<主机下载目录>
HOST_RESTRICTED_DIR=/<主机受限目录>
HOST_RESTRICTED_MOUNT_MODE=ro
MEDIA_ROOT=/media
DOWNLOADS_ROOT=/downloads
LOGICAL_PATHS={"movies":"/media/movies","tv":"/media/tv","restricted":"/xoxo"}
```

`.env` 是占位符填充的起点，不是可直接用的配置——上面的值原样通过不了部署。用前逐项按现场替换，尤其 `REGISTRY_OWNER` 与各项主机路径。

键与取值的对应用法：

- `REGISTRY_OWNER`：发布工作流在运行期从仓库解析出的属主，也是 GHCR 镜像地址的属主段。工程仓库的实际属主是 `yunjies`，这里仍按 `<registry-owner>` 占位，因为该值随仓库别名与镜像地址而变，读者应从工作流的运行输出取当前值，不从文档抄。
- `HOST_PORT`：宿主机上发布给 WebUI 的端口，容器内固定监听 8000。
- `HOST_IP`：访问 WebUI 的实际地址（含端口）里的主机部分，即 `CORS_ORIGINS` 的取值来源。**键名用英文是硬约束**：环境变量名只接受字母、数字与下划线，写成中文的键不会被 Compose 读到，`${...:-默认值}` 会静默退回默认值 `localhost`，于是从别的机器访问时页面能打开但接口被拦——那正是这一项要防的失败。不设该变量时应用只允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`。
- `HOST_DATA_DIR`、`HOST_MEDIA_DIR`、`HOST_DOWNLOADS_DIR`、`HOST_RESTRICTED_DIR`：四项主机侧目录，分别挂到容器内的 `/app/data`、`/media`、`/downloads`、`/xoxo`。数据目录可写且必须持久化；`/media` 为配置媒体库物理根的读写挂载；`/downloads` 保持只读。`/xoxo` 挂载由 `HOST_RESTRICTED_MOUNT_MODE` 控制，默认 `ro`；只有 `/xoxo` 正作为启用媒体库根且 Jellyfin sidecar 必须导出到其中时，才显式设为 `rw`，否则保持 `ro` 或删除该卷挂载。修改挂载模式须重新部署容器；这只描述配置要求，不表示任何现有主机已变更。
- `HOST_RESTRICTED_MOUNT_MODE`：`/xoxo` 卷的 Compose 挂载模式，只设为 `ro` 或 `rw`；未设置时默认为 `ro`。仅在 `/xoxo` 正配置为启用媒体库物理根且需要 sidecar 输出时设为 `rw`，不满足条件时保持 `ro` 或移除 `/xoxo` 卷。
- `MEDIA_ROOT`、`DOWNLOADS_ROOT`、`LOGICAL_PATHS`：容器内的取值，`LOGICAL_PATHS` 是逻辑根名到容器内物理路径的映射，取值须是合法 JSON 对象，逻辑根解析出的物理路径须真实存在且为目录（解析规则见 `src/packages/infrastructure/library/roots.py`）。`MEDIA_ROOT` 与 `DOWNLOADS_ROOT` 的内容对任何主机都一样，不写进 `.env` 时取 YAML 里 `${变量:-默认值}` 的默认值，部署照样成立；`LOGICAL_PATHS` 没有默认值，必须在 `.env` 里给，否则 Compose 在插值处报错并停下。

`.env.example` 与 `.env` 是两件不同用途的东西：前者是工程内的键名清单，只列非机密的开发期取值；后者是本机私有设置，不入版本库，也不得含真实凭据或真实端点（约定见 `CONTRIBUTING.md`）。

## Compose 配置全文

该文件是本文档刻意保留的可执行产物：它的取值随主机而异（主机路径、访问地址、外部网络），不在工程内，因此必须整份写在这里，不能改成取回路径。它本身不再硬写任何环境取值——`environment:` 里的每个键的取值都经 `${变量}` 从同目录 `.env` 取，取值清单即上一节。

Unraid 上存为 `/boot/config/plugins/compose.manager/projects/home-media-pilot/docker-compose.yml`（Compose Manager 的项目文件，`/boot/config/plugins/compose.manager/...` 是部署现场固有的位置，不是占位符）；其它设备存为任意目录下的 `docker-compose.yml`。两种情况都把 `.env` 放在同一目录。

```yaml
name: home-media-pilot

networks:
  scraping_server_default:
    external: true

services:
  pilot:
    image: ghcr.io/${REGISTRY_OWNER:-registry-owner}/home-media-pilot:main
    container_name: home-media-pilot
    restart: unless-stopped
    labels:
      net.unraid.docker.webui: "http://[IP]:[PORT:${HOST_PORT:-8000}]/"
      net.unraid.docker.icon: "https://raw.githubusercontent.com/${REGISTRY_OWNER:-registry-owner}/Home-Media-Pilot/main/frontend/public/favicon.svg"
    # Only deployment invariants belong here. Libraries and provider endpoints
    # are persisted in Pilot and are changed through its API/UI without a
    # restart.
    env_file:
      - .env
    environment:
      DATABASE_URL: sqlite:////app/data/home_media_pilot.db
      CORS_ORIGINS: http://${HOST_IP:-localhost}:${HOST_PORT:-8000}
      MEDIA_READ_ONLY: "false"
      DOWNLOADS_READ_ONLY: "true"
      LOGICAL_PATHS: ${LOGICAL_PATHS}
      MEDIA_ROOT: ${MEDIA_ROOT:-/media}
      DOWNLOADS_ROOT: ${DOWNLOADS_ROOT:-/downloads}
    ports:
      - "${HOST_PORT:-8000}:8000"
    volumes:
      - ${HOST_DATA_DIR:-./data}:/app/data
      - ${HOST_MEDIA_DIR:-./media}:/media:rw
      - ${HOST_DOWNLOADS_DIR:-./downloads}:/downloads:ro
      - ${HOST_RESTRICTED_DIR:-./xoxo}:/xoxo:${HOST_RESTRICTED_MOUNT_MODE:-ro}
    networks:
      - scraping_server_default
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
```

YAML 里的 `${变量:-默认值}` 是 Compose 的变量插值语法：同目录 `.env` 给了该键就用文件里的值，没给就用 `:-` 后的默认值，两者都没有则 Compose 报错并停下——它不会静默地拿一个空值去起容器。默认值只服务于「能起得来」这件事，不服务于「起对了」：`${HOST_DATA_DIR:-./data}` 之类的相对路径会落在 Compose 文件所在目录，那不是持久化该落的地方，生产部署四个主机目录都必须在 `.env` 里给全。

`env_file:` 与 `environment:` 并存时，`environment:` 的键在两者都出现时胜出。这里没有重叠：`env_file` 提供的是主机侧与容器内容器路径，`environment:` 提供的是容器内的部署不变量。

容器内的路径与端口（`/app/data`、`/media`、`/downloads`、`/xoxo`、8000）不是占位符，是镜像的契约，取值来自 `docker/api.Dockerfile` 与 `docker/api-entrypoint.sh`；`LOGICAL_PATHS` 映射到的容器内物理路径也必须是这些挂载点之下的真实目录，写别处无效。

## 部署与升级

首次部署与升级是同一条命令序列——镜像变没变由 `pull` 决定，不由操作者决定。

改动数据库前先备份它。`home_media_pilot.db` 是唯一无法从镜像重建的资产（媒体文件在主机目录里，配置在库里，而库本身只此一份）：

```bash
cp ${HOST_DATA_DIR}/home_media_pilot.db \
   ${HOST_DATA_DIR}/../backups/home_media_pilot.db.before-$(date +%Y%m%d-%H%M%S)
```

上面这段直接从 `.env` 取 `HOST_DATA_DIR`；若当前 shell 没有装载它，改写成该变量的实际取值，含义是备份 `HOST_DATA_DIR` 下的 `home_media_pilot.db`。

升级只做拉取与重建容器，不构建：

```bash
cd <存放 docker-compose.yml 与 .env 的目录>
docker compose pull
docker compose up -d
```

Unraid 上也可以用 Compose Manager 界面的 Pull 与 Up，效果相同。

容器启动时先跑 `python -m apps.api.migrate` 把数据库模式推进到迁移链表头，成功后才 `exec uvicorn` 开始服务（次序写在 `docker/api-entrypoint.sh`）。迁移失败即不提供服务——这是有意的：API 路由逐请求调 `create_all`，若不在启动时先迁移，建表就会由模型完成，schema 与迁移链的分歧随之被掩盖。

## 验证

依次确认三项，全部通过才算部署成功：

1. 容器健康检查为 `healthy`：`docker ps --filter name=home-media-pilot` 的状态列。
2. 服务应答：`curl http://<部署机IP>:<宿主端口>/health` 返回 `{"status":"ok","service":"home-media-pilot"}`；两个占位对应 `.env` 的 `HOST_IP` 与 `HOST_PORT`。
3. 数据可读：`curl http://<部署机IP>:<宿主端口>/media-libraries` 返回既有的媒体库条目。

确认这次升级是否真的换上了新代码，看 `curl http://<部署机IP>:<宿主端口>/version`：版本号取自镜像内 `/app/pyproject.toml` 的 `project.version`，**在运行时解析**，因此它反映的是这个镜像里声明的版本，不是本次操作的时间。同一版本号的连续两次发布分辨不出差别时（版本未 bump），改看镜像 ID 而非版本号：`docker image inspect ghcr.io/<registry-owner>/home-media-pilot:main --format '{{.Id}}'` 在 `pull` 前后是否变化。WebUI 左下角（左侧栏底部）显示的就是这个版本，取回失败时该处不渲染。

## 配置 TMDb 元数据 Provider

TMDb 适配器提供电影与 TV 搜索及详情端点；这是适配器的 API 能力，不是 HMP 对媒体库的 Provider 职能分配。先在部署环境为容器提供 TMDb Read Access Token：在同目录 `.env` 中设置 `TMDB_READ_ACCESS_TOKEN`，不要把令牌写入知识库、Compose 正文或提交到版本库。可按 [TMDb 应用认证说明](https://developer.themoviedb.org/docs/authentication-application) 创建与管理 token；认证能力与可用性详见 [TMDb FAQ](https://developer.themoviedb.org/docs/faq)，该服务未在此承诺 SLA。

在 WebUI 的「设置与管理台」打开 Provider Link 管理区，选择 TMDb 并创建 Link；保持官方 API Endpoint，启用 Link，并在凭据引用提示中填写 `env:TMDB_READ_ACCESS_TOKEN` 后保存。应用只接受官方 HTTPS TMDb v3 API 主机；Link 从进程环境读取该引用对应的 token，凭据不会作为 UI 响应回显。然后编辑希望使用此 Link 的特定媒体库，在媒体库编辑器中选择刚创建的 TMDb Link 并保存。每个媒体库保存的 `metadata_link_id`/ProviderLink 是用户配置的 Provider 选择；HMP 不依据媒体库名称或资源媒体类型自动分配、交换或回退到其他 Provider。TMDb 的 movie/TV 类型搜索分别调用 `/search/movie` 与 `/search/tv`，series/episode 映射为 TV；未指定类型的搜索使用有界 `/search/multi`，只保留 movie/TV 且有海报的结果。调用 TMDb 详情时须显式提供 `media_type`，数字 ID 本身无法区分电影与 TV。其他适配器仍只支持各自实际实现的 API 域，端点能力不定义 HMP 路由政策。可在 Link 行点击「测试」观察连接状态；只有目标实例显示本次验证成功，才可据此确认该实例连接测试通过。真实连接状态由操作者在目标实例验证。

持久保留 TMDb 元数据或海报须先取得覆盖持久留存用途的适用书面授权。官方 [TMDb API Terms](https://www.themoviedb.org/api-terms-of-use) 规定标准开发者 API 使用为非商业用途、缓存 TMDb 内容的期限最长六个月并要求署名。Settings Credits 显示的署名原文为：`This product uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.` 官方本地 TMDb logo 随前端提供。HMP 不核验该授权，也不执行缓存期限或到期删除；运营方负责确认书面授权覆盖持久留存并自行管理期限。

## 使用

部署完成后，业务操作都在 HTTP 接口与 WebUI 上，**配置权威在数据库而不在 Compose 文件**——媒体库、逻辑根绑定、元数据与字幕 Provider 的端点与启用状态都在应用数据库里，改它们不必重建容器。这正是上面 Compose 注释里那句话的意思：环境段里只该放部署不变量。

首次启动后按这个次序用：

1. 在 WebUI 里建媒体库：给名称、绑一个或多个逻辑根、指定元数据与字幕 Provider。可绑的逻辑根由部署环境的 `LOGICAL_PATHS` 与卷映射决定，未在映射里的逻辑根会被拒绝。
2. 对媒体库发起扫描，建立索引并落一份扫描报告。
3. 查资源清单，从清单里选一个资源发起元数据匹配，并显式选择候选列表内的候选——预览与批量刮削只创建候选会话，不写媒体目录；选择后仅在启用且配置物理根的媒体库路径创建 NFO 与海报 sidecar。电影使用 `movie.nfo`，剧集使用 `tvshow.nfo`；NFO 包含 Provider ID 与 `uniqueid`。TMDb 电影与 TV/series 导出均以 `<tmdbid>` 写入所选 TMDb 候选的规范数字 ID，并以 `<uniqueid type="tmdb">` 写入同一 ID；其他 Provider 继续使用各自的 Provider ID 元素及对应 `uniqueid` 类型。既有 NFO、poster 文件或 `folder.jpg` 会导致拒绝写入，不覆盖。写入前执行根路径、目标位置及符号链接检查，事务回滚时清理本事务创建的 sidecar；视频媒体字节不变。格式参照 [Jellyfin NFO 文档](https://jellyfin.org/docs/general/server/metadata/nfo/)。
4. 字幕搜索只列出候选，下载不在该流程内。

接口的权威定义与命令面在 `src/apps/api/` 与 `src/apps/cli/`。容器内另有 CLI 入口可用（`media-pilot`，入口声明见 `pyproject.toml` 的 `project.scripts`）：`docker exec home-media-pilot /app/.venv/bin/media-pilot --help` 列出它当前提供的命令，各命令的取值以该输出为准。

**写能力边界**：文件写入仅发生于用户显式选定元数据候选后，在启用且已配置物理根的媒体库路径下创建 NFO 与海报 sidecar；既有目标不覆盖。若 `/xoxo` 用作该输出根，Compose 挂载须配置为可写；不需要输出时保持只读或移除该卷。下载和其他通用文件写入、移动、删除及媒体变更没有可用的通用 mutation 接口，不因卷以读写方式挂入而启用。**重要残余风险**：每个 `:rw` bind mount 都授予容器进程对该挂载的整个主机目录树的 OS 层写权限；Pilot 的 sidecar 范围保护是应用层限制，不是文件名级隔离，不能阻止有漏洞或越过应用代码的进程写入挂载树中的其他文件。故 `/media:rw` 和按需启用的 `/xoxo:rw` 都有此整棵树权限；下载仍为 `/downloads:ro`。

## 本地测试与未验证的现场面

在 HMP 仓库克隆根按 [`tests/README.md`](home-media-pilot/tests/README.md) 执行 `UV_CACHE_DIR=.uv-cache uv run pytest -q`；全绿且退出码为 0 即通过。验证前端时在 `src/frontend` 执行 `npm run build`，TypeScript 检查及 Vite 构建均须成功且退出码为 0。若需复核本功能的离线覆盖，可运行：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest -q tests/src/packages/providers/metadata/test_tmdb.py tests/src/frontend/test_tmdb_credits.py tests/src/packages/application/test_metadata_exports.py tests/src/packages/frameworks/test_provider_stack_operations.py tests/src/packages/providers/test_provider_connection_status.py tests/src/apps/api/test_provider_api.py
```

这些 Provider/API 用例使用 mock；它们不证明真实服务连接、真实资源匹配或部署环境文件写入。

未验证面包括目标部署实例的 TMDb 连接测试、真实资源扫描或刮削、sidecar 写入以及 Jellyfin 导入。未来现场核验须由获准的运营方按目标实例单独执行并记录结果；上述本地证据不可替代现场结果，也不构成部署完成声明。

## 数据持久化

`DATABASE_URL` 指向 `/app/data/home_media_pilot.db`，必须把该路径挂到主机目录（上面的 `volumes` 首项即是，其主机侧取值来自 `.env` 的 `HOST_DATA_DIR`）。不挂则 sqlite 落在容器内，容器重建即清空——`up -d` 一次就把配置与扫描索引一起丢掉。

`/downloads` 保持只读挂入；配置媒体库物理根的 `/media` 保持读写挂入。`/xoxo` 默认只读，只有它正作为启用媒体库根且 Jellyfin sidecar 必须导出到其中时，才将 `.env` 中的 `HOST_RESTRICTED_MOUNT_MODE` 设为 `rw`；否则保留 `ro` 或删除 `/xoxo` 卷。检查实际 Compose 插值且尚未部署时，可在 Compose 文件所在目录运行 `docker compose config`，确认渲染的 `pilot.volumes` 中 `/xoxo` 行为 `:ro`，或仅在上述授权用途下为 `:rw`，并确认 `/media:rw`、`/downloads:ro` 与 `MEDIA_READ_ONLY=false`、`DOWNLOADS_READ_ONLY=true`；不要据此声称已改变运行中的容器。每个 RW bind mount 都给予容器进程对整棵主机挂载树的 OS 写权限，应用的 sidecar 限制不是文件名级隔离。挂载模式修改后须重新部署容器；本文档不表示 live host 已改变。此部署说明不证明任何实例已更新；当前运行实例的 sidecar 写入、资源级刮削与 Jellyfin 导入均未在此验证。

## 故障处置

启动失败时看 `docker logs home-media-pilot`。按日志形态分两类：

- **数据库版本超出镜像所知的迁移头**：日志里是 `alembic.util.exc.CommandError: Can't locate revision identified by ...`，容器退出。原因通常是该库曾被一份更新的镜像推进过，或该机能写源码树导致迁移链偏离上游。处置是把该库的 `alembic_version` 改到当前镜像迁移链的头再重启——表结构与数据保留，**超出那部分的迁移所加的功能不可用**。镜像的迁移头取：

  ```bash
  docker run --rm --entrypoint sh ghcr.io/<registry-owner>/home-media-pilot:main \
    -c "ls /app/src/migrations/versions/"
  ```

- **拉取失败（`unauthorized` / `denied`）**：凭据缺失或类型不对，回到[前置条件](#前置条件)核对该机是否已 `docker login ghcr.io` 且用的是 classic token。

- **容器起来但接口不通**：先分辨是端口映射还是 CORS。从部署机本机 `curl http://127.0.0.1:<宿主端口>/health` 通、而另一台机器打不开，看端口与防火墙；页面能打开但接口被拦，看 `.env` 的 `HOST_IP` 是否填了实际访问地址，以及 `HOST_PORT` 是否为对外发布的那一个端口。

- **扫描或媒体库配置报「逻辑根不存在」**：`.env` 的 `LOGICAL_PATHS` 里的物理路径在容器内没有对应的卷挂载，或挂载路径与映射写得不一致。

- **Compose 报变量未设置或容器里取值是空的**：`.env` 与 `docker-compose.yml` 不在同一目录，或键名拼写与插值处不一致。Compose 只读同目录的 `.env`，文件放别处不会被读取。

## 与开发栈的区别

工程克隆内的 `docker-compose.yml` 是**本地开发栈**，与本文档描述的部署栈不是一回事：

| | 开发栈（克隆内 `docker-compose.yml`） | 部署栈（本文档） |
| --- | --- | --- |
| 镜像来源 | 每个服务各自 `build`，就地构建 | 从 GHCR 拉 CI 产出的镜像 |
| 数据库 | PostgreSQL 容器 + 开发期一次性密码 | sqlite 文件，落在挂载的主机目录 |
| 前端 | `node:22-alpine` 起 Vite dev server（挂 `dev` profile） | 前端产物已在镜像内，由 API 服务 |
| 绑定 | localhost 与仓库内相对路径 | 主机真实媒体路径与外部网络 |
| 用途 | 改代码时的迭代 | 常驻运行 |

两者的判据是**镜像从哪来**：一旦需要构建，它就不是部署栈。想在本机试跑业务面而手上没有部署机时，用开发栈；想让媒体库长期在线服务，用本文档。

## 适用范围

- **成立**：x86_64 主机；能访问 `ghcr.io` 并持有 `read:packages` 的 classic token；沿用 Compose 全文时主机上已有该外部网络，或已按上文删掉它；`.env` 与 `docker-compose.yml` 同目录且四个主机目录已按现场填全；需要数据库跨容器重建存活时，`/app/data` 已挂到主机目录。
- **失效**：
  - `arm64` 等其它架构。发布工作流未声明 `platforms`，镜像目标架构随 GitHub runner（`ubuntu-latest`）而定为 `linux/amd64`，在 arm64 主机上拉下来跑不起来。要支持其它架构得改发布工作流，属工程侧改动。
  - 部署机需要产出前端产物或需要构建镜像的场景。此时该机必须能构建，本文档的「不构建」前提不再成立。
  - 只需要本地开发栈的场景，用克隆内的 `docker-compose.yml`。
  - 需要把 WebUI 与 API 分置于不同 origin 的场景：镜像内的前端按页面同源构造请求，分体部署要另建带 `VITE_API_BASE_URL` 的前端产物（构建入口见 `Makefile` 的 `frontend-build-split`），那不在本文档的部署形态内。
