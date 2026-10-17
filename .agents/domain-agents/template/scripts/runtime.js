import { applyKnowledgeOperation, advanceReview, beginReview, DomainToolError, validateRelativePath } from "./engine.js"

const MAX_RESOURCE_LINES = 200

async function readBoundedText(ctx, target, maxBytes, signal) {
  const stream = await ctx.fs.streamText(target, signal)
  const chunks = []
  let size = 0
  for await (const chunk of stream) {
    size += Buffer.byteLength(chunk, "utf8")
    if (size > maxBytes) throw new DomainToolError("RESOURCE_TOO_LARGE", "resource exceeds its declared size limit")
    chunks.push(chunk)
  }
  return chunks.join("")
}

function requireWorkspace(exec) {
  const cwd = exec.agent?.session?.header?.cwd
  if (typeof cwd !== "string" || cwd.length === 0) throw new DomainToolError("WORKSPACE_UNAVAILABLE", "calling agent has no workspace root")
  return cwd
}

function joinRelative(left, right) {
  return `${validateRelativePath(left)}/${validateRelativePath(right)}`
}

async function resolvedInside(ctx, relativePath, parentPath, cwd, signal) {
  const path = validateRelativePath(relativePath)
  const target = await ctx.fs.resolve(path, { cwd, signal })
  const workspaceRoot = await ctx.fs.resolve(cwd, { cwd, signal })
  const parent = parentPath ? await ctx.fs.resolve(validateRelativePath(parentPath), { cwd, signal }) : workspaceRoot
  if (!ctx.fs.contains(workspaceRoot, parent) || !ctx.fs.contains(parent, target)) throw new DomainToolError("PATH_OUTSIDE_SCOPE", "resolved path is outside its registered workspace root")
  return target
}

async function readJson(ctx, exec, domainRoot, fileName) {
  const cwd = requireWorkspace(exec)
  const relativePath = joinRelative(domainRoot, `data/${fileName}`)
  const target = await resolvedInside(ctx, relativePath, domainRoot, cwd, exec.signal)
  const info = await ctx.fs.stat(target, exec.signal)
  if (!info || info.type !== "file") throw new DomainToolError("DATA_FILE_MISSING", `${fileName} is missing or is not a regular file`)
  if (info.size !== undefined && info.size > 200000) throw new DomainToolError("DATA_FILE_TOO_LARGE", `${fileName} exceeds the data file size limit`)
  const text = await readBoundedText(ctx, target, 200000, exec.signal)
  let value
  try {
    value = JSON.parse(text)
  } catch {
    throw new DomainToolError("INVALID_JSON", `${fileName} is not valid JSON`)
  }
  if (value.domainId !== exec.domainId) throw new DomainToolError("DOMAIN_MISMATCH", `${fileName} belongs to another domain`)
  if (value.schemaVersion !== 1) throw new DomainToolError("UNSUPPORTED_SCHEMA", `${fileName} has an unsupported schema version`)
  return { value, target, info, cwd }
}

function validateResourceReferences(resourceIds, catalog, policy) {
  if (!Array.isArray(resourceIds) || resourceIds.some(id => typeof id !== "string")) throw new DomainToolError("INVALID_RESOURCE_INDEX", "resource ids must be a string array")
  for (const id of resourceIds) {
    if (!policy.readResourceIds.includes(id) || !catalog.resources.some(resource => resource.id === id)) throw new DomainToolError("INVALID_RESOURCE_INDEX", `resource ${id} is not both registered and readable`)
  }
}

async function readResource(ctx, exec, config, resourceId, offset = 1, limit = 120) {
  if (!Number.isSafeInteger(offset) || offset < 1) throw new DomainToolError("INVALID_RANGE", "offset must be a positive line number")
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_RESOURCE_LINES) throw new DomainToolError("INVALID_RANGE", `limit must be between 1 and ${MAX_RESOURCE_LINES}`)
  const { value: catalog } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "resource-catalog.json")
  const { value: policy } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "path-policy.json")
  if (!policy.readResourceIds.includes(resourceId)) throw new DomainToolError("RESOURCE_NOT_ALLOWED", "resource is not in the readable resource allowlist")
  const resource = catalog.resources.find(item => item.id === resourceId)
  if (!resource) throw new DomainToolError("RESOURCE_NOT_FOUND", "resource id is not registered")
  if (resource.format !== "markdown" || !Number.isSafeInteger(resource.maxBytes) || resource.maxBytes < 1 || resource.maxBytes > 1000000) throw new DomainToolError("INVALID_RESOURCE", "resource metadata does not satisfy its schema")
  const cwd = requireWorkspace(exec)
  const target = await resolvedInside(ctx, resource.path, undefined, cwd, exec.signal)
  const info = await ctx.fs.stat(target, exec.signal)
  if (!info || info.type !== "file") throw new DomainToolError("RESOURCE_MISSING", "registered resource is missing or is not a regular file")
  if (info.size !== undefined && info.size > resource.maxBytes) throw new DomainToolError("RESOURCE_TOO_LARGE", "registered resource exceeds its declared size limit")
  const text = await readBoundedText(ctx, target, resource.maxBytes, exec.signal)
  const lines = text.split(/\r?\n/u)
  const start = offset - 1
  const selected = lines.slice(start, start + limit)
  return {
    resourceId,
    title: resource.title,
    path: resource.path,
    format: resource.format,
    sourceVersion: info.version,
    offset,
    lines: selected.map((line, index) => ({ number: start + index + 1, text: line })),
    totalLines: lines.length,
    nextOffset: start + selected.length < lines.length ? start + selected.length + 1 : null
  }
}

