# 领域 agent 脚手架维护说明

本文件约束本目录内规范与模板的维护，不是领域 subagent 的运行提示。行为规范以 [`spec.md`](spec.md) 为准；知识库操作领域实例的 agent 提示见 [`template/AGENTS.md`](template/AGENTS.md)。

修改工具行为时，同步检查对应 JSON Schema、结构化实例数据、Host tool 声明和 `template/tests/` 反例。资源索引只登记权威源位置，不复制源文档正文。完成后运行知识库 `_lint/`，并运行模板 Node 测试。

本目录提供的是可实例化的 bundle 源码；只有用户明确要求修改当前 Harness profile 时，才安装或启用该 bundle。
