export class DomainToolError extends Error {
  constructor(code, message) {
    super(message)
    this.name = "DomainToolError"
    this.code = code
  }
}

export function validateRelativePath(path) {
  if (typeof path !== "string" || path.length === 0 || path.startsWith("/") || path.includes("\\") || path.includes("\u0000") || /^[A-Za-z]:/.test(path)) {
    throw new DomainToolError("PATH_REJECTED", "path must be a non-empty workspace-relative POSIX path")
  }
  const segments = path.split("/")
  if (segments.some(segment => segment === ".." || segment === "." || segment.length === 0)) {
    throw new DomainToolError("PATH_REJECTED", "path traversal and empty path segments are forbidden")
  }
  return path
}

export function isSafeIdentifier(value) {
  return typeof value === "string" && /^[a-z0-9][a-z0-9-]{0,63}$/.test(value)
}

export function validateDomainCatalog(catalog) {
  if (!catalog || catalog.schemaVersion !== 1 || !Array.isArray(catalog.domains)) {
    throw new DomainToolError("INVALID_DOMAIN_CATALOG", "domain catalog schema is invalid")
  }
  const ids = new Set()
  for (const domain of catalog.domains) {
    if (!isSafeIdentifier(domain?.id) || typeof domain.title !== "string" || !Array.isArray(domain.repositoryIds) || domain.repositoryIds.length === 0) {
      throw new DomainToolError("INVALID_DOMAIN_CATALOG", "domain catalog contains an invalid entry")
    }
    if (ids.has(domain.id)) throw new DomainToolError("INVALID_DOMAIN_CATALOG", `domain ${domain.id} is registered more than once`)
    ids.add(domain.id)
    if (!Array.isArray(domain.repositoryIds) || domain.repositoryIds.some(id => !isSafeIdentifier(id))) {
      throw new DomainToolError("INVALID_DOMAIN_CATALOG", `domain ${domain.id} has invalid repository ids`)
    }
    if (new Set(domain.repositoryIds).size !== domain.repositoryIds.length) {
      throw new DomainToolError("INVALID_DOMAIN_CATALOG", `domain ${domain.id} repeats a repository id`)
    }
    try {
      validateRelativePath(domain.manifestPath)
    } catch {
      throw new DomainToolError("INVALID_DOMAIN_CATALOG", `domain ${domain.id} has an unsafe manifest path`)
    }
  }
  return catalog
}

