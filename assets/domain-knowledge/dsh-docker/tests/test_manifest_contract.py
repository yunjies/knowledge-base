import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOMAIN_ID = "dsh-docker"
REPOSITORY_ID = "docker-for-dsh"


def test_catalog_registers_domain_and_repository():
    catalog = json.loads((ROOT / "assets/domain-knowledge/catalog.json").read_text())
    entry = next(domain for domain in catalog["domains"] if domain["id"] == DOMAIN_ID)
    assert entry["manifestPath"] == f"{DOMAIN_ID}/data/manifest.json"
    assert entry["repositoryIds"] == [REPOSITORY_ID]


def test_manifest_has_standard_validation_contract():
    manifest_path = ROOT / "assets/domain-knowledge" / DOMAIN_ID / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schemaVersion"] == 1
    assert manifest["domainId"] == DOMAIN_ID
    repository = next(repo for repo in manifest["repositories"] if repo["id"] == REPOSITORY_ID)
    assert repository["root"] == f"assets/projects/{REPOSITORY_ID}"
    assert (ROOT / repository["root"]).is_dir()
    resources = {resource["id"]: resource for resource in manifest["resources"]}
    assert resources["domain-tests"]["kind"] == "domain-knowledge-test-entry"
    assert resources["domain-tests"]["path"] == f"assets/domain-knowledge/{DOMAIN_ID}/tests/README.md"
    for resource in resources.values():
        assert (ROOT / resource["path"]).is_file()
    validation = next(method for method in manifest["operationMethods"] if method["id"] == "domain-knowledge-validation")
    assert validation["repositoryId"] == REPOSITORY_ID
    assert validation["methodId"] == "pytest"
    assert "domain-tests" in validation["resourceIds"]
    knowledge_change = next(change for change in manifest["changeKinds"] if change["id"] == "domain-knowledge")
    assert "lint" in knowledge_change["layers"]
    assert "domain-tests" in knowledge_change["resourceIds"]
