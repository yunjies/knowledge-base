from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from _harness import paths

RULE_IDS = tuple(f"DA-{number:02d}" for number in range(1, 13))
TOP_FIELDS = ("模态", "scope", "动作", "产出物")
ARTIFACT_FIELDS = ("形态", "判定口径", "语义判据")
RULE_REQUIREMENTS = {
    "DA-01": "且只声明一个知识领域",
    "DA-02": "只调用该实例在宿主工具注册表中注册且已授权的工具",
    "DA-03": "由宿主工具定义调用",
    "DA-04": "通过对应 schema",
    "DA-05": "不复制权威源正文",
    "DA-06": "路径归属检查",
    "DA-07": "未登记类别明确返回未知",
    "DA-08": "按 workflow 数据验证当前阶段输入",
    "DA-09": "预期版本",
    "DA-10": "返回结构化失败结果并停止该次操作",
    "DA-11": "无关 agent 看不到领域专属工具",
    "DA-12": "反例覆盖盲读",
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
    ".agents/domain-agents/template/scripts/registration.js",
    ".agents/domain-agents/template/scripts/runtime.js",
    ".agents/domain-agents/template/tests/engine.test.js",
    ".agents/domain-agents/template/tests/runtime.test.js",
    ".agents/domain-agents/template/tests/registration.test.js",
    ".agents/domain-agents/template/data/resource-catalog.json",
    ".agents/domain-agents/template/data/path-policy.json",
    ".agents/domain-agents/template/data/test-spec.json",
    ".agents/domain-agents/template/data/review-workflow.json",
    ".agents/domain-agents/template/data/knowledge-store.json",
    ".agents/domain-agents/template/data/schema/resource-catalog.schema.json",
    ".agents/domain-agents/template/data/schema/path-policy.schema.json",
    ".agents/domain-agents/template/data/schema/test-spec.schema.json",
    ".agents/domain-agents/template/data/schema/review-workflow.schema.json",
    ".agents/domain-agents/template/data/schema/knowledge-store.schema.json",
    ".agents/domain-agents/template/locale/en.json",
    ".agents/domain-agents/template/locale/zh.json",
    ".agents/domain-agents/template/icon.svg",
)
TOOL_NAMES = (
    "get_version_control_instructions",
    "get_access_paths",
    "get_test_specification",
    "get_knowledge_resource",
    "advance_review",
    "manage_domain_knowledge",
)
DATA_SCHEMAS = {
    "resource-catalog.json": "resource-catalog.schema.json",
    "path-policy.json": "path-policy.schema.json",
    "test-spec.json": "test-spec.schema.json",
    "review-workflow.json": "review-workflow.schema.json",
    "knowledge-store.json": "knowledge-store.schema.json",
}
SCHEMA_REQUIRED_FIELDS = {
    "resource-catalog.schema.json": {
        (): {"schemaVersion", "domainId", "resources"},
        ("properties", "resources", "items"): {"id", "title", "path", "format", "maxBytes"},
    },
    "path-policy.schema.json": {
        (): {"schemaVersion", "domainId", "policyResourceIds", "readResourceIds", "writeTargets", "denyPathForms"},
        ("properties", "writeTargets", "items"): {"id", "path", "operations", "versionGuarded"},
    },
    "test-spec.schema.json": {
        (): {"schemaVersion", "domainId", "changeKinds"},
        ("properties", "changeKinds", "items"): {"id", "layers", "resourceIds"},
    },
    "review-workflow.schema.json": {
        (): {"schemaVersion", "domainId", "workflowId", "startStage", "terminalStage", "stages"},
        ("properties", "stages", "items"): {"id", "resourceIds", "requiredResultFields", "fieldConstraints", "transitions"},
    },
    "knowledge-store.schema.json": {
        (): {"schemaVersion", "domainId", "revision", "records"},
        ("properties", "records", "items"): {"id", "title", "body", "tags", "revision"},
    },
}


