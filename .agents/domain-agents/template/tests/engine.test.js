import assert from "node:assert/strict"
import { test } from "node:test"
import { DomainToolError, isSafeIdentifier, pathPolicyAllows, pathPolicyMayContain, validateDomainCatalog, validateDomainManifest, validateRelativePath } from "../scripts/engine.js"

function manifest() {
  return {
    schemaVersion: 1,
    domainId: "sample-domain",
    resources: [
      { id: "flow", kind: "implemented-flow", title: "Flow", path: "assets/domain-knowledge/sample-domain/flow.md", format: "markdown", maxBytes: 10000 },
      { id: "domain-tests", kind: "domain-knowledge-test-entry", title: "Domain tests", path: "assets/domain-knowledge/sample-domain/tests/README.md", format: "markdown", maxBytes: 10000 },
      { id: "project-tests", kind: "project-test-entry", title: "Project tests", path: "assets/projects/sample-repo/tests/README.md", format: "markdown", maxBytes: 10000 }
    ],
    repositories: [
      { id: "sample-repo", root: "assets/projects/sample-repo", readPaths: ["README.md", "src/**", "tests/**"], denyPaths: [".git/**", "src/.env*"], maxFileBytes: 50000, maxLines: 200, development: { writePaths: ["src/**"], changeKind: "source-change", operationId: "project-validation", argv: ["node", "--test", "tests/example.test.js"] } }
    ],
    operationMethods: [
      { id: "github-remote", repositoryId: "sample-repo", methodId: "github-cli", resourceIds: ["flow"] },
      { id: "domain-knowledge-validation", repositoryId: "sample-repo", methodId: "pytest", resourceIds: ["domain-tests"] },
      { id: "project-validation", repositoryId: "sample-repo", methodId: "pytest", resourceIds: ["project-tests"] }
    ],
    changeKinds: [
      { id: "source-change", layers: ["static"], resourceIds: ["flow", "project-tests"] },
      { id: "domain-knowledge", layers: ["lint"], resourceIds: ["domain-tests"] }
    ]
  }
}

test("relative paths and identifiers reject unbounded values", () => {
  assert.equal(validateRelativePath("src/host/index.ts"), "src/host/index.ts")
  assert.throws(() => validateRelativePath("/etc/passwd"), error => error instanceof DomainToolError && error.code === "PATH_REJECTED")
  assert.throws(() => validateRelativePath("src/../secret"), error => error instanceof DomainToolError && error.code === "PATH_REJECTED")
  assert.equal(isSafeIdentifier("dsh-credentials"), true)
  assert.equal(isSafeIdentifier("../secret"), false)
})

test("domain catalog rejects duplicate identities and unsafe manifest paths", () => {
  const catalog = { schemaVersion: 1, domains: [{ id: "sample-domain", title: "Sample", repositoryIds: ["sample-repo"], manifestPath: "sample-domain/data/manifest.json" }] }
  assert.equal(validateDomainCatalog(catalog), catalog)
  assert.throws(() => validateDomainCatalog({ ...catalog, domains: [...catalog.domains, catalog.domains[0]] }), error => error.code === "INVALID_DOMAIN_CATALOG")
  assert.throws(() => validateDomainCatalog({ ...catalog, domains: [{ ...catalog.domains[0], manifestPath: "../manifest.json" }] }), error => error.code === "INVALID_DOMAIN_CATALOG")
})

test("domain manifest resolves stable resource and method mappings", () => {
  const value = manifest()
  const result = validateDomainManifest(value, "sample-domain")
  assert.equal(result.resources.get("flow").path, "assets/domain-knowledge/sample-domain/flow.md")
  assert.equal(result.repositories.get("sample-repo").root, "assets/projects/sample-repo")
  assert.throws(() => validateDomainManifest(value, "other-domain"), error => error.code === "DOMAIN_MISMATCH")
})

test("optional development policy binds exact writes to a registered test operation", () => {
  const value = manifest()
  const repositories = validateDomainManifest(value, "sample-domain").repositories
  assert.deepEqual(repositories.get("sample-repo").development.writePaths, ["src/**"])
  const wrongMethod = manifest()
  wrongMethod.operationMethods.find(operation => operation.id === "project-validation").methodId = "manual"
  assert.throws(() => validateDomainManifest(wrongMethod, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
  const missingTestResource = manifest()
  missingTestResource.resources = missingTestResource.resources.filter(resource => resource.id !== "project-tests")
  assert.throws(() => validateDomainManifest(missingTestResource, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
  const outOfReadScope = manifest()
  outOfReadScope.repositories[0].development.writePaths = ["config/**"]
  assert.throws(() => validateDomainManifest(outOfReadScope, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
  const unsafeArgv = manifest()
  unsafeArgv.repositories[0].development.argv = ["node", "\u0000"]
  assert.throws(() => validateDomainManifest(unsafeArgv, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
})

test("domain manifest requires one standard domain-knowledge lint contract", () => {
  const missingTestResource = manifest()
  missingTestResource.resources = missingTestResource.resources.filter(resource => resource.id !== "domain-tests")
  assert.throws(() => validateDomainManifest(missingTestResource, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")

  const missingOperation = manifest()
  missingOperation.operationMethods = missingOperation.operationMethods.filter(operation => operation.id !== "domain-knowledge-validation")
  assert.throws(() => validateDomainManifest(missingOperation, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")

  const missingChangeKind = manifest()
  missingChangeKind.changeKinds = missingChangeKind.changeKinds.filter(changeKind => changeKind.id !== "domain-knowledge")
  assert.throws(() => validateDomainManifest(missingChangeKind, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")

  const wrongMethod = manifest()
  wrongMethod.operationMethods.find(operation => operation.id === "domain-knowledge-validation").methodId = "manual"
  assert.throws(() => validateDomainManifest(wrongMethod, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
})

test("domain manifest rejects traversal, duplicate methods, and cross-repository mappings", () => {
  const unsafePath = manifest()
  unsafePath.resources[0].path = "assets/domain-knowledge/../private.md"
  assert.throws(() => validateDomainManifest(unsafePath, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
  const duplicate = manifest()
  duplicate.operationMethods.push({ ...duplicate.operationMethods[0] })
  assert.throws(() => validateDomainManifest(duplicate, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
  const crossRepo = manifest()
  crossRepo.operationMethods[0].repositoryId = "unknown-repo"
  assert.throws(() => validateDomainManifest(crossRepo, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
  const writeCapability = manifest()
  writeCapability.writeTargets = [{ id: "records", path: "data/store.json", operations: ["update"], versionGuarded: true }]
  assert.throws(() => validateDomainManifest(writeCapability, "sample-domain"), error => error.code === "INVALID_DOMAIN_MANIFEST")
})

test("repository policy permits only registered paths and denies sensitive patterns", () => {
  const repository = manifest().repositories[0]
  assert.equal(pathPolicyAllows("src/host/tool.ts", repository), true)
  assert.equal(pathPolicyAllows("README.md", repository), true)
  assert.equal(pathPolicyAllows("tests/README.md", repository), true)
  assert.equal(pathPolicyAllows("src/.env.local", repository), false)
  assert.equal(pathPolicyMayContain("src", repository), true)
  assert.equal(pathPolicyMayContain("node_modules", repository), false)
})
