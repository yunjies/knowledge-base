from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from _harness import paths

RULE_IDS = tuple(f"DA-{number:02d}" for number in range(1, 14))
TOP_FIELDS = ("模态", "scope", "动作", "产出物")
ARTIFACT_FIELDS = ("形态", "判定口径", "语义判据")
RULE_REQUIREMENTS = {
    "DA-01": "为每次调用声明活动领域",
    "DA-02": "只调用本次调用作用域内已注册且已授权的 host tools",
    "DA-03": "具名脚本 handler",
    "DA-04": "通过对应 schema",
    "DA-05": "不复制权威源正文",
    "DA-06": "在每次 I/O 前执行归属检查",
    "DA-07": "未登记类别明确返回未知",
    "DA-08": "按通用 audit workflow 数据验证当前阶段输入",
    "DA-09": "不存在 worker 知识/源码写入工具",
    "DA-10": "返回结构化失败结果并停止该次操作",
    "DA-11": "修改工具参数中的领域或仓库标识不能扩大",
    "DA-12": "通用脚手架通过共享 lint/tests",
    "DA-13": "按活动项目的结构化策略解析",
}
REQUIRED_FILES = (
    ".agents/domain-agents/AGENTS.md",
    ".agents/domain-agents/README.md",
    ".agents/domain-agents/spec.md",
    ".agents/domain-agents/template/AGENTS.md",
    ".agents/domain-agents/template/README.md",
    ".agents/domain-agents/template/package.json",
    ".agents/domain-agents/template/cordis.patch.yml",
    ".agents/domain-agents/template/index.js",
    ".agents/domain-agents/template/scripts/engine.js",
    ".agents/domain-agents/template/scripts/domain-runtime.js",
    ".agents/domain-agents/template/scripts/child-runner.js",
    ".agents/domain-agents/template/scripts/registration.js",
    ".agents/domain-agents/template/tests/engine.test.js",
    ".agents/domain-agents/template/tests/runtime.test.js",
    ".agents/domain-agents/template/tests/registration.test.js",
    ".agents/domain-agents/template/data/schema/domain-catalog.schema.json",
    ".agents/domain-agents/template/data/schema/domain-manifest.schema.json",
    ".agents/domain-agents/template/locale/en.json",
    ".agents/domain-agents/template/locale/zh.json",
    ".agents/domain-agents/template/icon.svg",
)
TOOL_NAMES = (
    "list_domain_knowledge",
    "run_domain_agent",
    "get_access_paths",
    "get_operation_method",
    "get_knowledge_resource",
    "list_project_files",
    "get_project_source",
    "get_test_specification",
    "submit_audit_findings",
)
SCHEMA_REQUIRED_FIELDS = {
    "domain-catalog.schema.json": {
        (): {"schemaVersion", "domains"},
        ("properties", "domains", "items"): {"id", "title", "manifestPath", "repositoryIds"},
    },
    "domain-manifest.schema.json": {
        (): {"schemaVersion", "domainId", "resources", "repositories", "operationMethods", "changeKinds"},
        ("properties", "resources", "items"): {"id", "kind", "title", "path", "format", "maxBytes"},
        ("properties", "repositories", "items"): {"id", "root", "readPaths", "denyPaths", "maxFileBytes", "maxLines"},
        ("properties", "operationMethods", "items"): {"id", "repositoryId", "methodId", "resourceIds"},
        ("properties", "changeKinds", "items"): {"id", "layers", "resourceIds"},
    },
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def schema_errors(value, schema: dict, pointer: str = "$") -> list[str]:
    errors = []
    expected = schema.get("type")
    type_ok = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected in type_ok and not type_ok[expected]:
        return [f"{pointer} must have type {expected}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{pointer} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{pointer} must be one of {schema['enum']!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{pointer} is shorter than minLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{pointer} does not match its pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", value):
            errors.append(f"{pointer} is below minimum")
        if value > schema.get("maximum", value):
            errors.append(f"{pointer} is above maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{pointer} has too few items")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            errors.append(f"{pointer} contains duplicate items")
        if schema.get("items"):
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], f"{pointer}[{index}]"))
    if isinstance(value, dict):
        errors.extend(f"{pointer}.{key} is required" for key in schema.get("required", []) if key not in value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors.extend(f"{pointer}.{key} is not allowed" for key in value if key not in properties)
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(schema_errors(value[key], child_schema, f"{pointer}.{key}"))
        if isinstance(schema.get("additionalProperties"), dict):
            for key, child in value.items():
                if key not in properties:
                    errors.extend(schema_errors(child, schema["additionalProperties"], f"{pointer}.{key}"))
    return errors


def spec_errors(text: str) -> list[str]:
    errors = []
    section_match = re.search(r"(?m)^## 1\. 单领域调用与工具约束$", text)
    if section_match is None:
        return ["missing the normative rule section"]
    section = text[section_match.end() :]
    headings = list(re.finditer(r"(?m)^### ([A-Z]{2}-\d{2}) (.+)$", section))
    found = [heading.group(1) for heading in headings]
    if found != list(RULE_IDS):
        errors.append(f"rule headings must be exactly {list(RULE_IDS)}, found {found}")
    for line_number, line in enumerate(section.splitlines(), start=1):
        if not line.strip() or re.fullmatch(r"### [A-Z]{2}-\d{2} .+", line):
            continue
        if re.fullmatch(r"- \*\*(模态|scope|动作|产出物)\*\*: .+", line):
            continue
        if re.fullmatch(r"  - \*\*(形态|判定口径|语义判据)\*\*: .+", line):
            continue
        errors.append(f"non-card content at rule-section line {line_number}: {line}")
    for index, heading in enumerate(headings):
        rule_id = heading.group(1)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(section)
        block = section[heading.end() : end]
        for field in TOP_FIELDS:
            count = len(re.findall(rf"(?m)^- \*\*{re.escape(field)}\*\*:", block))
            if count != 1:
                errors.append(f"{rule_id} requires exactly one {field} field, found {count}")
        for field in ARTIFACT_FIELDS:
            count = len(re.findall(rf"(?m)^  - \*\*{re.escape(field)}\*\*:", block))
            if count != 1:
                errors.append(f"{rule_id} requires exactly one artifact {field}, found {count}")
        if not re.search(r"(?m)^- \*\*模态\*\*: must$", block):
            errors.append(f"{rule_id} must explicitly declare modality must")
        requirement = RULE_REQUIREMENTS.get(rule_id)
        if requirement is not None and requirement not in block:
            errors.append(f"{rule_id} is missing required normative content: {requirement}")
        if rule_id == "DA-13":
            for token in ("get_operation_method", "get_knowledge_resource", "自然语言描述", "模型从措辞推断"):
                if token not in block:
                    errors.append(f"DA-13 is missing standardized method selection contract: {token}")
    return errors


def schema_contract_errors(schemas: dict[str, dict]) -> list[str]:
    errors = []
    for schema_name, required_paths in SCHEMA_REQUIRED_FIELDS.items():
        schema = schemas.get(schema_name)
        if not isinstance(schema, dict):
            errors.append(f"missing schema contract: {schema_name}")
            continue
        for path, expected in required_paths.items():
            node = schema
            for part in path:
                node = node.get(part, {}) if isinstance(node, dict) else {}
            actual = set(node.get("required", [])) if isinstance(node, dict) else set()
            if not expected.issubset(actual):
                errors.append(f"{schema_name} does not require all contract fields at {path}: {sorted(expected - actual)}")
    return errors


def sample_domain_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "domainId": "sample-domain",
        "resources": [{"id": "flow", "kind": "implemented-flow", "title": "Flow", "path": "assets/domain-knowledge/sample-domain/flow.md", "format": "markdown", "maxBytes": 10000}],
        "repositories": [{"id": "sample-repo", "root": "assets/projects/sample-repo", "readPaths": ["src/**"], "denyPaths": [".git/**"], "maxFileBytes": 50000, "maxLines": 200}],
        "operationMethods": [{"id": "local-git", "repositoryId": "sample-repo", "methodId": "git-cli", "resourceIds": ["flow"]}],
        "changeKinds": [{"id": "source-change", "layers": ["static"], "resourceIds": ["flow"]}],
    }


