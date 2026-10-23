# dsh-credentials 领域知识测试

本测试只验证领域 manifest schema、资源与源码读取边界、全部操作到权威资源的映射、目标连接状态文档与源码枚举的一致性、DSH profile 部署入口及通用 audit 引用；它不测试源码行为。运行前需让 dsh-credentials 源码 checkout 位于 manifest 登记的 `assets/projects/dsh-credentials/`。源码行为的测试入口以源码仓库 `tests/README.md` 为准。

## 运行

从 knowledge-base 仓库根目录运行：

```bash
UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest assets/domain-knowledge/dsh-credentials/tests -q
```

判据为全部测试通过且退出码为 0。用例验证 manifest 符合 schema、唯一源码仓库及资源/操作映射完整、无 orphan resource、全部读取/拒绝路径与限额登记、目标连接状态文案与源码枚举一致、部署命令模板可由 shell 解析、部署页只承载 DSH profile 集成并索引源码构建/测试说明，以及领域资料不重复定义通用 audit workflow。