export function validateDomainManifest(manifest, expectedDomainId) {
  const allowedFields = new Set(["schemaVersion", "domainId", "resources", "repositories", "operationMethods", "changeKinds"])
  if (manifest && Object.keys(manifest).some(key => !allowedFields.has(key))) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "domain manifest contains an unsupported capability field")
  if (!manifest || manifest.schemaVersion !== 1 || manifest.domainId !== expectedDomainId) {
    throw new DomainToolError("DOMAIN_MISMATCH", "domain manifest does not match the active domain")
  }
  for (const key of ["resources", "repositories", "operationMethods", "changeKinds"]) {
    if (!Array.isArray(manifest[key])) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `domain manifest field ${key} must be an array`)
  }
  const resources = new Map()
  for (const resource of manifest.resources) {
    if (!isSafeIdentifier(resource?.id) || !isSafeIdentifier(resource?.kind) || resources.has(resource.id) || typeof resource.title !== "string" || resource.format !== "markdown" || !Number.isSafeInteger(resource.maxBytes) || resource.maxBytes < 1 || resource.maxBytes > 1000000) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "domain manifest contains an invalid or duplicate resource")
    }
    try {
      validateRelativePath(resource.path)
    } catch {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `resource ${resource.id} has an unsafe path`)
    }
    resources.set(resource.id, resource)
  }
  const repositories = new Map()
  for (const repository of manifest.repositories) {
    if (!isSafeIdentifier(repository?.id) || repositories.has(repository.id) || repository.root !== `assets/projects/${repository.id}`) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "repository root must be the direct project checkout path")
    }
    try {
      validateRelativePath(repository.root)
    } catch {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `repository ${repository.id} has an unsafe root`)
    }
    if (!Array.isArray(repository.readPaths) || repository.readPaths.length === 0 || !Array.isArray(repository.denyPaths)) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `repository ${repository.id} has invalid read policy`)
    }
    for (const pattern of [...repository.readPaths, ...repository.denyPaths]) {
      if (typeof pattern !== "string" || pattern.length === 0 || pattern.startsWith("/") || pattern.includes("\\") || pattern.split("/").some(segment => segment === ".." || segment === ".")) {
        throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `repository ${repository.id} has an unsafe path policy`)
      }
    }
    if (!Number.isSafeInteger(repository.maxFileBytes) || repository.maxFileBytes < 1 || repository.maxFileBytes > 1000000 || !Number.isSafeInteger(repository.maxLines) || repository.maxLines < 1 || repository.maxLines > 200) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `repository ${repository.id} has invalid read bounds`)
    }
    repositories.set(repository.id, repository)
  }
  const operationIds = new Set()
  for (const operation of manifest.operationMethods) {
    if (!isSafeIdentifier(operation?.id) || operationIds.has(operation.id) || !repositories.has(operation.repositoryId) || !isSafeIdentifier(operation.methodId) || !Array.isArray(operation.resourceIds) || operation.resourceIds.length === 0) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "operation method mapping is invalid or ambiguous")
    }
    operationIds.add(operation.id)
    if (new Set(operation.resourceIds).size !== operation.resourceIds.length || operation.resourceIds.some(id => !resources.has(id))) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `operation ${operation.id} references an unregistered resource`)
    }
  }
  const changeKindIds = new Set()
  for (const changeKind of manifest.changeKinds) {
    if (!isSafeIdentifier(changeKind?.id) || changeKindIds.has(changeKind.id) || !Array.isArray(changeKind.layers) || changeKind.layers.length === 0 || changeKind.layers.some(layer => !["lint", "static", "live", "external"].includes(layer)) || !Array.isArray(changeKind.resourceIds) || changeKind.resourceIds.length === 0 || new Set(changeKind.resourceIds).size !== changeKind.resourceIds.length) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "change kind is invalid or duplicated")
    }
    changeKindIds.add(changeKind.id)
    if (changeKind.resourceIds.some(id => !resources.has(id))) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `change kind ${changeKind.id} references an unregistered resource`)
  }
  const testResource = resources.get("domain-tests")
  const validationOperation = manifest.operationMethods.find(item => item.id === "domain-knowledge-validation")
  const knowledgeChange = manifest.changeKinds.find(item => item.id === "domain-knowledge")
  if (testResource?.kind !== "domain-knowledge-test-entry" || testResource.path !== `assets/domain-knowledge/${manifest.domainId}/tests/README.md`) {
    throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "domain manifest must register its domain-tests resource at the standard tests README path")
  }
  if (!validationOperation || validationOperation.methodId !== "pytest" || !validationOperation.resourceIds.includes("domain-tests")) {
    throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "domain manifest must map domain-knowledge-validation to pytest and domain-tests")
  }
  if (!knowledgeChange || !knowledgeChange.layers.includes("lint") || !knowledgeChange.resourceIds.includes("domain-tests")) {
    throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "domain manifest must expose domain-knowledge lint through domain-tests")
  }
  for (const repository of repositories.values()) {
    const development = repository.development
    if (development === undefined) continue
    const fields = ["writePaths", "changeKind", "operationId", "argv"]
    if (!development || Object.keys(development).some(key => !fields.includes(key)) || !Array.isArray(development.writePaths) || development.writePaths.length === 0 || new Set(development.writePaths).size !== development.writePaths.length) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "development policy must declare unique write paths")
    for (const pattern of development.writePaths) {
      validateRelativePath(pattern)
      if (!repository.readPaths.some(read => read === pattern || (read.endsWith("/**") && pattern.startsWith(`${read.slice(0, -3)}/`)))) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "development write paths must be within readable paths")
    }
    const operation = manifest.operationMethods.find(item => item.id === development.operationId && item.repositoryId === repository.id)
    const change = manifest.changeKinds.find(item => item.id === development.changeKind)
    const testResource = resources.get("project-tests")
    if (!operation || operation.methodId !== "pytest" || !change || !operation.resourceIds.includes("project-tests") || !change.resourceIds.includes("project-tests") || testResource?.path !== `${repository.root}/tests/README.md` || testResource?.kind !== "project-test-entry" || !pathPolicyAllows("tests/README.md", repository)) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "development must map a readable project-tests entry to its pytest operation and change kind")
    if (!Array.isArray(development.argv) || development.argv.length === 0 || development.argv.length > 64 || development.argv.some(arg => typeof arg !== "string" || arg.trim().length === 0 || arg.length > 4000 || arg.includes("\u0000")) || development.argv.reduce((size, arg) => size + arg.length, 0) > 32768) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "development must register bounded test argv")
  }
  return { resources, repositories }
}

function pathMatches(pattern, path) {
  if (pattern.endsWith("/**")) {
    const root = pattern.slice(0, -3).replace(/\/$/, "")
    return path === root || path.startsWith(`${root}/`)
  }
  if (pattern.startsWith("**/")) {
    const suffixPattern = pattern.slice(3)
    return pathMatches(suffixPattern, path) || path.split("/").some(segment => pathMatches(suffixPattern, segment))
  }
  if (!pattern.includes("*")) return path === pattern
  const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]*")
  return new RegExp(`^${escaped}$`).test(path)
}

export function pathPolicyAllows(path, repository) {
  const denied = repository.denyPaths.some(pattern => pathMatches(pattern, path))
  if (denied) return false
  return repository.readPaths.some(pattern => pathMatches(pattern, path))
}

export function pathPolicyMayContain(path, repository) {
  if (path.length === 0) return true
  if (repository.denyPaths.some(pattern => pathMatches(pattern, path))) return false
  return repository.readPaths.some(pattern => {
    if (pathMatches(pattern, path)) return true
    const base = pattern.endsWith("/**") ? pattern.slice(0, -3).replace(/\/$/, "") : pattern
    return base.startsWith(`${path}/`)
  })
}
