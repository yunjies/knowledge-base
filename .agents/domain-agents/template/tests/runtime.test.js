import assert from "node:assert/strict"
import { readFile, stat as statFile } from "node:fs/promises"
import { resolve, relative, isAbsolute, sep } from "node:path"
import { fileURLToPath } from "node:url"
import { test } from "node:test"
import { createRuntime, runTool } from "../scripts/runtime.js"

const repositoryRoot = fileURLToPath(new URL("../../../../", import.meta.url))
const domainRoot = ".agents/domain-agents/template"
const domainId = "knowledge-base-operations"
const agent = { id: "session-test", session: { header: { cwd: repositoryRoot } } }
const signal = new AbortController().signal

async function loadJson(path) {
  return JSON.parse(await readFile(resolve(repositoryRoot, path), "utf8"))
}

class MemoryFs {
  constructor() {
    this.files = new Map()
    this.staleNextWrite = false
  }

  add(path, text) {
    this.files.set(resolve(repositoryRoot, path), { text, version: "v1" })
  }

  async resolve(path, options = {}) {
    const cwd = options.cwd ?? repositoryRoot
    const absolute = isAbsolute(path) ? resolve(path) : resolve(cwd, path)
    return { targetKey: absolute, displayPath: absolute }
  }

  contains(parent, child) {
    const result = relative(parent.targetKey, child.targetKey)
    return result === "" || (result !== ".." && !result.startsWith(`..${sep}`) && !isAbsolute(result))
  }

  async stat(target) {
    const entry = this.files.get(target.targetKey)
    if (entry) return { type: "file", size: Buffer.byteLength(entry.text), version: entry.version }
    try {
      const info = await statFile(target.targetKey)
      if (!info.isFile()) return { type: "other", size: info.size, version: "external" }
      return { type: "file", size: info.size, version: "external" }
    } catch {
      return undefined
    }
  }

  async streamText(target) {
    const entry = this.files.get(target.targetKey)
    const text = entry?.text ?? await readFile(target.targetKey, "utf8")
    return (async function* () {
      for (let offset = 0; offset < text.length; offset += 257) yield text.slice(offset, offset + 257)
    })()
  }

  async writeText(target, content, expected, signalValue, policy) {
    if (policy?.mode !== "workspace-write" || policy.workspaceRoot !== repositoryRoot) throw new Error("sandbox policy was not passed")
    const existing = this.files.get(target.targetKey)
    if (this.staleNextWrite && existing) {
      this.staleNextWrite = false
      this.files.set(target.targetKey, { ...existing, version: "v77" })
    }
    const current = this.files.get(target.targetKey)
    if (!current || expected?.kind !== "replaceIfVersion" || expected.version !== current.version) {
      throw Object.assign(new Error("stale target"), { code: "FS_STALE_VERSION" })
    }
    const nextVersion = `v${Number(existing.version.slice(1)) + 1}`
    this.files.set(target.targetKey, { text: content, version: nextVersion })
    return { operation: "update", version: nextVersion, before: existing.text, after: content }
  }
}

async function setupRuntime() {
  const fs = new MemoryFs()
  const base = resolve(repositoryRoot, domainRoot)
  for (const name of ["resource-catalog.json", "path-policy.json", "test-spec.json", "review-workflow.json", "knowledge-store.json"]) {
    fs.add(`${domainRoot}/data/${name}`, await readFile(resolve(base, "data", name), "utf8"))
  }
  const catalog = await loadJson(`${domainRoot}/data/resource-catalog.json`)
  for (const resource of catalog.resources) fs.add(resource.path, await readFile(resolve(repositoryRoot, resource.path), "utf8"))
  const runtime = createRuntime({ fs }, { domainId, domainRoot })
  runtime.domainId = domainId
  const exec = { agent, signal, domainId }
  async function invoke(method, args = {}) {
    return runTool(runtime[method].bind(runtime), args, exec)
  }
  return { fs, runtime, invoke }
}

function fieldsFor(stage) {
  const fields = {}
  for (const key of stage.requiredResultFields) {
    const constraint = stage.fieldConstraints[key]
    if (constraint.type === "string") fields[key] = constraint.enum?.[0] ?? "evidence-ref"
    else if (constraint.type === "array") fields[key] = Array.from({ length: constraint.minItems ?? 0 }, (_, index) => ({ id: `${key}-${index}` }))
    else if (constraint.type === "object") fields[key] = {}
    else if (constraint.type === "boolean") fields[key] = true
    else if (constraint.type === "integer" || constraint.type === "number") fields[key] = 1
  }
  return fields
}

async function reviewStateAt(invoke, workflow, targetStage) {
  let state
  for (let index = 0; index <= workflow.stages.length; index += 1) {
    const current = await invoke("advanceReview", state ? { state } : {})
    assert.equal(current.ok, true)
    if (current.stage.id === targetStage) return current.state
    const stage = current.stage
    const outcome = Object.keys(stage.transitions)[0]
    const next = await invoke("advanceReview", {
      state: current.state,
      submission: { outcome, fields: fieldsFor(stage), evidence: [{ ref: `${stage.id}-evidence` }] }
    })
    assert.equal(next.ok, true, stage.id)
    state = next.state
  }
  throw new Error(`review stage ${targetStage} was not reachable`)
}

