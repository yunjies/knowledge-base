import { readFile } from "node:fs/promises"
import { DomainToolError, isSafeIdentifier, pathPolicyAllows, pathPolicyMayContain, validateDomainCatalog, validateDomainManifest, validateRelativePath } from "./engine.js"

const MAX_DOMAIN_CATALOG_BYTES = 200000
const MAX_DOMAIN_MANIFEST_BYTES = 1000000
const MAX_RESOURCE_LINES = 200
const MAX_DIRECTORY_ENTRIES = 100
const DOMAIN_TEST_TIMEOUT_MS = 600000
const MAX_TEST_OUTPUT_CHARS = 20000

async function readBoundedText(ctx, target, maxBytes, signal) {
  const stream = await ctx.fs.streamText(target, signal)
  const chunks = []
  let size = 0
  for await (const chunk of stream) {
    size += Buffer.byteLength(chunk, "utf8")
    if (size > maxBytes) throw new DomainToolError("RESOURCE_TOO_LARGE", "resource exceeds its registered byte limit")
    chunks.push(chunk)
  }
  return chunks.join("")
}

function workspaceRoot(exec) {
  const cwd = exec.agent?.session?.header?.cwd
  if (typeof cwd !== "string" || cwd.length === 0) throw new DomainToolError("WORKSPACE_UNAVAILABLE", "calling agent has no workspace root")
  return cwd
}

function joinRelative(left, right) {
  const prefix = validateRelativePath(left)
  const suffix = validateRelativePath(right)
  return `${prefix}/${suffix}`
}

async function rejectSymlinkComponents(ctx, relativePath, cwd, signal) {
  const path = validateRelativePath(relativePath)
  let prefix = ""
  for (const segment of path.split("/")) {
    prefix = prefix === "" ? segment : `${prefix}/${segment}`
    const info = await ctx.fs.lstat(prefix, { cwd }, signal)
    if (!info) break
    if (info.type === "symlink") throw new DomainToolError("PATH_SYMLINK", "registered paths cannot traverse symbolic links")
  }
}

async function resolveInside(ctx, relativePath, parentPath, cwd, signal) {
  const path = validateRelativePath(relativePath)
  await rejectSymlinkComponents(ctx, path, cwd, signal)
  const target = await ctx.fs.resolve(path, { cwd, signal })
  const root = await ctx.fs.resolve(cwd, { cwd, signal })
  const parent = parentPath ? await ctx.fs.resolve(validateRelativePath(parentPath), { cwd, signal }) : root
  if (!ctx.fs.contains(root, parent) || !ctx.fs.contains(parent, target)) {
    throw new DomainToolError("PATH_OUTSIDE_SCOPE", "resolved path is outside its registered root")
  }
  return target
}

async function readJson(ctx, exec, path, parentPath, limit) {
  const cwd = workspaceRoot(exec)
  const target = await resolveInside(ctx, path, parentPath, cwd, exec.signal)
  const info = await ctx.fs.stat(target, exec.signal)
  if (!info || info.type !== "file") throw new DomainToolError("DATA_FILE_MISSING", "registered JSON resource is missing or is not a regular file")
  if (info.size !== undefined && info.size > limit) throw new DomainToolError("DATA_FILE_TOO_LARGE", "registered JSON resource exceeds its byte limit")
  const text = await readBoundedText(ctx, target, limit, exec.signal)
  try {
    return JSON.parse(text)
  } catch {
    throw new DomainToolError("INVALID_JSON", "registered JSON resource is not valid JSON")
  }
}

function validateRelativePatterns(patterns, name) {
  if (!Array.isArray(patterns) || patterns.length === 0) throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `${name} must be a non-empty path-pattern array`)
  for (const pattern of patterns) {
    if (typeof pattern !== "string" || pattern.length === 0 || pattern.startsWith("/") || pattern.includes("\\") || pattern.split("/").some(segment => segment === ".." || segment === "." || segment.length === 0)) {
      throw new DomainToolError("INVALID_DOMAIN_MANIFEST", `${name} contains an unsafe path pattern`)
    }
  }
}