def spec_errors(text: str) -> list[str]:
    errors = []
    section_match = re.search(r"(?m)^## 1\. 单领域 host-tool agent 约束$", text)
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
    return errors


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
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, item_schema, f"{pointer}[{index}]"))
    if isinstance(value, dict):
        missing = [key for key in schema.get("required", []) if key not in value]
        errors.extend(f"{pointer}.{key} is required" for key in missing)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors.extend(f"{pointer}.{key} is not allowed" for key in value if key not in properties)
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(schema_errors(value[key], child_schema, f"{pointer}.{key}"))
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            for key, child in value.items():
                if key not in properties:
                    errors.extend(schema_errors(child, additional, f"{pointer}.{key}"))
        if len(value) < schema.get("minProperties", 0):
            errors.append(f"{pointer} has too few properties")
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


def validate_data(data: dict[str, dict], schemas: dict[str, dict]) -> list[str]:
    errors = schema_contract_errors(schemas)
    for filename, schema_name in DATA_SCHEMAS.items():
        if filename not in data or schema_name not in schemas:
            errors.append(f"missing structured data or schema: {filename}")
            continue
        errors.extend(schema_errors(data[filename], schemas[schema_name], filename))
    catalog = data.get("resource-catalog.json", {})
    policy = data.get("path-policy.json", {})
    test_spec = data.get("test-spec.json", {})
    workflow = data.get("review-workflow.json", {})
    store = data.get("knowledge-store.json", {})
    resources = catalog.get("resources", [])
    resource_ids = [resource.get("id") for resource in resources]
    if len(resource_ids) != len(set(resource_ids)):
        errors.append("resource ids must be unique")
    for resource in resources:
        path = resource.get("path", "")
        if path.startswith("/") or "\\" in path or ".." in path.split("/"):
            errors.append(f"resource path is not workspace-relative: {path}")
    resource_set = set(resource_ids)
    readable = set(policy.get("readResourceIds", []))
    policy_sources = set(policy.get("policyResourceIds", []))
    if readable - resource_set:
        errors.append(f"path policy references unknown resources: {sorted(readable - resource_set)}")
    if policy_sources - readable:
        errors.append(f"policy source resources are not readable: {sorted(policy_sources - readable)}")
    for change_kind in test_spec.get("changeKinds", []):
        unknown = set(change_kind.get("resourceIds", [])) - readable
        if unknown:
            errors.append(f"test kind {change_kind.get('id')} references unreadable resources: {sorted(unknown)}")
    stages = workflow.get("stages", [])
    stage_ids = [stage.get("id") for stage in stages]
    if len(stage_ids) != len(set(stage_ids)):
        errors.append("review stage ids must be unique")
    stage_set = set(stage_ids)
    if workflow.get("startStage") not in stage_set:
        errors.append("review startStage must name a registered stage")
    terminal = workflow.get("terminalStage")
    for stage in stages:
        if set(stage.get("resourceIds", [])) - readable:
            errors.append(f"review stage {stage.get('id')} references unreadable resources")
        for target in stage.get("transitions", {}).values():
            if target not in stage_set and target not in {terminal, "halt"}:
                errors.append(f"review stage {stage.get('id')} has unknown transition target {target}")
    reachable = set()
    frontier = [workflow.get("startStage")]
    by_id = {stage.get("id"): stage for stage in stages}
    while frontier:
        current = frontier.pop()
        if current in reachable or current not in by_id:
            continue
        reachable.add(current)
        frontier.extend(by_id[current].get("transitions", {}).values())
    if reachable != stage_set:
        errors.append(f"review workflow contains unreachable stages: {sorted(stage_set - reachable)}")
    target = next((item for item in policy.get("writeTargets", []) if item.get("id") == "knowledge-records"), None)
    if not target or target.get("path") != "data/knowledge-store.json" or set(target.get("operations", [])) != {"create", "read", "update", "delete"} or target.get("versionGuarded") is not True:
        errors.append("path policy must version-guard CRUD to data/knowledge-store.json only")
    record_ids = [record.get("id") for record in store.get("records", [])]
    if len(record_ids) != len(set(record_ids)):
        errors.append("knowledge store record ids must be unique")
    return errors


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tool_registration_errors(source: str) -> list[str]:
    errors = [f"host tool registration is missing {tool_name}" for tool_name in TOOL_NAMES if f'definition(defineTool, runtime, "{tool_name}"' not in source]
    if "ctx.tools.register" not in source or "ctx.effect" not in source:
        errors.append("host tools must register in the agent scope and dispose with its context")
    return errors