test("runtime fetches every registered resource through the path allowlist", async () => {
  const { invoke } = await setupRuntime()
  const access = await invoke("getAccessPaths")
  assert.equal(access.ok, true)
  const catalog = await loadJson(`${domainRoot}/data/resource-catalog.json`)
  assert.equal(access.readPaths.length, catalog.resources.length)
  assert.deepEqual(access.policySources.map(source => source.resourceId), ["agent-policy", "directory-map"])
  assert.deepEqual(access.writePaths.map(target => target.path), [`${domainRoot}/data/knowledge-store.json`])
  for (const resource of catalog.resources) {
    const result = await invoke("getKnowledgeResource", { resourceId: resource.id, offset: 1, limit: 2 })
    assert.equal(result.ok, true, resource.id)
    assert.equal(result.resourceId, resource.id)
    assert.ok(result.lines.length > 0, resource.id)
    assert.equal(typeof result.sourceVersion, "string")
  }
})

test("version, test, and path tools consume every domain data entry", async () => {
  const { invoke } = await setupRuntime()
  const version = await invoke("getVersionControlInstructions", { offset: 1, limit: 5 })
  assert.equal(version.resourceId, "version-control")
  assert.equal(version.ok, true)
  const testSpec = await loadJson(`${domainRoot}/data/test-spec.json`)
  for (const changeKind of testSpec.changeKinds) {
    const result = await invoke("getTestSpecification", { changeKind: changeKind.id })
    assert.equal(result.ok, true, changeKind.id)
    assert.deepEqual(result.resourceIds, changeKind.resourceIds)
  }
})

test("runtime rejects unregistered resources, invalid ranges, and unknown test kinds", async () => {
  const { invoke } = await setupRuntime()
  assert.equal((await invoke("getKnowledgeResource", { resourceId: "../../AGENTS.md" })).error.code, "RESOURCE_NOT_ALLOWED")
  assert.equal((await invoke("getKnowledgeResource", { resourceId: "agent-policy", limit: 201 })).error.code, "INVALID_RANGE")
  assert.equal((await invoke("getTestSpecification", { changeKind: "unknown" })).error.code, "UNKNOWN_CHANGE_KIND")
})

test("review runner reaches every declared stage and loads each stage resource", async () => {
  const { invoke } = await setupRuntime()
  const workflow = await loadJson(`${domainRoot}/data/review-workflow.json`)
  let state
  let visited = 0
  while (true) {
    const current = await invoke("advanceReview", state ? { state } : {})
    assert.equal(current.ok, true)
    if (current.terminal) {
      assert.equal(current.state.status, "complete")
      break
    }
    const stage = current.stage
    assert.ok(stage)
    visited += 1
    for (const resourceId of stage.resourceIds) {
      const source = await invoke("getKnowledgeResource", { resourceId, offset: 1, limit: 1 })
      assert.equal(source.ok, true, `${stage.id}:${resourceId}`)
    }
    if (stage.id === "dispatch") assert.equal(stage.delegationOwner, "session-leader")
    const outcome = Object.keys(stage.transitions)[0]
    const advanced = await invoke("advanceReview", { state: current.state, submission: { outcome, fields: fieldsFor(stage), evidence: [{ ref: `${stage.id}-evidence` }] } })
    assert.equal(advanced.ok, true, stage.id)
    state = advanced.state
  }
  assert.equal(visited, workflow.stages.length)
})

test("runtime validates every declared review transition", async () => {
  const { invoke } = await setupRuntime()
  const workflow = await loadJson(`${domainRoot}/data/review-workflow.json`)
  for (const stage of workflow.stages) {
    for (const [outcome, nextStage] of Object.entries(stage.transitions)) {
      const state = await reviewStateAt(invoke, workflow, stage.id)
      const result = await invoke("advanceReview", {
        state,
        submission: { outcome, fields: fieldsFor(stage), evidence: [{ ref: `${stage.id}-${outcome}` }] }
      })
      assert.equal(result.ok, true, `${stage.id}:${outcome}`)
      assert.equal(result.state.currentStage, nextStage, `${stage.id}:${outcome}`)
    }
  }
})

test("knowledge CRUD runs against the version-guarded in-memory store", async () => {
  const { invoke } = await setupRuntime()
  const created = await invoke("manageKnowledge", { action: "create", recordId: "runbook-1", title: "Runbook", body: "Structured body", tags: ["ops"] })
  assert.equal(created.ok, true)
  assert.equal(created.record.revision, 1)
  const listed = await invoke("manageKnowledge", { action: "list" })
  assert.equal(listed.records.length, 1)
  const read = await invoke("manageKnowledge", { action: "get", recordId: "runbook-1" })
  assert.equal(read.record.body, "Structured body")
  const stale = await invoke("manageKnowledge", { action: "update", recordId: "runbook-1", expectedRevision: 0, title: "Runbook", body: "Stale" })
  assert.equal(stale.error.code, "STALE_RECORD_VERSION")
  const updated = await invoke("manageKnowledge", { action: "update", recordId: "runbook-1", expectedRevision: 1, title: "Runbook", body: "Updated" })
  assert.equal(updated.record.revision, 2)
  const deleted = await invoke("manageKnowledge", { action: "delete", recordId: "runbook-1", expectedRevision: 2 })
  assert.equal(deleted.operation, "deleted")
  assert.equal((await invoke("manageKnowledge", { action: "list" })).records.length, 0)
})

test("runtime maps concurrent stale writes to a structured failure", async () => {
  const { fs, invoke } = await setupRuntime()
  const created = await invoke("manageKnowledge", { action: "create", recordId: "runbook-2", title: "Runbook", body: "Body" })
  assert.equal(created.ok, true)
  fs.staleNextWrite = true
  const result = await invoke("manageKnowledge", { action: "update", recordId: "runbook-2", expectedRevision: 1, title: "Runbook", body: "Race" })
  assert.equal(result.ok, false)
  assert.equal(result.error.code, "STALE_STORE_VERSION")
})