export function createRuntime(ctx, config) {
  return {
    async getVersionControlInstructions(args, exec) {
      return readResource(ctx, exec, config, "version-control", args.offset ?? 1, args.limit ?? 120)
    },
    async getKnowledgeResource(args, exec) {
      return readResource(ctx, exec, config, args.resourceId, args.offset ?? 1, args.limit ?? 120)
    },
    async getAccessPaths(_args, exec) {
      const { value: policy } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "path-policy.json")
      const { value: catalog } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "resource-catalog.json")
      validateResourceReferences(policy.readResourceIds, catalog, policy)
      validateResourceReferences(policy.policyResourceIds, catalog, policy)
      const policySources = policy.policyResourceIds.map(id => {
        const resource = catalog.resources.find(item => item.id === id)
        return { resourceId: id, path: resource.path }
      })
      const readPaths = policy.readResourceIds.map(id => {
        const resource = catalog.resources.find(item => item.id === id)
        if (!resource) throw new DomainToolError("INVALID_PATH_POLICY", `read resource ${id} is not registered`)
        return { resourceId: id, path: resource.path, operation: "read" }
      })
      const writePaths = policy.writeTargets.map(target => ({ ...target, path: joinRelative(config.domainRoot, target.path) }))
      return { domainId: config.domainId, policySources, readPaths, writePaths, deniedForms: policy.denyPathForms }
    },
    async getTestSpecification(args, exec) {
      const { value: testSpec } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "test-spec.json")
      const { value: catalog } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "resource-catalog.json")
      const { value: policy } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "path-policy.json")
      const changeKind = testSpec.changeKinds.find(item => item.id === args.changeKind)
      if (!changeKind) throw new DomainToolError("UNKNOWN_CHANGE_KIND", `change kind ${args.changeKind} is not registered`)
      validateResourceReferences(changeKind.resourceIds, catalog, policy)
      return { domainId: config.domainId, ...changeKind }
    },
    async advanceReview(args, exec) {
      const { value: workflow } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "review-workflow.json")
      const { value: catalog } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "resource-catalog.json")
      const { value: policy } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "path-policy.json")
      const state = args.state ?? beginReview(workflow)
      const nextState = args.submission ? advanceReview(workflow, state, args.submission) : state
      const stage = workflow.stages.find(item => item.id === nextState.currentStage)
      if (stage) validateResourceReferences(stage.resourceIds, catalog, policy)
      return {
        state: nextState,
        stage: stage ?? null,
        terminal: nextState.status === "complete" || nextState.status === "blocked",
        guidanceTool: "get_knowledge_resource"
      }
    },
    async manageKnowledge(args, exec) {
      const { value: policy } = await readJson(ctx, { ...exec, domainId: config.domainId }, config.domainRoot, "path-policy.json")
      const targetRule = policy.writeTargets.find(item => item.id === "knowledge-records")
      const policyOperation = args.action === "get" || args.action === "list" ? "read" : args.action
      if (!targetRule || targetRule.path !== "data/knowledge-store.json" || targetRule.versionGuarded !== true || !targetRule.operations.includes(policyOperation)) throw new DomainToolError("WRITE_NOT_ALLOWED", "operation is not allowed for the knowledge store")
      const relativePath = joinRelative(config.domainRoot, targetRule.path)
      const target = await resolvedInside(ctx, relativePath, config.domainRoot, requireWorkspace(exec), exec.signal)
      const info = await ctx.fs.stat(target, exec.signal)
      if (!info || info.type !== "file") throw new DomainToolError("STORE_MISSING", "knowledge store is missing or is not a regular file")
      if (info.size !== undefined && info.size > 1000000) throw new DomainToolError("STORE_TOO_LARGE", "knowledge store exceeds the size limit")
      const text = await readBoundedText(ctx, target, 1000000, exec.signal)
      let store
      try {
        store = JSON.parse(text)
      } catch {
        throw new DomainToolError("INVALID_STORE", "knowledge store is not valid JSON")
      }
      if (store.domainId !== config.domainId || store.schemaVersion !== 1) throw new DomainToolError("DOMAIN_MISMATCH", "knowledge store schema or domain does not match")
      const operation = applyKnowledgeOperation(store, {
        ...args,
        record: args.title === undefined && args.body === undefined ? undefined : {
          id: args.recordId,
          title: args.title,
          body: args.body,
          tags: args.tags
        }
      })
      if (operation.store === store) return { domainId: config.domainId, ...operation.result }
      const writeResult = await ctx.fs.writeText(
        target,
        `${JSON.stringify(operation.store, null, 2)}\n`,
        { kind: "replaceIfVersion", version: info.version },
        exec.signal,
        { mode: "workspace-write", workspaceRoot: requireWorkspace(exec), sessionId: exec.agent.id }
      )
      return { domainId: config.domainId, ...operation.result, storeVersion: writeResult.version }
    }
  }
}

export async function runTool(handler, args, exec) {
  try {
    return { ok: true, ...await handler(args, exec) }
  } catch (error) {
    if (error instanceof DomainToolError) return { ok: false, error: { code: error.code, message: error.message } }
    if (error?.code === "FS_STALE_VERSION") return { ok: false, error: { code: "STALE_STORE_VERSION", message: "knowledge store changed during this operation; reread it before retrying" } }
    return { ok: false, error: { code: "TOOL_FAILURE", message: "host tool operation failed; no success is asserted" } }
  }
}
