# 领域 agent 脚手架维护说明

本文件约束本目录内通用领域 agent 脚手架与规范的维护，不是 subagent 的运行提示。行为规范以 [`spec.md`](spec.md) 为准；每次调用注入的通用指令见 [`template/AGENTS.md`](template/AGENTS.md)。

修改通用工具行为时，同步检查工具 schema、通用数据契约、Host tool 声明和 `template/tests/` 反例。通用资源索引只登记权威源位置，不复制源文档正文。完成后运行知识库 `_lint/` 与通用脚手架测试。领域业务数据和业务脚手架由领域知识目录维护，并通过其自身 lint/tests 验证；不得把领域专属实例数据并入通用模板。

本目录提供可复用的 bundle 源码；只有用户明确要求修改当前 Harness profile 时，才安装或启用该 bundle。