async function loadDomainCatalog(ctx, exec, knowledgeRoot) {
  const root = validateRelativePath(knowledgeRoot)
  const catalog = await readJson(ctx, exec, joinRelative(root, "catalog.json"), root, MAX_DOMAIN_CATALOG_BYTES)
  return validateDomainCatalog(catalog)
}

function splitLines(text, offset, limit) {
  if (!Number.isSafeInteger(offset) || offset < 1) throw new DomainToolError("INVALID_RANGE", "offset must be a positive line number")
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_RESOURCE_LINES) throw new DomainToolError("INVALID_RANGE", `limit must be between 1 and ${MAX_RESOURCE_LINES}`)
  const lines = text.split(/\r?\n/)
  const selected = lines.slice(offset - 1, offset - 1 + limit)
  const nextIndex = offset - 1 + selected.length
  return {
    offset,
    lines: selected.map((text, index) => ({ number: offset + index, text })),
    totalLines: lines.length,
    ...(nextIndex < lines.length ? { nextOffset: nextIndex + 1 } : {})
  }
}

function checkedResource(scope, resourceId) {
  const resource = scope.indexes.resources.get(resourceId)
  if (!resource) throw new DomainToolError("RESOURCE_NOT_ALLOWED", "resource is not registered in the active domain")
  return resource
}

function boundedTestOutput(value) {
  const text = typeof value === "string" ? value : ""
  return {
    text: text.length > MAX_TEST_OUTPUT_CHARS ? text.slice(-MAX_TEST_OUTPUT_CHARS) : text,
    truncated: text.length > MAX_TEST_OUTPUT_CHARS
  }
}

export async function runDomainKnowledgeLint(ctx, scope, exec) {
  const testResource = scope.indexes.resources.get("domain-tests")
  if (!testResource || testResource.path !== `assets/domain-knowledge/${scope.domainId}/tests/README.md`) {
    throw new DomainToolError("INVALID_DOMAIN_MANIFEST", "domain knowledge lint test entry is not registered at the standard path")
  }
  const testPath = `assets/domain-knowledge/${scope.domainId}/tests`
  const command = `UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest ${testPath} -q`
  let handle
  try {
    const uvPath = await ctx.subprocess.resolveExecutable("uv", undefined, exec.signal)
    handle = ctx.subprocess.spawn({
      argv: [uvPath, "run", "--with", "pytest==9.1.1", "pytest", testPath, "-q"],
      cwd: scope.workspaceRoot,
      env: { ...process.env, UV_CACHE_DIR: ".uv-cache" },
      stdio: { stdin: "ignore", stdout: { maxBytes: MAX_TEST_OUTPUT_CHARS }, stderr: { maxBytes: MAX_TEST_OUTPUT_CHARS } },
      graceMs: 1000,
      signal: exec.signal
    })
  } catch (error) {
    if (exec.signal.aborted) throw error
    return {
      domainId: scope.domainId,
      repositoryId: scope.repository.id,
      command,
      exitCode: -1,
      passed: false,
      stdout: "",
      stderr: "",
      outputTruncated: false,
      errorMessage: String(error?.message ?? "subprocess provider could not start pytest").slice(0, 2000)
    }
  }
  let outcome
  let errorMessage = ""
  try {
    outcome = await handle.done
  } catch (error) {
    if (exec.signal.aborted) throw error
    errorMessage = String(error?.message ?? "subprocess provider failed").slice(0, 2000)
  }
  const stdout = handle.collected.stdout?.readFrom(0)
  const stderr = handle.collected.stderr?.readFrom(0)
  if (!stdout || !stderr) errorMessage ||= "subprocess output was not collected"
  const exitCode = outcome?.exitCode ?? -1
  return {
    domainId: scope.domainId,
    repositoryId: scope.repository.id,
    command,
    exitCode,
    passed: errorMessage === "" && exitCode === 0 && outcome?.signal === null,
    stdout: boundedTestOutput(stdout?.text).text,
    stderr: boundedTestOutput(stderr?.text).text,
    outputTruncated: Boolean(stdout?.lossy || stderr?.lossy),
    errorMessage
  }
}

