# 项目资产索引

本索引列出 `assets/projects/` 中的项目资产入口。领域流程、部署与审核资料按项目行给出的领域知识入口读取；源码实现与项目测试以对应的源码 checkout 为准。

## 当前 DSH 版本

本机 DSH CLI 于 2026-10-04（Pacific/Guam）通过 `dsh --version` 核验为 `0.2.0-rc.2`；该值描述当前开发环境，不代表所有部署机，也不自动证明所有 DSH 插件兼容。

判断插件适用性时，分别读取本机 `dsh --version` 与项目部署文档中的兼容基线；版本标记不同或未标记时，先在隔离 profile 验证，不从项目包自己的版本号推断 DSH 版本。

## 项目目录

| 项目 | 用途 | DSH 版本标注 | 入口 |
| --- | --- | --- | --- |
| `home-media-pilot` | 家庭媒体控制面与容器化部署 | 非 DSH 插件；不适用 | [流程](home-media-pilot/feature-flow.md) · [部署](home-media-pilot/deploy.md) · [仓库说明](home-media-pilot/home-media-pilot/README.md) |
| `dsh-credentials` | DSH agent 凭证目录与管理页面 | 项目部署说明未固定 DSH 版本；按其适用范围与测试说明核验 | [源码仓库说明](dsh-credentials/README.md) · [领域知识](../domain-knowledge/dsh-credentials/README.md) |
| `dsh-settings-trusted-authority` | 为可信远程 Web authority 提供 Host-backed Settings 持久化 | 插件包[版本](dsh-settings-trusted-authority/dsh-settings-trusted-authority/package.json)为 `0.1.0`；DSH 验证基线 `0.2.0-rc.2`，与本机当前 CLI 一致 | [流程](dsh-settings-trusted-authority/feature-flow.md) · [部署](dsh-settings-trusted-authority/deploy.md) · [GitHub](https://github.com/yunjies/dsh-settings-trusted-authority) · [本地仓库说明](dsh-settings-trusted-authority/dsh-settings-trusted-authority/README.md) |

## 跨项目方案

遇到可信远程 authority 上 Settings 页面不可用或修改无法跨刷新保留时，先读[解决方案笔记](../notes/dsh-trusted-web-authority-settings.md)，再进入对应项目的部署说明。