def scaffold_errors(root: Path, spec_override: str | None = None, data_override: dict[str, dict] | None = None) -> list[str]:
    errors = [f"missing required file: {path}" for path in REQUIRED_FILES if not (root / path).is_file()]
    if errors:
        return errors
    spec_path = root / ".agents/domain-agents/spec.md"
    spec = spec_override if spec_override is not None else spec_path.read_text(encoding="utf-8")
    errors.extend(spec_errors(spec))
    maintainer_instructions = (root / ".agents/domain-agents/AGENTS.md").read_text(encoding="utf-8")
    if "spec.md" not in maintainer_instructions or "template/AGENTS.md" not in maintainer_instructions:
        errors.append("domain-agent maintainer AGENTS.md must identify the spec and instance prompt")
    template = root / ".agents/domain-agents/template"
    readme = (template / "README.md").read_text(encoding="utf-8")
    if "../spec.md" not in readme:
        errors.append("template index must point to the normative spec")
    agent = (template / "AGENTS.md").read_text(encoding="utf-8")
    for required in (
        "不得直接读取、遍历或搜索知识目录",
        "get_version_control_instructions",
        "get_access_paths",
        "get_test_specification",
        "get_knowledge_resource",
        "manage_domain_knowledge",
        "advance_review",
    ):
        if required not in agent:
            errors.append(f"agent prompt is missing required tool-use instruction: {required}")
    index = (template / "index.js").read_text(encoding="utf-8")
    registration = (template / "scripts/registration.js").read_text(encoding="utf-8")
    errors.extend(tool_registration_errors(registration))
    for required in ("export const inject", "export const Config", "export function apply", "registerDomainTools(ctx, config, defineTool)"):
        if required not in index:
            errors.append(f"DSH plugin adapter is missing {required}")
    package = load_json(template / "package.json")
    if package.get("dsh", {}).get("bundle", {}).get("patch") != "./cordis.patch.yml":
        errors.append("host-tool package must declare its Cordis bundle patch")
    if "./icon" not in package.get("exports", {}) or "./locale/*.json" not in package.get("exports", {}):
        errors.append("host-tool package must export its icon and locale resources")
    required_package_files = {"AGENTS.md", "index.js", "scripts/*.js", "data/*.json", "data/schema/*.json", "locale/*.json", "icon.svg"}
    if not required_package_files.issubset(set(package.get("files", []))):
        errors.append("host-tool package files must include scripts, structured data, schemas, locales, and icon")
    if "@deepseek-ai/dsh-tools" not in package.get("peerDependencies", {}):
        errors.append("host-tool package must declare the DSH tool registry peer")
    try:
        ET.parse(template / "icon.svg")
    except ET.ParseError:
        errors.append("host-tool icon must be valid SVG")
    patch = (template / "cordis.patch.yml").read_text(encoding="utf-8")
    if "id: preset-knowledge-base-operations" not in patch or "name: '@local/domain-agent-scaffold'" not in patch:
        errors.append("bundle patch must mount the tool package inside its domain agent preset")
    if data_override is None:
        data = {path.name: load_json(path) for path in (template / "data").glob("*.json")}
        schemas = {path.name: load_json(path) for path in (template / "data/schema").glob("*.json")}
    else:
        data = data_override
        schemas = {path.name: load_json(path) for path in (template / "data/schema").glob("*.json")}
    instruction_resource = next((item for item in data.get("resource-catalog.json", {}).get("resources", []) if item.get("id") == "agent-instructions"), None)
    readable_resources = set(data.get("path-policy.json", {}).get("readResourceIds", []))
    if not instruction_resource or instruction_resource.get("path") != ".agents/domain-agents/template/AGENTS.md" or "agent-instructions" not in readable_resources:
        errors.append("subagent AGENTS.md must be an allowlisted resource for prompt loading")
    errors.extend(validate_data(data, schemas))
    for resource in data.get("resource-catalog.json", {}).get("resources", []):
        source = root / resource.get("path", "")
        if not source.is_file() or source.is_symlink() or root.resolve() not in source.resolve().parents:
            errors.append(f"registered resource source is missing or escapes the repository: {resource.get('id')}")
    return errors


def test_domain_agent_scaffold_conforms() -> None:
    assert scaffold_errors(paths.repository_root()) == []


