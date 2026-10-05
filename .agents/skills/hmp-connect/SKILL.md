---
name: hmp-connect
description: 按用户指定的目标实例，通过 HTTP API 或 CLI 连接、查询或操作 Home Media Pilot；从该实例的当前契约与部署事实发现所需接口，不猜端点、凭据或权限。
whenToUse: 用户要求连接、集成、查询、排障或操作 Home Media Pilot，或要求编写调用 HMP 的客户端代码时。
---

# HMP 连接与调用

本 skill 帮助 agent 针对明确的 HMP 实例发现并调用当前可用的 HTTP API 或 CLI。它不替代 HMP 部署、Provider 配置或业务写操作的审批流程。

## 使用入口

- 先确认用户请求的目标实例、操作和允许的影响；目标或权限不明确时先询问，不从历史对话或默认值猜测。
- 只发现完成当前操作所需的接口与参数；选择运行时契约、部署资料、CLI 帮助或源码的依据和调用护栏见[连接约束](references/connect-constraint.md)。
- 需要凭据时通过凭证插件提供的已授权机制取用；不得要求用户在对话中粘贴秘密，也不得将秘密复制到 skill、日志、命令输出或版本库。
- 调用前后按[连接约束](references/connect-constraint.md)核实目标、权限、副作用与业务结果；HTTP 成功状态本身不代表 HMP 或其消费者已成功完成操作。

## 范围

本 skill 管理 HMP API/CLI 的目标识别、当前契约发现、授权调用与结果验证；它不保存易变的基础 URL、端点、参数表、CLI 命令或服务状态。需要修改 HMP 部署、Provider 配置或受审批保护的业务状态时，应转到对应流程，并在执行写操作前取得该操作所需的明确授权。