function isDeniedPath(path, repository) {
  return repository.denyPaths.some(pattern => pathPolicyAllows(path, { readPaths: [pattern], denyPaths: [] }))
}

export function createInvocationRuntime(ctx, scope) {
  const getProjectSource = async (args, exec) => {
    const relativePath = validateRelativePath(args.relativePath)
    if (isDeniedPath(relativePath, scope.repository) || !pathPolicyAllows(relativePath, scope.repository)) throw new DomainToolError("PATH_NOT_ALLOWED", "source path is not registered as readable")
    const fullPath = `${scope.repository.root}/${relativePath}`
    const target = await resolveInside(ctx, fullPath, scope.repository.root, scope.workspaceRoot, exec.signal)
    const info = await ctx.fs.stat(target, exec.signal)
    if (!info || info.type !== "file") throw new DomainToolError("SOURCE_FILE_MISSING", "source path is missing or is not a regular file")
    if (info.size !== undefined && info.size > scope.repository.maxFileBytes) throw new DomainToolError("SOURCE_TOO_LARGE", "source file exceeds its registered byte limit")
    const text = await readBoundedText(ctx, target, scope.repository.maxFileBytes, exec.signal)
    const result = splitLines(text, args.offset ?? 1, args.limit ?? scope.repository.maxLines)
    return { domainId: scope.domainId, repositoryId: scope.repository.id, relativePath, sourceVersion: info.version, ...result }
  }
  return {
    getAccessPaths() {
      return {
        domainId: scope.domainId,
        repositoryId: scope.repository.id,
        repositoryRoot: scope.repository.root,
        readPaths: [...scope.repository.readPaths],
        denyPaths: [...scope.repository.denyPaths],
        resourceIds: [...scope.indexes.resources.keys()],
        operationIds: scope.manifest.operationMethods.filter(item => item.repositoryId === scope.repository.id).map(item => item.id)
      }
    },
    getOperationMethod(args) {
      const operation = scope.manifest.operationMethods.find(item => item.id === args.operationId && item.repositoryId === scope.repository.id)
      if (!operation) throw new DomainToolError("UNKNOWN_OPERATION", "operationId is not registered for the active repository")
      return { domainId: scope.domainId, repositoryId: scope.repository.id, operationId: operation.id, methodId: operation.methodId, resourceIds: [...operation.resourceIds] }
    },
    async getKnowledgeResource(args, exec) {
      const resource = checkedResource(scope, args.resourceId)
      const target = await resolveInside(ctx, resource.path, undefined, scope.workspaceRoot, exec.signal)
      const info = await ctx.fs.stat(target, exec.signal)
      if (!info || info.type !== "file") throw new DomainToolError("RESOURCE_MISSING", "registered resource is missing or is not a regular file")
      if (info.size !== undefined && info.size > resource.maxBytes) throw new DomainToolError("RESOURCE_TOO_LARGE", "resource exceeds its registered byte limit")
      const text = await readBoundedText(ctx, target, resource.maxBytes, exec.signal)
      return { domainId: scope.domainId, resourceId: resource.id, kind: resource.kind, title: resource.title, path: resource.path, sourceVersion: info.version, ...splitLines(text, args.offset ?? 1, args.limit ?? 120) }
    },
    async getTestSpecification(args) {
      const changeKind = scope.manifest.changeKinds.find(item => item.id === args.changeKind)
      if (!changeKind) throw new DomainToolError("UNKNOWN_CHANGE_KIND", "change kind is not registered for the active domain")
      return { domainId: scope.domainId, ...changeKind }
    },
    async listProjectFiles(args, exec) {
      const relativePath = args.relativePath === undefined ? "" : args.relativePath
      if (relativePath !== "") validateRelativePath(relativePath)
      if (!pathPolicyMayContain(relativePath, scope.repository)) throw new DomainToolError("PATH_NOT_ALLOWED", "directory is outside the registered read paths")
      if (isDeniedPath(relativePath, scope.repository)) throw new DomainToolError("PATH_NOT_ALLOWED", "directory is denied by the repository policy")
      const path = relativePath === "" ? scope.repository.root : `${scope.repository.root}/${relativePath}`
      const target = await resolveInside(ctx, path, scope.repository.root, scope.workspaceRoot, exec.signal)
      const info = await ctx.fs.stat(target, exec.signal)
      if (!info || info.type !== "directory") throw new DomainToolError("DIRECTORY_MISSING", "source directory is missing or is not a directory")
      const entries = await ctx.fs.listDir(target, exec.signal)
      const offset = args.offset ?? 0
      const limit = args.limit ?? 100
      if (!Number.isSafeInteger(offset) || offset < 0) throw new DomainToolError("INVALID_RANGE", "offset must be a non-negative integer")
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_DIRECTORY_ENTRIES) throw new DomainToolError("INVALID_RANGE", `limit must be between 1 and ${MAX_DIRECTORY_ENTRIES}`)
      const visible = []
      for (const entry of entries) {
        if (entry.type === "other") continue
        const childPath = relativePath === "" ? entry.name : `${relativePath}/${entry.name}`
        if (isDeniedPath(childPath, scope.repository)) continue
        if (!pathPolicyAllows(childPath, scope.repository) && !(entry.type === "directory" && pathPolicyMayContain(childPath, scope.repository))) continue
        const childInfo = await ctx.fs.lstat(`${scope.repository.root}/${childPath}`, { cwd: scope.workspaceRoot }, exec.signal)
        if (!childInfo || childInfo.type === "symlink") continue
        visible.push(entry)
      }
      const selected = visible.slice(offset, offset + limit)
      return {
        domainId: scope.domainId,
        repositoryId: scope.repository.id,
        relativePath,
        entries: selected.map(entry => ({ path: relativePath === "" ? entry.name : `${relativePath}/${entry.name}`, type: entry.type, ...(entry.size === undefined ? {} : { size: entry.size }) })),
        ...(offset + selected.length < visible.length ? { nextOffset: offset + selected.length } : {})
      }
    },
    getProjectSource,
    async submitAuditFindings(args, exec) {
      if (!Array.isArray(args.findings) || args.findings.length > 30) throw new DomainToolError("INVALID_FINDINGS", "findings must be an array with at most 30 entries")
      const findings = []
      for (const [index, finding] of args.findings.entries()) {
        if (!finding || typeof finding.title !== "string" || finding.title.trim().length === 0 || finding.title.length > 500) throw new DomainToolError("INVALID_FINDING", `finding ${index} has an invalid title`)
        if (!['blocker', 'high', 'medium', 'low'].includes(finding.severity)) throw new DomainToolError("INVALID_FINDING", `finding ${index} has an invalid severity`)
        for (const field of ['claim', 'counterargument', 'falsificationCondition']) {
          if (typeof finding[field] !== 'string' || finding[field].trim().length === 0 || finding[field].length > 4000) throw new DomainToolError("INVALID_FINDING", `finding ${index} has an invalid ${field}`)
        }
        if (!Number.isSafeInteger(finding.startLine) || !Number.isSafeInteger(finding.endLine) || finding.startLine < 1 || finding.endLine < finding.startLine || finding.endLine - finding.startLine > 19) throw new DomainToolError("INVALID_FINDING", `finding ${index} has an invalid evidence range`)
        const source = await getProjectSource({ relativePath: finding.relativePath, offset: finding.startLine, limit: finding.endLine - finding.startLine + 1 }, exec)
        if (source.lines.length !== finding.endLine - finding.startLine + 1) throw new DomainToolError("INVALID_FINDING", `finding ${index} evidence range extends beyond the source file`)
        findings.push({
          title: finding.title.trim(), severity: finding.severity, claim: finding.claim.trim(),
          counterargument: finding.counterargument.trim(), falsificationCondition: finding.falsificationCondition.trim(),
          evidence: { relativePath: source.relativePath, startLine: finding.startLine, endLine: finding.endLine, sourceVersion: source.sourceVersion, lines: source.lines }
        })
      }
      return { domainId: scope.domainId, repositoryId: scope.repository.id, findings }
    }
  }
}