def test_missing_rule_card_is_rejected() -> None:
    root = paths.repository_root()
    spec = (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    damaged = re.sub(r"(?ms)^### DA-04 .*?(?=^### DA-05 )", "", spec)
    assert any("rule headings must be exactly" in error for error in spec_errors(damaged))


def test_weakened_tool_only_rule_is_rejected() -> None:
    root = paths.repository_root()
    spec = (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    damaged = spec.replace("只调用该实例在宿主工具注册表中注册且已授权的工具", "优先调用工具", 1)
    assert any("DA-02 is missing required normative content" in error for error in spec_errors(damaged))


def test_non_card_prose_is_rejected() -> None:
    root = paths.repository_root()
    spec = (root / ".agents/domain-agents/spec.md").read_text(encoding="utf-8")
    damaged = spec.replace("## 1. 单领域 host-tool agent 约束\n", "## 1. 单领域 host-tool agent 约束\n说明文字\n", 1)
    assert any("non-card content" in error for error in spec_errors(damaged))


def test_absolute_resource_path_is_rejected() -> None:
    root = paths.repository_root()
    data = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data").glob("*.json")}
    data["resource-catalog.json"]["resources"][0]["path"] = "/etc/passwd"
    schemas = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data/schema").glob("*.json")}
    assert any("workspace-relative" in error for error in validate_data(data, schemas))


def test_unknown_read_resource_is_rejected() -> None:
    root = paths.repository_root()
    data = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data").glob("*.json")}
    data["path-policy.json"]["readResourceIds"].append("unregistered")
    schemas = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data/schema").glob("*.json")}
    assert any("unknown resources" in error for error in validate_data(data, schemas))


def test_unknown_review_transition_is_rejected() -> None:
    root = paths.repository_root()
    data = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data").glob("*.json")}
    data["review-workflow.json"]["stages"][0]["transitions"]["ready"] = "missing-stage"
    schemas = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data/schema").glob("*.json")}
    assert any("unknown transition target" in error for error in validate_data(data, schemas))


def test_unversioned_or_arbitrary_write_target_is_rejected() -> None:
    root = paths.repository_root()
    data = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data").glob("*.json")}
    data["path-policy.json"]["writeTargets"][0]["path"] = "../../AGENTS.md"
    schemas = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data/schema").glob("*.json")}
    assert any("version-guard CRUD" in error for error in validate_data(data, schemas))


def test_domain_agent_agents_files_are_guarded() -> None:
    assert ".agents/domain-agents/AGENTS.md" in REQUIRED_FILES
    assert ".agents/domain-agents/template/AGENTS.md" in REQUIRED_FILES


def test_missing_host_tool_registration_is_rejected() -> None:
    root = paths.repository_root()
    registration = (root / ".agents/domain-agents/template/scripts/registration.js").read_text(encoding="utf-8")
    source = registration.replace('definition(defineTool, runtime, "advance_review"', 'definition(defineTool, runtime, "other_tool"', 1)
    assert any("advance_review" in error for error in tool_registration_errors(source))


def test_domain_agent_index_and_directory_map_are_linked() -> None:
    root = paths.repository_root()
    index = (root / ".agents/knowledge-repository/AGENTS.md").read_text(encoding="utf-8")
    directory_map = (root / "knowledge-repository/directory-structure.md").read_text(encoding="utf-8")
    assert "../domain-agents/spec.md" in index
    assert ".agents/domain-agents/" in directory_map


def test_schema_contract_rejects_removed_required_field() -> None:
    root = paths.repository_root()
    schemas = {path.name: load_json(path) for path in (root / ".agents/domain-agents/template/data/schema").glob("*.json")}
    schemas["resource-catalog.schema.json"]["required"].remove("domainId")
    assert any("domainId" in error for error in schema_contract_errors(schemas))


def test_every_host_tool_javascript_source_parses() -> None:
    root = paths.repository_root()
    sources = sorted((root / ".agents/domain-agents/template").rglob("*.js"))
    assert sources
    for source in sources:
        result = subprocess.run(["node", "--check", str(source.relative_to(root))], cwd=root, capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"{source}: {result.stdout}{result.stderr}"


def test_host_tool_engine_node_suite_passes() -> None:
    root = paths.repository_root()
    result = subprocess.run(
        [
            "node",
            "--test",
            ".agents/domain-agents/template/tests/engine.test.js",
            ".agents/domain-agents/template/tests/runtime.test.js",
            ".agents/domain-agents/template/tests/registration.test.js",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
