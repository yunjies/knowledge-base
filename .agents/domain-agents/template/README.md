# 领域 agent 实例脚手架

本模板以脚本和结构化数据驱动宿主工具；agent 不通过盲读操作手册获取领域知识。规范见[`领域 agent 脚手架规范`](../spec.md)，实例工具只在该 agent 的 preset 作用域内注册。

```text
template/
├── AGENTS.md
├── package.json
├── cordis.patch.yml
├── index.js
├── scripts/
│   ├── engine.js
│   ├── registration.js
│   └── runtime.js
├── data/
│   ├── resource-catalog.json
│   ├── path-policy.json
│   ├── test-spec.json
│   ├── review-workflow.json
│   ├── knowledge-store.json
│   └── schema/
│       ├── resource-catalog.schema.json
│       ├── path-policy.schema.json
│       ├── test-spec.schema.json
│       ├── review-workflow.schema.json
│       └── knowledge-store.schema.json
├── tests/
│   ├── engine.test.js
│   ├── runtime.test.js
│   └── registration.test.js
├── locale/
└── icon.svg
```

`index.js` 注册模型可调用的宿主工具。`scripts/` 实现按需取数、受控路径访问、结构化知识 CRUD 与审核状态转移。`data/` 承载机器可读的实例契约；资源记录只定位权威文档，不复制其正文。`AGENTS.md` 是主 agent 加载并注入 subagent 的正式指令文件。

`tests/` 对业务逻辑、宿主工具注册适配和 runtime 文件操作分别设门禁，并遍历资源目录、测试类别、审核阶段与 CRUD 操作验证实例数据可用。

审核脚本校验阶段顺序、必需产物与合法转移，不替模型作语义裁决。需要 reviewer subagent 的阶段由主 agent 调度，领域 agent 将审核证据交回主 agent。

实例化者须替换领域标识与资源、路径配置，设置 preset 的 `domainRoot`，并运行 Node 测试与知识库文档守护。实例只有在数据 schema、授权配置和行为测试齐备后才可挂载。