def scaffold_errors(root: Path, spec_override: str | None = None) -> list[str]:
    errors = [f"missing required file: {path}" for path in REQUIRED_FILES if not (root / path).is_file()]
    if errors:
        return errors
    spec = spec_override if spec_override is not None else (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    errors.extend(spec_errors(spec))
    maintainer = (root / ".agents/domain-agents/AGENTS.md").read_text(encoding="utf-8")
    if "spec.md" not in maintainer or "template/AGENTS.md" not in maintainer:
        errors.append("maintainer instructions must identify the normative spec and worker prompt")
    template = root / ".agents/domain-agents/template"
    readme = (template / "README.md").read_text(encoding="utf-8")
    for phrase in ("run_domain_agent", "get_operation_method", "get_project_source", "每次调用", "不复制 audit workflow"):
        if phrase not in readme:
            errors.append(f"template README is missing the invocation contract: {phrase}")
    agent = (template / "AGENTS.md").read_text(encoding="utf-8")
    for tool_name in ("get_access_paths", "get_operation_method", "get_knowledge_resource", "list_project_files", "get_project_source", "get_test_specification", "run_domain_knowledge_lint"):
        if tool_name not in agent:
            errors.append(f"worker instructions are missing tool contract: {tool_name}")
    if "不得根据用户措辞推断" not in agent or "不得使用普通文件" not in agent:
        errors.append("worker instructions must forbid semantic method selection and unscoped file access")
    for phrase in ("domain-knowledge-validation", "domain-tests", "lint", "标准输出/错误、退出码"):
        if phrase not in agent:
            errors.append(f"worker instructions are missing the unified domain knowledge test flow: {phrase}")
    for phrase in ("domain-knowledge-validation", "domain-tests", "领域间唯一允许不同的是本领域测试断言和覆盖内容"):
        if phrase not in readme:
            errors.append(f"template README is missing the common per-domain test contract: {phrase}")
    index = (template / "index.js").read_text(encoding="utf-8")
    registration = (template / "scripts/registration.js").read_text(encoding="utf-8")
    runtime = (template / "scripts/domain-runtime.js").read_text(encoding="utf-8")
    child_runner = (template / "scripts/child-runner.js").read_text(encoding="utf-8")
    for required in ("export const inject", "export const Config", "export function apply", "registerCoordinatorTools"):
        if required not in index:
            errors.append(f"coordinator plugin is missing {required}")
    errors.extend(tool_registration_errors(registration))
    if "parent.ctx.agents.create" not in child_runner or "workerPresetId" not in child_runner or "childSessionMeta" not in child_runner or "owner.track(childSessionId" not in child_runner:
        errors.append("per-call child creation must bind and own an ephemeral worker scope")
    if "ctx.fs.listDir" not in runtime or "getProjectSource" not in runtime:
        errors.append("source tools must list and read through the scoped filesystem provider")
    if "ctx.subprocess.spawn" not in runtime or "resolveExecutable" not in runtime or "run_domain_knowledge_lint" not in registration:
        errors.append("domain lint must execute only through the managed subprocess service")
    if "resolveInside" not in runtime or "PATH_OUTSIDE_SCOPE" not in runtime:
        errors.append("domain tools must check canonical filesystem containment")
    package = load_json(template / "package.json")
    if package.get("dsh", {}).get("bundle", {}).get("patch") != "./cordis.patch.yml":
        errors.append("host-tool package must declare its Cordis bundle patch")
    if "./icon" not in package.get("exports", {}) or "./locale/*.json" not in package.get("exports", {}):
        errors.append("host-tool package must export its icon and locales")
    required_files = {"AGENTS.md", "index.js", "cordis.patch.yml", "scripts/*.js", "data/schema/*.json", "locale/*.json", "icon.svg"}
    if not required_files.issubset(set(package.get("files", []))):
        errors.append("host-tool package files must include all runtime and display resources")
    try:
        ET.parse(template / "icon.svg")
    except ET.ParseError:
        errors.append("host-tool icon must be valid SVG")
    for peer in (
        "@deepseek-ai/dsh-tools",
        "@deepseek-ai/dsh-agent-loop",
        "@deepseek-ai/dsh-agent",
        "@deepseek-ai/dsh-system-prompt",
        "@deepseek-ai/dsh-agent-preset-registry",
        "@deepseek-ai/dsh-llm",
        "@deepseek-ai/dsh-subagent",
    ):
        if peer not in package.get("peerDependencies", {}):
            errors.append(f"host-tool package is missing peer dependency {peer}")
    patch = (template / "cordis.patch.yml").read_text(encoding="utf-8")
    if "domain-agent-coordinator" not in patch or "domain-agent-worker" in patch or "knowledge-base-operations" in patch:
        errors.append("bundle patch must declare one generic coordinator preset, not one preset per domain")
    schemas = {path.name: load_json(path) for path in (template / "data/schema").glob("*.json")}
    errors.extend(schema_contract_errors(schemas))
    manifest_schema = schemas["domain-manifest.schema.json"]
    errors.extend(schema_errors(sample_domain_manifest(), manifest_schema))
    unsafe = sample_domain_manifest()
    unsafe["repositories"][0]["root"] = "assets/projects/../outside"
    if not schema_errors(unsafe, manifest_schema):
        errors.append("domain manifest schema must reject traversing source roots")
    return errors


def tool_registration_errors(source: str) -> list[str]:
    errors = [f"host tool registration is missing {tool_name}" for tool_name in TOOL_NAMES if f'"{tool_name}"' not in source]
    if "ctx.tools.register" not in source or "ctx.effect" not in source:
        errors.append("host tools must register in their owning context and dispose with it")
    return errors


def test_domain_agent_scaffold_conforms() -> None:
    assert scaffold_errors(paths.repository_root()) == []


def test_common_domain_knowledge_categories_are_documented() -> None:
    root = paths.repository_root()
    spec = (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    for knowledge_type in ("项目与源码定位", "已实现流程", "DSH 集成部署", "版本管理", "测试规范", "审核流程入口", "路径与能力策略", "操作方式映射", "领域业务规则"):
        assert knowledge_type in spec
    assert "通用 audit workflow" in spec


def test_method_selection_must_not_depend_on_task_semantics() -> None:
    root = paths.repository_root()
    spec = (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    damaged = spec.replace("只改用户任务的自然语言描述，工具解析出的 `methodId` 是否保持不变", "由工具按任务语义选择 `methodId`", 1)
    assert any("DA-13 is missing standardized method selection contract" in error for error in spec_errors(damaged))


def test_agent_preset_bundle_rows_are_generic() -> None:
    root = paths.repository_root()
    patch = (root / ".agents/domain-agents/template/cordis.patch.yml").read_text(encoding="utf-8")
    assert "domain-agent-coordinator" in patch
    assert "domain-agent-worker" not in patch
    assert "dsh-credentials" not in patch


def test_domain_catalog_and_manifest_schema_files_are_json() -> None:
    root = paths.repository_root()
    schema_root = root / ".agents/domain-agents/template/data/schema"
    schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in schema_root.glob("*.json")}
    assert set(schemas) == {"domain-catalog.schema.json", "domain-manifest.schema.json"}
    assert all(isinstance(schema, dict) for schema in schemas.values())


def test_spec_rule_cards_remain_closed_and_required() -> None:
    root = paths.repository_root()
    spec = (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    damaged = spec.replace("按活动项目的结构化策略解析", "按模型措辞猜测解析", 1)
    assert any("DA-13 is missing required normative content" in error for error in spec_errors(damaged))


def test_coordinator_resolves_scope_before_invoking_child() -> None:
    root = paths.repository_root()
    registration = (root / ".agents/domain-agents/template/scripts/registration.js").read_text(encoding="utf-8")
    assert registration.index("loadDomainScope(ctx, exec, config, args.domainId, args.repositoryId)") < registration.index("runChildAgent({ args, exec, scope })")


def test_child_setup_precedes_the_first_prompt() -> None:
    root = paths.repository_root()
    runner = (root / ".agents/domain-agents/template/scripts/child-runner.js").read_text(encoding="utf-8")
    assert runner.index("setup: async agentCtx") < runner.index("child.followup(")
    assert "registerDomainTools(agentCtx, scope" in runner


def test_child_scope_restricts_tools_and_disposes_registrations() -> None:
    root = paths.repository_root()
    registration = (root / ".agents/domain-agents/template/scripts/registration.js").read_text(encoding="utf-8")
    child_runner = (root / ".agents/domain-agents/template/scripts/child-runner.js").read_text(encoding="utf-8")
    assert "agentCtx.tools.restrict({ deny: deniedGlobalTools })" in registration
    assert "agentCtx.tools.guard(" in registration
    assert "agentCtx.tools.presentAs(\"native\")" in registration
    assert "disposers.splice(0).reverse().forEach(dispose => dispose())" in registration
    assert "owner.track(childSessionId, { dispose: disposeHandle })" in child_runner
    assert "await disposeHandle()" in child_runner
    assert "ctx.effect(() => async ()" in child_runner


def test_domain_runtime_is_read_only() -> None:
    root = paths.repository_root()
    runtime = (root / ".agents/domain-agents/template/scripts/domain-runtime.js").read_text(encoding="utf-8")
    assert "ctx.fs.listDir" in runtime
    assert "ctx.fs.streamText" in runtime
    assert "ctx.fs.writeText" not in runtime
    assert "ctx.fs.unlink" not in runtime


def test_operation_mapping_is_keyed_only_by_registered_operation_id() -> None:
    root = paths.repository_root()
    runtime = (root / ".agents/domain-agents/template/scripts/domain-runtime.js").read_text(encoding="utf-8")
    assert "item.id === args.operationId" in runtime
    assert "operation.methodId" in runtime
    assert "args.task" not in runtime


def test_domain_ids_and_repository_roots_are_not_configured_per_instance() -> None:
    root = paths.repository_root()
    index = (root / ".agents/domain-agents/template/index.js").read_text(encoding="utf-8")
    patch = (root / ".agents/domain-agents/template/cordis.patch.yml").read_text(encoding="utf-8")
    assert "domainId: z.string().default" not in index
    assert "domainRoot: z.string().default" not in index
    assert "domain-agent-coordinator" in patch
    assert "domain-agent-worker" not in patch
    assert 'workerPresetId: "minimal"' in index
    assert "dsh-credentials" not in patch


def test_domain_manifest_schema_requires_boundaries_and_method_resources() -> None:
    root = paths.repository_root()
    schema = load_json(root / ".agents/domain-agents/template/data/schema/domain-manifest.schema.json")
    assert schema_errors(sample_domain_manifest(), schema) == []
    assert "operationMethods" in schema["required"]
    assert "resourceIds" in schema["properties"]["operationMethods"]["items"]["required"]
    assert "readPaths" in schema["properties"]["repositories"]["items"]["required"]
    assert "writeTargets" not in schema["properties"]


def test_host_tool_javascript_sources_parse() -> None:
    root = paths.repository_root()
    sources = sorted((root / ".agents/domain-agents/template").rglob("*.js"))
    assert sources
    for source in sources:
        result = subprocess.run(["node", "--check", str(source.relative_to(root))], cwd=root, capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"{source}: {result.stdout}{result.stderr}"


def test_host_tool_node_suite_passes() -> None:
    root = paths.repository_root()
    result = subprocess.run(
        ["node", "--test", ".agents/domain-agents/template/tests/engine.test.js", ".agents/domain-agents/template/tests/runtime.test.js", ".agents/domain-agents/template/tests/registration.test.js"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
