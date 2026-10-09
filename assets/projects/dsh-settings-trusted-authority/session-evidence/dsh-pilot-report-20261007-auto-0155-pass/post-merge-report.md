# A5 本地合并与隔离部署结果

**结论：PASS。** 需求方已在当前 session 明确批准；报告绑定的项目补丁已提交到本地审阅分支、fast-forward 到本地 `main`，合并版本的包已安装到全新隔离 Web profile，并通过真实浏览器保存/刷新冒烟。未 push 远端、未改动活跃 profile；inbox 文档未归档。

## 提交与审阅绑定

- 合并 commit：`c0bd39b5bd58cbc22fc2efc05c899fceae9927f3`；父 commit：`d4885c89c3d150c04d8109ea5f814b1daf6ff23d`。
- `main` 与 `pilot/session-review-preview` 均指向该 commit；本地 `main` 比 `origin/main` ahead 1，未 push；项目工作树干净。
- 提交差异与已批准 [项目补丁](project.diff) 的字节内容完全一致，SHA-256 均为 `d2e37e8b17ca9acf47a815a036972328b24098a951619139427baa95611aff05`；复算文件为 [project-commit-check.diff](project-commit-check.diff)。
- 外层知识库仍有既有改动；A5 只提交并合并了嵌套插件仓库，没有提交外层仓库。

## 合并版本验证

- [postmerge-static-c0bd39b.log](postmerge-static-c0bd39b.log)：来自合并后的 `main`；`node --check`、`npm test`（10/10）、`npm pack --dry-run` 与 `git diff --check` 均退出码 0。
- [postmerge-preview-c0bd39b.log](postmerge-preview-c0bd39b.log)：从该干净 `main` 工作树执行 `preview:session`，真实 Chromium 结果为 `PREVIEW_RESULT=PASS`，保存的 Models provider 刷新后仍可读；profile 清理结果为 `PROFILE_CLEANUP=removed`，命令退出码 0。
- 隔离 profile：`session-preview-22965-1791352171729`；临时 origin：`http://127.0.0.1:43163/`。runner 将 DSH 子进程的 `DSH_HOME` 指向全新临时 home，并清除继承的 `DSH_PROFILE`、`DSH_PROFILE_DIR`；该 home 与服务已清理，活跃 profile 未作为部署目标。
- 合并版本生成并实际安装的包为 [post-merge tarball](../dsh-pilot-postmerge-c0bd39b/dsh-settings-trusted-authority-plugin-0.1.0.tgz)，SHA-256：`e0e64a27958e7d3e0f15d71bf9288d27b815e0318fc226ddc03fb9e5d7fdfd69`。它是从合并后的 `main` 重新构建的产物；不同于批准前报告绑定的 tarball，后者仍见[原报告](session-pr-report.md)。
- 浏览器证据：[保存后截图](../dsh-pilot-postmerge-c0bd39b/models-saved.png)、[刷新后截图](../dsh-pilot-postmerge-c0bd39b/models-after-refresh.png)、[录屏](../dsh-pilot-postmerge-c0bd39b/session-preview.webm)。使用的是无效合成 key；验证只证明本地 Settings 持久化，不证明凭据有效、模型 API 可用或服务连通。

## 外层知识库状态

- 合并后的请求状态已记录为验收通过、A5 完成；需求文档仍留在 inbox。A5 批准不视为归档授权；未收到明确归档同意前不移动文档。
- 批准后仅更新了该需求流程图的 A5/完成状态；该外层状态记录不在已批准的预合并 [knowledge-base.diff](knowledge-base.diff) 内，未提交外层仓库，也未 push。
- 最新全量知识库 lint 仍为 45 passed、2 failed、exit 1；两项失败都指向未纳入试点的 [Home Media Pilot resource-meta-read 请求](</mnt/deepseek-harness/knowledge-base/assets/inbox/req.home-media-pilot.resource-meta-read.20261007-140840.md>)。本试点的定向检查通过；详细输出见 [postmerge-kb-lint.log](postmerge-kb-lint.log)。该请求未被修改。

## 可复用能力与裁决

**【事实】** 本试点证明一个非 GitHub 的 session 审阅关卡能把精确项目 diff、包哈希、静态测试、隔离 DSH Web profile、真实浏览器保存/刷新证据与明确人工批准串成闭环；批准后可核对提交差异、仅 fast-forward 本地 `main`，再从合并版本重建包并隔离冒烟。项目内可复用的 runner、守卫测试、命令与限制已固化在插件仓库的 [session-preview.mjs](</mnt/deepseek-harness/knowledge-base/assets/projects/dsh-settings-trusted-authority/dsh-settings-trusted-authority/scripts/session-preview.mjs>)、[workflow.test.js](</mnt/deepseek-harness/knowledge-base/assets/projects/dsh-settings-trusted-authority/dsh-settings-trusted-authority/tests/workflow.test.js>)、[tests/README.md](</mnt/deepseek-harness/knowledge-base/assets/projects/dsh-settings-trusted-authority/dsh-settings-trusted-authority/tests/README.md>) 与 [deploy.md](</mnt/deepseek-harness/knowledge-base/assets/projects/dsh-settings-trusted-authority/deploy.md>)。

**【反题】** 单个插件项目、一个 DSH 版本和一个 Models 设置面不能证明每类项目都需要相同的预览或发布步骤；把它强制写成全局必经流程，可能给无 UI、无可部署包或有不同发布策略的项目增加无关门禁。Workbench live diff UI 本次也未展示。

**【裁决】** 固化为按项目能力选择的可选 session gate：报告必须绑定基线与精确 diff/package，按实际交付选择测试、运行预览和截图/视频，明确未验证面；人工批准前不合并或部署，批准后只做已授权的本地合并与隔离冒烟。本次保留项目级 runner/文档，不把 GitHub PR/CI、自动远端发布或统一主干策略提升为全局规则。

**可证伪条件与弃用代价：** 若下一个不同类型项目不能在不写项目专用适配器的情况下使用该 gate，或任何报告哈希、提交差异、部署包不一致，则需修订或限制该流程；若弃用，移除项目级 runner、对应测试和部署说明并恢复手动核验，不影响插件运行时代码。

## 下一项目建议

推荐下一步处理 Home Media Pilot 的本地 metadata/封面读取，但先把新的 resource-meta-read 请求与已存在的 [media-library-waterfall 请求](</mnt/deepseek-harness/knowledge-base/assets/inbox/req.home-media-pilot.media-library-waterfall.20261003-055635.md>)协调为一个不重叠的范围。当前 resource-meta-read 文档的缺少子流程图与参数槽触发了上述两项全量 lint 失败；先由需求方确认归并/修正规格，再授权启动，不在本报告中开始该项目。
