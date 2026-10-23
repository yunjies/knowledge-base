import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOMAIN = ROOT / "assets/domain-knowledge/dsh-credentials"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_errors(value: object, schema: dict, location: str = "$") -> list[str]:
    errors = []
    expected = schema.get("type")
    type_checks = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected in type_checks and not type_checks[expected]:
        return [f"{location} must be {expected}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location} has wrong constant")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location} is outside enum")
    if isinstance(value, int) and not isinstance(value, bool):
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            errors.append(f"{location} is outside numeric bounds")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{location} is too short")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{location} does not match pattern")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{location} has too few items")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            errors.append(f"{location} has duplicate items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], f"{location}[{index}]"))
    if isinstance(value, dict):
        errors.extend(f"{location}.{key} is required" for key in schema.get("required", []) if key not in value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors.extend(f"{location}.{key} is not allowed" for key in value if key not in properties)
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(schema_errors(value[key], child_schema, f"{location}.{key}"))
    return errors


def test_global_domain_catalog_points_to_this_manifest() -> None:
    schema = load_json(ROOT / ".agents/domain-agents/template/data/schema/domain-catalog.schema.json")
    catalog = load_json(ROOT / "assets/domain-knowledge/catalog.json")
    assert schema_errors(catalog, schema) == []
    entries = {item["id"]: item for item in catalog["domains"]}
    assert entries["dsh-credentials"]["manifestPath"] == "dsh-credentials/data/manifest.json"
    assert entries["dsh-credentials"]["repositoryIds"] == ["dsh-credentials"]
    assert (ROOT / "assets/domain-knowledge" / entries["dsh-credentials"]["manifestPath"]).is_file()


def test_manifest_has_registered_resources_and_operation_mappings() -> None:
    schema = load_json(ROOT / ".agents/domain-agents/template/data/schema/domain-manifest.schema.json")
    manifest = load_json(DOMAIN / "data/manifest.json")
    assert schema_errors(manifest, schema) == []
    assert manifest["domainId"] == "dsh-credentials"
    resource_ids = [item["id"] for item in manifest["resources"]]
    repository_ids = [item["id"] for item in manifest["repositories"]]
    operation_ids = [item["id"] for item in manifest["operationMethods"]]
    change_kind_ids = [item["id"] for item in manifest["changeKinds"]]
    assert len(resource_ids) == len(set(resource_ids))
    assert repository_ids == ["dsh-credentials"]
    assert len(repository_ids) == len(set(repository_ids))
    assert len(operation_ids) == len(set(operation_ids))
    assert len(change_kind_ids) == len(set(change_kind_ids))
    assert all(item["repositoryId"] in repository_ids for item in manifest["operationMethods"])
    assert all(set(item["resourceIds"]) <= set(resource_ids) for item in manifest["operationMethods"])
    assert all(set(item["resourceIds"]) <= set(resource_ids) for item in manifest["changeKinds"])
    assert {item["id"]: item["methodId"] for item in manifest["operationMethods"]} == {
        "local-version-control": "git-cli",
        "github-remote": "github-cli",
        "dsh-profile-install": "dsh-plugin-cli",
        "domain-knowledge-validation": "pytest",
        "project-source-validation": "npm-test",
    }
    assert {
        item["id"]: set(item["resourceIds"])
        for item in manifest["operationMethods"]
    } == {
        "local-version-control": {"version-management"},
        "github-remote": {"version-management", "github-cli-constraints"},
        "dsh-profile-install": {"dsh-deployment", "project-build"},
        "domain-knowledge-validation": {"domain-tests"},
        "project-source-validation": {"project-tests"},
    }
    referenced_resource_ids = {
        resource_id
        for item in [*manifest["operationMethods"], *manifest["changeKinds"]]
        for resource_id in item["resourceIds"]
    }
    assert set(resource_ids) == referenced_resource_ids


def test_manifest_resources_are_workspace_relative_and_present() -> None:
    manifest = load_json(DOMAIN / "data/manifest.json")
    for item in manifest["resources"]:
        path = Path(item["path"])
        assert not path.is_absolute()
        assert ".." not in path.parts
        assert (ROOT / path).is_file()
        assert item["format"] == "markdown"
        assert isinstance(item["maxBytes"], int) and item["maxBytes"] > 0
        assert item["maxBytes"] <= 1_000_000


def test_manifest_repository_read_permissions_and_size_limits() -> None:
    manifest = load_json(DOMAIN / "data/manifest.json")
    repository = manifest["repositories"][0]
    assert repository["readPaths"] == [
        "README.md",
        "package.json",
        "bundle.patch.yml",
        "loader-configs/build.json",
        "src/**",
        "tests/**",
        "scripts/**",
    ]
    assert repository["denyPaths"] == [
        ".git/**",
        "node_modules/**",
        "dist/**",
        "tests/.artifacts/**",
        "**/.env*",
        "**/*.log",
    ]
    assert isinstance(repository["maxFileBytes"], int)
    assert 0 < repository["maxFileBytes"] <= 1_000_000
    assert isinstance(repository["maxLines"], int)
    assert 0 < repository["maxLines"] <= 200


def test_project_source_is_directly_under_projects_with_read_boundaries() -> None:
    manifest = load_json(DOMAIN / "data/manifest.json")
    repository = manifest["repositories"][0]
    assert repository["id"] == "dsh-credentials"
    assert repository["root"] == "assets/projects/dsh-credentials"
    assert (ROOT / repository["root"] / ".git").exists()
    assert "src/**" in repository["readPaths"]
    assert "tests/**" in repository["readPaths"]
    assert ".git/**" in repository["denyPaths"]
    assert "node_modules/**" in repository["denyPaths"]


def test_target_connection_state_docs_match_the_source_state_vocabulary() -> None:
    source = (ROOT / "assets/projects/dsh-credentials/src/shared/targets.ts").read_text(encoding="utf-8")
    state_match = re.search(r"export type ConnectionState = ([^\n]+)", source)
    assert state_match is not None
    states = set(re.findall(r"'([^']+)'", state_match.group(1)))
    expected = {
        "connected": "已连接",
        "unauthenticated": "认证失败",
        "unreachable": "连不上",
        "sandbox-denied": "沙箱拒绝",
        "spawn-failed": "本机无法执行",
        "unknown": "未检测",
    }
    assert states == set(expected)
    badges = source.split("export function stateBadge(", 1)[1].split("export function originBadge(", 1)[0]
    explicit_badges = dict(re.findall(r"case '([^']+)':\s*return\s*\{\s*text:\s*'([^']+)'", badges))
    for state, label in expected.items():
        if state == "unknown":
            assert re.search(r"default:\s*return\s*\{\s*text:\s*'未检测'", badges)
        else:
            assert explicit_badges[state] == label
        assert label in (ROOT / "assets/projects/dsh-credentials/README.md").read_text(encoding="utf-8")
        assert label in (DOMAIN / "feature-flow.md").read_text(encoding="utf-8")


def test_domain_deploy_and_audit_are_indexed_without_duplication() -> None:
    index = (DOMAIN / "README.md").read_text(encoding="utf-8")
    deploy = (DOMAIN / "deploy.md").read_text(encoding="utf-8")
    assert "audit-record-loop-flow.md" in index
    assert "audit-perspectives.md" in index
    assert not (DOMAIN / "review-guide.md").exists()
    assert "README.md#构建" in deploy
    assert "tests/README.md" in deploy
    assert 'dsh plugin add --profile "$PROFILE" "file:$PROJECT_ROOT"' in deploy
    assert 'dsh --profile "$PROFILE"' in deploy
    assert 'dsh --profile "$PROFILE" --dump-config' in deploy
    assert "npm run build:bundle" not in deploy
    shell_block = re.search(r"```sh\n(.*?)\n```", deploy, re.DOTALL)
    assert shell_block is not None
    subprocess.run(["sh", "-n", "-c", shell_block.group(1)], check=True)