export async function loadAgentInstructions() {
  return readFile(new URL("../AGENTS.md", import.meta.url), "utf8")
}

export async function listDomainCatalog(ctx, config, exec) {
  const cwd = workspaceRoot(exec)
  const knowledgeRoot = validateRelativePath(config.domainKnowledgeRoot)
  const catalog = await loadDomainCatalog(ctx, exec, knowledgeRoot)
  return {
    domains: catalog.domains.map(domain => ({ id: domain.id, title: domain.title, repositoryIds: [...domain.repositoryIds] }))
  }
}

export async function loadDomainScope(ctx, exec, config, domainId, repositoryId) {
  if (!isSafeIdentifier(domainId)) throw new DomainToolError("UNKNOWN_DOMAIN", "domainId must be a registered identifier")
  if (!isSafeIdentifier(repositoryId)) throw new DomainToolError("UNKNOWN_REPOSITORY", "repositoryId must be a registered identifier")
  const cwd = workspaceRoot(exec)
  const knowledgeRoot = validateRelativePath(config.domainKnowledgeRoot)
  const catalog = await loadDomainCatalog(ctx, exec, knowledgeRoot)
  const domain = catalog.domains.find(item => item.id === domainId)
  if (!domain) throw new DomainToolError("UNKNOWN_DOMAIN", "domain is not registered in the domain catalog")
  if (!domain.repositoryIds.includes(repositoryId)) throw new DomainToolError("UNKNOWN_REPOSITORY", "repository is not registered for the active domain")
  if (!domain.manifestPath.startsWith(`${domainId}/`)) throw new DomainToolError("INVALID_DOMAIN_CATALOG", "domain manifest path is outside its registered domain directory")
  const manifestPath = joinRelative(knowledgeRoot, domain.manifestPath)
  const manifest = await readJson(ctx, exec, manifestPath, knowledgeRoot, MAX_DOMAIN_MANIFEST_BYTES)
  const indexes = validateDomainManifest(manifest, domainId)
  const repository = indexes.repositories.get(repositoryId)
  if (!repository) throw new DomainToolError("UNKNOWN_REPOSITORY", "repository is not registered in the active domain manifest")
  if (!domain.repositoryIds.includes(repository.id)) throw new DomainToolError("DOMAIN_SCOPE_MISMATCH", "manifest repository is not permitted by the domain catalog")
  validateRelativePatterns(repository.readPaths, "readPaths")
  validateRelativePatterns(repository.denyPaths, "denyPaths")
  const sourceRoot = await resolveInside(ctx, repository.root, undefined, cwd, exec.signal)
  const sourceInfo = await ctx.fs.stat(sourceRoot, exec.signal)
  if (!sourceInfo || sourceInfo.type !== "directory") throw new DomainToolError("SOURCE_REPOSITORY_MISSING", "registered source checkout is not present")
  const gitMarker = await ctx.fs.lstat(`${repository.root}/.git`, { cwd }, exec.signal)
  if (!gitMarker || (gitMarker.type !== "directory" && gitMarker.type !== "file")) throw new DomainToolError("SOURCE_REPOSITORY_MISSING", "registered source root is not a Git checkout")
  return { domainId, domain, manifest, indexes, repository, workspaceRoot: cwd, knowledgeRoot }
}

export async function runTool(handler, args, exec) {
  try {
    return { ok: true, ...await handler(args, exec) }
  } catch (error) {
    if (error instanceof DomainToolError) return { ok: false, error: { code: error.code, message: error.message } }
    if (error?.code === "FS_STALE_VERSION") return { ok: false, error: { code: "STALE_STORE_VERSION", message: "the source or knowledge resource changed during this operation; reread it before retrying" } }
    return { ok: false, error: { code: "TOOL_FAILURE", message: "domain agent operation failed; no success is asserted" } }
  }
}
